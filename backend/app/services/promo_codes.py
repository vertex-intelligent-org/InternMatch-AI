"""Secure InternMatch-managed promotional code lifecycle."""

import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import PromoCampaign, PromoRedemption
from app.repositories.promo_code import PromoCodeRepository
from app.repositories.student_profile import StudentProfileRepository
from app.services.revenuecat_promo_grant import (
    RevenueCatPromoConfigurationError,
    RevenueCatPromoProviderError,
    grant_revenuecat_promotional_entitlement,
)
from app.services.revenuecat_reconciliation import (
    RevenueCatReconciliationConfigurationError,
    RevenueCatReconciliationProviderError,
    reconcile_employer_subscription,
    reconcile_student_subscription,
)
from app.services.subscription import (
    PRO_EMPLOYER_ENTITLEMENT_ID,
    PRO_STUDENT_ENTITLEMENT_ID,
    get_employer_subscription_snapshot,
    get_student_subscription_snapshot,
)

PROMO_DURATION_DAYS = 7
PROMO_PENDING_RETRY_AFTER_SECONDS = 120

AUDIENCE_STUDENT = "student"
AUDIENCE_EMPLOYER = "employer"

SUPPORTED_AUDIENCES = {
    AUDIENCE_STUDENT,
    AUDIENCE_EMPLOYER,
}


class PromoCodeError(RuntimeError):
    """Base promotional-code domain error."""


class PromoCodeDisabled(PromoCodeError):
    pass


class PromoCodeConfigurationError(PromoCodeError):
    pass


class PromoCodeInvalid(PromoCodeError):
    pass


class PromoCodeConflict(PromoCodeError):
    pass


class PromoCodeAlreadyRedeemed(PromoCodeError):
    pass


class PromoCodeInProgress(PromoCodeError):
    pass


class PromoCodeActivePro(PromoCodeError):
    pass


class PromoCampaignNotFound(PromoCodeError):
    pass


class PromoCodeProviderUnavailable(PromoCodeError):
    pass


