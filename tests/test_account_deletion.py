"""
Account deletion regression tests.

Covers authenticated identity authority, owned-data purge, employer listing
detachment, RevenueCat deleted-account barriers and missing-auth rejection.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.db.models import (
    AIQuotaPeriod,
    InternshipListing,
    ProcessingJob,
    RevenueCatWebhookEvent,
    StudentProfile,
    SubscriptionEntitlement,
)
from app.services import account_deletion as deletion_service
from app.services.account_deletion import (
    AccountDeletionError,
    delete_authenticated_account,
    deleted_account_event_id,
)
from app.services.revenuecat_reconciliation import (
    reconcile_student_subscription,
)
from app.services.revenuecat_webhook import process_revenuecat_webhook

from tests.db import TestingSessionLocal


def test_delete_account_requires_authentication(client):
    response = client.delete("/api/v1/auth/account")

    assert response.status_code == 401


def test_delete_account_uses_verified_identity_only(
    client,
    mock_supabase_auth,
    monkeypatch,
):
    import app.api.v1.endpoints.auth as auth_endpoint

    authenticated_user_id = uuid4()
    attacker_user_id = uuid4()
    captured = {}

    def fake_delete(db, *, user_id):
        captured["user_id"] = user_id
        return {
            "deleted": True,
            "message": "InternMatch AI account deleted.",
        }

    monkeypatch.setattr(
        auth_endpoint,
        "delete_authenticated_account",
        fake_delete,
    )

    token = f"valid-user-{authenticated_user_id}"

    response = client.delete(
        (
            "/api/v1/auth/account"
            f"?user_id={attacker_user_id}"
        ),
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert captured["user_id"] == authenticated_user_id
    assert captured["user_id"] != attacker_user_id


def test_delete_account_purges_owned_rows_and_detaches_employer_listing(
    monkeypatch,
):
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    monkeypatch.setattr(
        deletion_service,
        "_delete_supabase_auth_user",
        lambda *, user_id: None,
    )

    with TestingSessionLocal() as db:
        profile = StudentProfile(
            user_id=user_id,
            full_name="Deletion Test User",
        )
        db.add(profile)

        job = ProcessingJob(
            user_id=user_id,
            job_type="cv_extraction",
        )
        db.add(job)

        entitlement = SubscriptionEntitlement(
            user_id=user_id,
            entitlement_id="pro_student",
            status="active",
            is_active=True,
            will_renew=True,
        )
        db.add(entitlement)

        quota = AIQuotaPeriod(
            user_id=user_id,
            feature_key="cv_analysis",
            plan_key="free",
            period_start=now,
            period_end=now + timedelta(days=30),
            used_count=0,
            reserved_count=0,
        )
        db.add(quota)

        listing = InternshipListing(
            employer_user_id=user_id,
            listing_source="employer",
            title="Deletion Test Internship",
            company="Deletion Test Company",
            location="Remote",
            work_type="Remote",
            description="Test listing retained for candidate history.",
            required_skills=["Python"],
            preferred_skills=[],
            is_active=True,
        )
        db.add(listing)

        db.commit()
        listing_id = listing.id

        result = delete_authenticated_account(
            db,
            user_id=user_id,
        )

        assert result["deleted"] is True

        assert (
            db.query(StudentProfile)
            .filter(StudentProfile.user_id == user_id)
            .count()
            == 0
        )
        assert (
            db.query(ProcessingJob)
            .filter(ProcessingJob.user_id == user_id)
            .count()
            == 0
        )
        assert (
            db.query(SubscriptionEntitlement)
            .filter(SubscriptionEntitlement.user_id == user_id)
            .count()
            == 0
        )
        assert (
            db.query(AIQuotaPeriod)
            .filter(AIQuotaPeriod.user_id == user_id)
            .count()
            == 0
        )

        detached_listing = db.get(
            InternshipListing,
            listing_id,
        )
        assert detached_listing is not None
        assert detached_listing.employer_user_id is None
        assert detached_listing.is_active is False
        assert detached_listing.listing_source == "employer"

        tombstone = db.get(
            RevenueCatWebhookEvent,
            deleted_account_event_id(user_id),
        )
        assert tombstone is not None
        assert tombstone.user_id == user_id
        assert tombstone.outcome == "account_deleted"


def test_revenuecat_reconciliation_does_not_resurrect_deleted_account(
    monkeypatch,
):
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    with TestingSessionLocal() as db:
        db.add(
            RevenueCatWebhookEvent(
                event_id=deleted_account_event_id(user_id),
                user_id=user_id,
                event_type="ACCOUNT_DELETED",
                event_timestamp_ms=int(now.timestamp() * 1000),
                outcome="account_deleted",
                received_at=now,
                processed_at=now,
            )
        )
        db.commit()

        def fail_provider_call(*args, **kwargs):
            raise AssertionError(
                "RevenueCat provider must not be called "
                "for a deleted account"
            )

        import app.services.revenuecat_reconciliation as reconciliation

        monkeypatch.setattr(
            reconciliation,
            "_fetch_revenuecat_subscriptions",
            fail_provider_call,
        )

        result = reconcile_student_subscription(
            db,
            user_id=user_id,
            min_interval_seconds=0,
        )

        assert result["outcome"] == "ignored_deleted_account"
        assert result["subscription"]["plan"] == "free"

        assert (
            db.query(SubscriptionEntitlement)
            .filter(SubscriptionEntitlement.user_id == user_id)
            .count()
            == 0
        )


def test_revenuecat_webhook_ignores_deleted_account():
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    event_id = f"deleted-account-event-{uuid4()}"

    with TestingSessionLocal() as db:
        db.add(
            RevenueCatWebhookEvent(
                event_id=deleted_account_event_id(user_id),
                user_id=user_id,
                event_type="ACCOUNT_DELETED",
                event_timestamp_ms=int(now.timestamp() * 1000),
                outcome="account_deleted",
                received_at=now,
                processed_at=now,
            )
        )
        db.commit()

        result = process_revenuecat_webhook(
            db,
            payload={
                "event": {
                    "id": event_id,
                    "type": "INITIAL_PURCHASE",
                    "event_timestamp_ms": int(now.timestamp() * 1000),
                    "app_user_id": str(user_id),
                    "entitlement_ids": ["pro_student"],
                }
            },
        )

        assert result["outcome"] == "ignored_deleted_account"

        assert (
            db.query(SubscriptionEntitlement)
            .filter(SubscriptionEntitlement.user_id == user_id)
            .count()
            == 0
        )

        ledger = db.get(
            RevenueCatWebhookEvent,
            event_id,
        )
        assert ledger is not None
        assert ledger.user_id is None
        assert ledger.outcome == "ignored_deleted_account"
def test_delete_account_does_not_touch_other_user(monkeypatch):
    deleting_user_id = uuid4()
    other_user_id = uuid4()

    monkeypatch.setattr(
        deletion_service,
        "_delete_supabase_auth_user",
        lambda *, user_id: None,
    )

    monkeypatch.setattr(
        deletion_service,
        "_delete_private_storage",
        lambda **kwargs: None,
    )

    with TestingSessionLocal() as db:
        deleting_profile = StudentProfile(
            user_id=deleting_user_id,
            full_name="Deleting User",
        )
        other_profile = StudentProfile(
            user_id=other_user_id,
            full_name="Other User",
        )

        db.add_all(
            [
                deleting_profile,
                other_profile,
                ProcessingJob(
                    user_id=deleting_user_id,
                    job_type="cv_extraction",
                ),
                ProcessingJob(
                    user_id=other_user_id,
                    job_type="cv_extraction",
                ),
            ]
        )
        db.commit()

        delete_authenticated_account(
            db,
            user_id=deleting_user_id,
        )

        assert (
            db.query(StudentProfile)
            .filter(StudentProfile.user_id == deleting_user_id)
            .count()
            == 0
        )

        assert (
            db.query(StudentProfile)
            .filter(StudentProfile.user_id == other_user_id)
            .count()
            == 1
        )

        assert (
            db.query(ProcessingJob)
            .filter(ProcessingJob.user_id == deleting_user_id)
            .count()
            == 0
        )

        assert (
            db.query(ProcessingJob)
            .filter(ProcessingJob.user_id == other_user_id)
            .count()
            == 1
        )


def test_storage_failure_prevents_product_purge_and_auth_deletion(
    monkeypatch,
):
    user_id = uuid4()
    auth_calls = []

    def fail_storage(**kwargs):
        raise AccountDeletionError(
            "Private account storage deletion failed."
        )

    def capture_auth_delete(*, user_id):
        auth_calls.append(user_id)

    monkeypatch.setattr(
        deletion_service,
        "_delete_private_storage",
        fail_storage,
    )
    monkeypatch.setattr(
        deletion_service,
        "_delete_supabase_auth_user",
        capture_auth_delete,
    )

    with TestingSessionLocal() as db:
        db.add(
            StudentProfile(
                user_id=user_id,
                full_name="Storage Failure User",
            )
        )
        db.add(
            ProcessingJob(
                user_id=user_id,
                job_type="cv_extraction",
            )
        )
        db.commit()

        with pytest.raises(AccountDeletionError):
            delete_authenticated_account(
                db,
                user_id=user_id,
            )

        assert (
            db.query(StudentProfile)
            .filter(StudentProfile.user_id == user_id)
            .count()
            == 1
        )

        assert (
            db.query(ProcessingJob)
            .filter(ProcessingJob.user_id == user_id)
            .count()
            == 1
        )

        assert (
            db.get(
                RevenueCatWebhookEvent,
                deleted_account_event_id(user_id),
            )
            is None
        )

        assert auth_calls == []


def test_auth_delete_failure_never_returns_false_success_and_keeps_retry_barrier(
    monkeypatch,
):
    user_id = uuid4()

    monkeypatch.setattr(
        deletion_service,
        "_delete_private_storage",
        lambda **kwargs: None,
    )

    def fail_auth_delete(*, user_id):
        raise AccountDeletionError(
            "Authentication identity deletion failed."
        )

    monkeypatch.setattr(
        deletion_service,
        "_delete_supabase_auth_user",
        fail_auth_delete,
    )

    with TestingSessionLocal() as db:
        db.add(
            StudentProfile(
                user_id=user_id,
                full_name="Auth Failure User",
            )
        )
        db.add(
            ProcessingJob(
                user_id=user_id,
                job_type="cv_extraction",
            )
        )
        db.commit()

        with pytest.raises(AccountDeletionError):
            delete_authenticated_account(
                db,
                user_id=user_id,
            )

        # Product data is intentionally committed before external Auth
        # deletion so a transient identity-service failure can be retried.
        assert (
            db.query(StudentProfile)
            .filter(StudentProfile.user_id == user_id)
            .count()
            == 0
        )

        assert (
            db.query(ProcessingJob)
            .filter(ProcessingJob.user_id == user_id)
            .count()
            == 0
        )

        tombstone = db.get(
            RevenueCatWebhookEvent,
            deleted_account_event_id(user_id),
        )

        assert tombstone is not None
        assert tombstone.user_id == user_id
        assert tombstone.outcome == "account_deleted"
