"""
Authenticated account deletion orchestration.

The authenticated Supabase UUID is the sole account identity. The deletion
flow removes user-controlled application data and private storage objects,
detaches employer-owned listings where candidate history must remain intact,
records a minimal RevenueCat deletion barrier, and finally removes the
Supabase Auth identity.

The RevenueCat deletion barrier is intentionally retained as a minimal
security/consistency record so delayed provider events cannot recreate
subscription authority for a deleted account.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session
from supabase import create_client

from app.core.config import settings
from app.db.models import (
    AIQuotaOperation,
    AIQuotaPeriod,
    AIUsageEvent,
    InternshipListing,
    ProcessingJob,
    RevenueCatWebhookEvent,
    StudentProfile,
    SubscriptionEntitlement,
)
from app.services.avatar_storage import delete_candidate_avatar
from app.services.cv_storage import delete_candidate_cv


DELETED_ACCOUNT_EVENT_PREFIX = "account-deleted:"


class AccountDeletionError(RuntimeError):
    """Raised when account deletion cannot be completed safely."""


def deleted_account_event_id(user_id: UUID) -> str:
    return f"{DELETED_ACCOUNT_EVENT_PREFIX}{user_id}"


def is_account_deleted(
    db: Session,
    *,
    user_id: UUID,
) -> bool:
    """Return whether the account has a server-side deletion barrier."""
    return (
        db.get(
            RevenueCatWebhookEvent,
            deleted_account_event_id(user_id),
        )
        is not None
    )


def _require_storage_configuration() -> None:
    url = (settings.SUPABASE_URL or "").strip()
    key = (settings.SUPABASE_SERVICE_ROLE_KEY or "").strip()

    if (
        not url
        or "placeholder" in url.lower()
        or not key
        or "placeholder" in key.lower()
    ):
        raise AccountDeletionError(
            "Account deletion storage service is unavailable."
        )


def _delete_supabase_auth_user(*, user_id: UUID) -> None:
    url = (settings.SUPABASE_URL or "").strip()
    key = (settings.SUPABASE_SERVICE_ROLE_KEY or "").strip()

    if (
        not url
        or "placeholder" in url.lower()
        or not key
        or "placeholder" in key.lower()
    ):
        raise AccountDeletionError(
            "Account deletion identity service is unavailable."
        )

    try:
        client = create_client(url, key)
        client.auth.admin.delete_user(str(user_id))
    except Exception as exc:
        raise AccountDeletionError(
            "Authentication identity deletion failed."
        ) from exc


def _delete_private_storage(
    *,
    user_id: UUID,
    cv_storage_path: str | None,
    avatar_storage_path: str | None,
) -> None:
    if not cv_storage_path and not avatar_storage_path:
        return

    _require_storage_configuration()

    try:
        if cv_storage_path:
            delete_candidate_cv(
                user_id=user_id,
                storage_path=cv_storage_path,
            )

        if avatar_storage_path:
            deleted = delete_candidate_avatar(
                user_id=user_id,
                storage_path=avatar_storage_path,
            )
            if not deleted:
                raise AccountDeletionError(
                    "Profile avatar deletion could not be verified."
                )
    except AccountDeletionError:
        raise
    except Exception as exc:
        raise AccountDeletionError(
            "Private account storage deletion failed."
        ) from exc


def delete_authenticated_account(
    db: Session,
    *,
    user_id: UUID,
) -> dict[str, object]:
    """
    Permanently remove the authenticated InternMatch account data.

    Database deletion is committed before removing the external Auth identity.
    This lets an authenticated user safely retry the request if Supabase Auth
    deletion temporarily fails after product data has already been purged.
    """
    if not isinstance(user_id, UUID):
        raise AccountDeletionError(
            "Authenticated user identity is invalid."
        )

    profile = (
        db.query(StudentProfile)
        .filter(StudentProfile.user_id == user_id)
        .one_or_none()
    )

    cv_storage_path = (
        profile.cv_storage_path
        if profile is not None
        else None
    )
    avatar_storage_path = (
        profile.avatar_storage_path
        if profile is not None
        else None
    )

    _delete_private_storage(
        user_id=user_id,
        cv_storage_path=cv_storage_path,
        avatar_storage_path=avatar_storage_path,
    )

    now = datetime.now(timezone.utc)
    tombstone_id = deleted_account_event_id(user_id)

    try:
        # Remove telemetry before deleting jobs/quota operations referenced by it.
        (
            db.query(AIUsageEvent)
            .filter(AIUsageEvent.user_id == user_id)
            .delete(synchronize_session=False)
        )

        (
            db.query(AIQuotaOperation)
            .filter(AIQuotaOperation.user_id == user_id)
            .delete(synchronize_session=False)
        )

        (
            db.query(AIQuotaPeriod)
            .filter(AIQuotaPeriod.user_id == user_id)
            .delete(synchronize_session=False)
        )

        (
            db.query(ProcessingJob)
            .filter(ProcessingJob.user_id == user_id)
            .delete(synchronize_session=False)
        )

        (
            db.query(SubscriptionEntitlement)
            .filter(SubscriptionEntitlement.user_id == user_id)
            .delete(synchronize_session=False)
        )

        # Preserve candidate application history while removing ownership and
        # stopping further employer activity on deleted-account listings.
        (
            db.query(InternshipListing)
            .filter(InternshipListing.employer_user_id == user_id)
            .update(
                {
                    InternshipListing.employer_user_id: None,
                    InternshipListing.publication_status: "closed",
                    InternshipListing.is_active: False,
                },
                synchronize_session=False,
            )
        )

        # StudentProfile is the parent for candidate skills, education,
        # experience, projects, matches, applications and saved internships.
        # Their database FKs use ON DELETE CASCADE.
        if profile is not None:
            db.delete(profile)

        # Remove provider-ledger rows containing the user UUID, then retain one
        # minimal technical deletion barrier. This prevents delayed RevenueCat
        # events from recreating subscription entitlement state.
        (
            db.query(RevenueCatWebhookEvent)
            .filter(
                RevenueCatWebhookEvent.user_id == user_id,
                RevenueCatWebhookEvent.event_id != tombstone_id,
            )
            .delete(synchronize_session=False)
        )

        tombstone = db.get(
            RevenueCatWebhookEvent,
            tombstone_id,
        )

        if tombstone is None:
            tombstone = RevenueCatWebhookEvent(
                event_id=tombstone_id,
                user_id=user_id,
                event_type="ACCOUNT_DELETED",
                event_timestamp_ms=int(now.timestamp() * 1000),
                outcome="account_deleted",
                received_at=now,
                processed_at=now,
            )
            db.add(tombstone)
        else:
            tombstone.user_id = user_id
            tombstone.event_type = "ACCOUNT_DELETED"
            tombstone.outcome = "account_deleted"
            tombstone.processed_at = now

        db.commit()
    except Exception as exc:
        db.rollback()
        raise AccountDeletionError(
            "Account product-data deletion failed."
        ) from exc

    # External Auth deletion intentionally happens after the committed product
    # purge. If this call fails, the authenticated user can retry DELETE
    # /auth/account; the tombstone keeps provider state from resurrecting.
    _delete_supabase_auth_user(user_id=user_id)

    return {
        "deleted": True,
        "message": "InternMatch AI account deleted.",
    }