def _as_utc(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _normalize_audience(
    value: str,
) -> str:
    normalized = (value or "").strip().lower()

    if normalized not in SUPPORTED_AUDIENCES:
        raise ValueError("Unsupported promo audience.")

    return normalized


def _normalize_code(
    value: str,
) -> str:
    normalized = (value or "").strip().upper()

    # High-entropy private codes only.
    # No spaces or punctuation that can be normalized ambiguously.
    if not re.fullmatch(
        r"[A-Z0-9_-]{16,64}",
        normalized,
    ):
        raise PromoCodeInvalid("Promo code is invalid or unavailable.")

    if not re.search(
        r"[A-Z]",
        normalized,
    ) or not re.search(
        r"[0-9]",
        normalized,
    ):
        raise PromoCodeInvalid("Promo code is invalid or unavailable.")

    return normalized


def _hmac_secret() -> str:
    secret = (settings.PROMO_CODE_HMAC_SECRET or "").strip()

    if len(secret) < 32:
        raise PromoCodeConfigurationError("Promo code validation is not configured.")

    return secret


def _digest_code(
    normalized_code: str,
) -> str:
    return hmac.new(
        _hmac_secret().encode("utf-8"),
        normalized_code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _code_hint(
    normalized_code: str,
) -> str:
    return normalized_code[:3] + "***" + normalized_code[-3:]


def _canonical_user_audience(
    db: Session,
    *,
    user_id: UUID,
) -> str:
    profile = StudentProfileRepository.get_by_user_id(
        db,
        user_id=user_id,
    )

    if profile is None:
        raise PromoCodeInvalid("Promo code is invalid or unavailable.")

    account_type = (profile.preferences or {}).get("account_type")

    normalized = (
        account_type.strip().lower()
        if isinstance(
            account_type,
            str,
        )
        else ""
    )

    if normalized == "employer":
        return AUDIENCE_EMPLOYER

    if normalized in {
        "intern",
        "student",
    }:
        return AUDIENCE_STUDENT

    raise PromoCodeInvalid("Promo code is invalid or unavailable.")


def _entitlement_for_audience(
    audience: str,
) -> str:
    if audience == AUDIENCE_EMPLOYER:
        return PRO_EMPLOYER_ENTITLEMENT_ID

    return PRO_STUDENT_ENTITLEMENT_ID


def _subscription_snapshot(
    db: Session,
    *,
    user_id: UUID,
    audience: str,
) -> dict[str, Any]:
    getter = (
        get_employer_subscription_snapshot
        if audience == AUDIENCE_EMPLOYER
        else get_student_subscription_snapshot
    )

    return getter(
        db,
        user_id=user_id,
    )


def _reconcile_after_grant(
    db: Session,
    *,
    user_id: UUID,
    audience: str,
) -> dict[str, Any]:
    reconcile = (
        reconcile_employer_subscription
        if audience == AUDIENCE_EMPLOYER
        else reconcile_student_subscription
    )

    return reconcile(
        db,
        user_id=user_id,
        min_interval_seconds=0,
    )


def create_campaign(
    db: Session,
    *,
    audience: str,
    code: str,
    admin_user_id: UUID,
    publish: bool = True,
) -> PromoCampaign:
    """
    Create a new campaign.

    Publishing automatically retires the previously published campaign
    for that audience. Existing user grants are not revoked.
    """

    normalized_audience = _normalize_audience(audience)

    normalized_code = _normalize_code(code)

    digest = _digest_code(normalized_code)

    existing = PromoCodeRepository.get_campaign_by_digest(
        db,
        audience=normalized_audience,
        code_digest=digest,
        published_only=False,
    )

    if existing is not None:
        raise PromoCodeConflict("That promo code is already registered.")

    now = datetime.now(timezone.utc)

    if publish:
        for campaign in PromoCodeRepository.retire_published_for_audience(
            db,
            audience=normalized_audience,
        ):
            campaign.status = "retired"
            campaign.retired_at = now
            campaign.retired_by_admin_user_id = admin_user_id
            campaign.updated_at = now

    campaign = PromoCampaign(
        audience=normalized_audience,
        code_digest=digest,
        code_hint=_code_hint(normalized_code),
        status=("published" if publish else "draft"),
        duration_days=PROMO_DURATION_DAYS,
        created_by_admin_user_id=(admin_user_id),
        created_at=now,
        updated_at=now,
    )

    db.add(campaign)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        raise PromoCodeConflict("Promo campaign conflicts with an existing campaign.") from exc

    db.refresh(campaign)

    return campaign


def publish_campaign(
    db: Session,
    *,
    campaign_id: UUID,
    admin_user_id: UUID,
) -> PromoCampaign:
    campaign = PromoCodeRepository.get_campaign(
        db,
        campaign_id=campaign_id,
        for_update=True,
    )

    if campaign is None:
        raise PromoCampaignNotFound("Promo campaign was not found.")

    if campaign.status == "retired":
        raise PromoCodeConflict("A retired promo campaign cannot be republished.")

    if campaign.status == "published":
        return campaign

    now = datetime.now(timezone.utc)

    for previous in PromoCodeRepository.retire_published_for_audience(
        db,
        audience=campaign.audience,
    ):
        if previous.id == campaign.id:
            continue

        previous.status = "retired"
        previous.retired_at = now
        previous.retired_by_admin_user_id = admin_user_id
        previous.updated_at = now

    campaign.status = "published"
    campaign.updated_at = now

    db.commit()
    db.refresh(campaign)

    return campaign


def retire_campaign(
    db: Session,
    *,
    campaign_id: UUID,
    admin_user_id: UUID,
) -> PromoCampaign:
    campaign = PromoCodeRepository.get_campaign(
        db,
        campaign_id=campaign_id,
        for_update=True,
    )

    if campaign is None:
        raise PromoCampaignNotFound("Promo campaign was not found.")

    if campaign.status == "retired":
        return campaign

    now = datetime.now(timezone.utc)

    campaign.status = "retired"
    campaign.retired_at = now
    campaign.retired_by_admin_user_id = admin_user_id
    campaign.updated_at = now

    db.commit()
    db.refresh(campaign)

    return campaign


def list_campaigns(
    db: Session,
    *,
    audience: str | None = None,
) -> list[PromoCampaign]:
    normalized = _normalize_audience(audience) if audience is not None else None

    return PromoCodeRepository.list_campaigns(
        db,
        audience=normalized,
    )


def get_redemption_status(
    db: Session,
    *,
    user_id: UUID,
) -> dict[str, Any]:
    audience = _canonical_user_audience(
        db,
        user_id=user_id,
    )

    redemption = PromoCodeRepository.get_redemption(
        db,
        user_id=user_id,
        audience=audience,
    )

    if redemption is None:
        return {
            "audience": audience,
            "used_once": False,
            "status": None,
            "access_expires_at": None,
        }

    return {
        "audience": audience,
        "used_once": (redemption.status == "redeemed"),
        "status": redemption.status,
        "access_expires_at": (redemption.access_expires_at),
    }


def redeem_promo_code(
    db: Session,
    *,
    user_id: UUID,
    code: str,
) -> dict[str, Any]:
    """
    Validate an InternMatch private code and ask RevenueCat to grant
    exactly seven days of the role-specific Pro entitlement.

    RevenueCat remains the authoritative entitlement provider.
    """

    if not settings.PROMO_CODES_ENABLED:
        raise PromoCodeDisabled("Promo redemption is not currently available.")

    normalized_code = _normalize_code(code)

    audience = _canonical_user_audience(
        db,
        user_id=user_id,
    )

    existing = PromoCodeRepository.get_redemption(
        db,
        user_id=user_id,
        audience=audience,
        for_update=True,
    )

    now = datetime.now(timezone.utc)

    if existing is not None and existing.status == "redeemed":
        raise PromoCodeAlreadyRedeemed("This account has already used its promotional access.")

    if existing is not None and existing.status == "pending":
        requested_at = _as_utc(existing.requested_at) or now

        if (now - requested_at).total_seconds() < (PROMO_PENDING_RETRY_AFTER_SECONDS):
            raise PromoCodeInProgress("A promo redemption is already being processed.")

    current_subscription = _subscription_snapshot(
        db,
        user_id=user_id,
        audience=audience,
    )

    if current_subscription.get("is_active") is True:
        raise PromoCodeActivePro("Pro access is already active on this account.")

    digest = _digest_code(normalized_code)

    campaign = PromoCodeRepository.get_campaign_by_digest(
        db,
        audience=audience,
        code_digest=digest,
        published_only=True,
        for_update=True,
    )

    # Wrong audience, retired, draft and unknown codes all produce the
    # same external result so the endpoint is not a code-discovery oracle.
    if campaign is None:
        raise PromoCodeInvalid("Promo code is invalid or unavailable.")

    preserve_pending_window = (
        existing is not None
        and existing.status == "pending"
        and existing.access_started_at is not None
        and existing.access_expires_at is not None
    )

    if preserve_pending_window:
        access_started_at = _as_utc(existing.access_started_at) or now

        access_expires_at = _as_utc(existing.access_expires_at) or (
            access_started_at + timedelta(days=PROMO_DURATION_DAYS)
        )
    else:
        access_started_at = now
        access_expires_at = access_started_at + timedelta(days=PROMO_DURATION_DAYS)

    if existing is None:
        redemption = PromoRedemption(
            campaign_id=campaign.id,
            user_id=user_id,
            audience=audience,
            status="pending",
            requested_at=now,
            access_started_at=(access_started_at),
            access_expires_at=(access_expires_at),
            created_at=now,
            updated_at=now,
        )

        db.add(redemption)
    else:
        redemption = existing
        redemption.campaign_id = campaign.id
        redemption.status = "pending"
        redemption.requested_at = now
        redemption.access_started_at = access_started_at
        redemption.access_expires_at = access_expires_at
        redemption.provider_subscription_id = None
        redemption.last_error_code = None
        redemption.updated_at = now

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        concurrent = PromoCodeRepository.get_redemption(
            db,
            user_id=user_id,
            audience=audience,
        )

        if concurrent is not None and concurrent.status == "redeemed":
            raise PromoCodeAlreadyRedeemed(
                "This account has already used its promotional access."
            ) from exc

        raise PromoCodeInProgress("A promo redemption is already being processed.") from exc

    redemption_id = redemption.id

    entitlement_lookup_key = _entitlement_for_audience(audience)

    try:
        grant_revenuecat_promotional_entitlement(
            user_id=user_id,
            entitlement_lookup_key=entitlement_lookup_key,
            expires_at=access_expires_at,
        )
    except RevenueCatPromoConfigurationError as exc:
        failed = PromoCodeRepository.get_redemption_by_id(
            db,
            redemption_id=redemption_id,
            for_update=True,
        )

        if failed is not None:
            failed.status = "failed"
            failed.last_error_code = "PROVIDER_CONFIGURATION"
            failed.access_started_at = None
            failed.access_expires_at = None
            failed.updated_at = datetime.now(timezone.utc)
            db.commit()

        raise PromoCodeConfigurationError("Promotional access provider is not configured.") from exc

    except RevenueCatPromoProviderError as exc:
        failed = PromoCodeRepository.get_redemption_by_id(
            db,
            redemption_id=redemption_id,
            for_update=True,
        )

        if failed is not None:
            failed.status = "failed"
            failed.last_error_code = "PROVIDER_UNAVAILABLE"
            failed.access_started_at = None
            failed.access_expires_at = None
            failed.updated_at = datetime.now(timezone.utc)
            db.commit()

        raise PromoCodeProviderUnavailable(
            "Promotional access provider is temporarily unavailable."
        ) from exc

    finalized = PromoCodeRepository.get_redemption_by_id(
        db,
        redemption_id=redemption_id,
        for_update=True,
    )

    if finalized is None:
        raise PromoCodeProviderUnavailable("Promotional redemption state could not be finalized.")

    # RevenueCat V2 grant_entitlement returns a Customer object.
    # Do not mislabel the Customer ID as a subscription ID.
    provider_subscription_id = None

    finalized.status = "redeemed"
    finalized.access_started_at = access_started_at
    finalized.access_expires_at = access_expires_at
    finalized.provider_subscription_id = provider_subscription_id
    finalized.last_error_code = None
    finalized.updated_at = datetime.now(timezone.utc)

    db.commit()

    sync_pending = False
    subscription = None

    try:
        reconciliation = _reconcile_after_grant(
            db,
            user_id=user_id,
            audience=audience,
        )

        subscription = (
            reconciliation.get("subscription")
            if isinstance(
                reconciliation,
                dict,
            )
            else None
        )

        expected_plan = "employer_pro" if audience == AUDIENCE_EMPLOYER else "pro_student"

        if not (
            isinstance(
                subscription,
                dict,
            )
            and subscription.get("plan") == expected_plan
            and subscription.get("is_active") is True
        ):
            sync_pending = True

    except (
        RevenueCatReconciliationConfigurationError,
        RevenueCatReconciliationProviderError,
    ):
        # The provider grant already succeeded. Never roll it back merely
        # because our recovery snapshot is temporarily unavailable.
        sync_pending = True

    return {
        "outcome": ("granted_sync_pending" if sync_pending else "granted"),
        "audience": audience,
        "plan": ("employer_pro" if audience == AUDIENCE_EMPLOYER else "pro_student"),
        "access_started_at": access_started_at,
        "access_expires_at": access_expires_at,
        "sync_pending": sync_pending,
        "subscription": subscription,
    }


def record_verified_store_redemption(
    *_args,
    **_kwargs,
) -> None:
    """
    Compatibility shim for the earlier foundation hook.

    Internal promo redemption is now completed only by the authenticated
    promo endpoint after RevenueCat's promotional-grant API succeeds.
    Ordinary store purchase webhooks must never consume a promo code.
    """

    return None
