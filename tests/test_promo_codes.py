"""Security and lifecycle tests for one-time promotional Pro access."""

from datetime import timedelta, timezone
from uuid import uuid4

import pytest
from app.core.config import settings
from app.db.models import (
    StudentProfile,
)
from app.repositories.promo_code import PromoCodeRepository
from app.services.promo_codes import (
    PromoCodeAlreadyRedeemed,
    PromoCodeInvalid,
    PromoCodeProviderUnavailable,
    create_campaign,
    redeem_promo_code,
    retire_campaign,
)
from app.services.revenuecat_promo_grant import (
    RevenueCatPromoProviderError,
)

from tests.db import TestingSessionLocal

TEST_HMAC_SECRET = (
    "promo-test-secret-"
    "0123456789abcdef"
    "0123456789abcdef"
)


def _configure_promo(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "PROMO_CODES_ENABLED",
        True,
    )

    monkeypatch.setattr(
        settings,
        "PROMO_CODE_HMAC_SECRET",
        TEST_HMAC_SECRET,
    )

    monkeypatch.setattr(
        settings,
        "REVENUECAT_PROMO_SECRET_KEY",
        "test-server-only-key",
    )

    monkeypatch.setattr(
        settings,
        "REVENUECAT_PROJECT_ID",
        "proj_test",
    )


def _create_profile(
    *,
    user_id,
    account_type,
):
    with TestingSessionLocal() as db:
        db.add(
            StudentProfile(
                user_id=user_id,
                full_name="Promo Tester",
                preferences={
                    "account_type":
                        account_type,
                },
            )
        )
        db.commit()


def _mock_successful_provider(
    monkeypatch,
):
    captured = {}

    def fake_grant(
        *,
        user_id,
        entitlement_lookup_key,
        expires_at,
    ):
        captured["user_id"] = user_id
        captured[
            "entitlement_lookup_key"
        ] = entitlement_lookup_key
        captured["expires_at"] = expires_at

        return {
            "object": "subscription",
            "id": "promo-subscription-test",
        }

    def fake_reconcile(
        db,
        *,
        user_id,
        min_interval_seconds=30,
    ):
        return {
            "outcome": "reconciled",
            "subscription": {
                "plan": "pro_student",
                "is_active": True,
            },
        }

    def fake_employer_reconcile(
        db,
        *,
        user_id,
        min_interval_seconds=30,
    ):
        return {
            "outcome": "reconciled",
            "subscription": {
                "plan": "employer_pro",
                "is_active": True,
            },
        }

    monkeypatch.setattr(
        "app.services.promo_codes."
        "grant_revenuecat_promotional_entitlement",
        fake_grant,
    )

    monkeypatch.setattr(
        "app.services.promo_codes."
        "reconcile_student_subscription",
        fake_reconcile,
    )

    monkeypatch.setattr(
        "app.services.promo_codes."
        "reconcile_employer_subscription",
        fake_employer_reconcile,
    )

    return captured


def test_raw_code_is_never_persisted(
    monkeypatch,
):
    _configure_promo(
        monkeypatch
    )

    admin_id = uuid4()

    raw_code = (
        "SHIPATON-STUDENT-2026"
    )

    with TestingSessionLocal() as db:
        campaign = create_campaign(
            db,
            audience="student",
            code=raw_code,
            admin_user_id=admin_id,
            publish=True,
        )

        db.refresh(campaign)

        assert (
            campaign.code_digest
            != raw_code
        )

        assert (
            raw_code
            not in campaign.code_hint
        )

        assert len(
            campaign.code_digest
        ) == 64

        assert campaign.status == (
            "published"
        )

        assert (
            not hasattr(
                campaign,
                "code",
            )
        )


def test_student_and_employer_codes_are_isolated(
    monkeypatch,
):
    _configure_promo(
        monkeypatch
    )

    student_id = uuid4()
    admin_id = uuid4()

    _create_profile(
        user_id=student_id,
        account_type="intern",
    )

    with TestingSessionLocal() as db:
        create_campaign(
            db,
            audience="student",
            code=(
                "STUDENT-JUDGES-2026"
            ),
            admin_user_id=admin_id,
            publish=True,
        )

        create_campaign(
            db,
            audience="employer",
            code=(
                "EMPLOYER-JUDGES-2026"
            ),
            admin_user_id=admin_id,
            publish=True,
        )

        with pytest.raises(
            PromoCodeInvalid
        ):
            redeem_promo_code(
                db,
                user_id=student_id,
                code=(
                    "EMPLOYER-JUDGES-2026"
                ),
            )


def test_successful_redemption_is_exactly_seven_days_and_one_time(
    monkeypatch,
):
    _configure_promo(
        monkeypatch
    )

    captured = (
        _mock_successful_provider(
            monkeypatch
        )
    )

    user_id = uuid4()
    admin_id = uuid4()

    _create_profile(
        user_id=user_id,
        account_type="intern",
    )

    with TestingSessionLocal() as db:
        first = create_campaign(
            db,
            audience="student",
            code=(
                "STUDENT-FIRST-2026"
            ),
            admin_user_id=admin_id,
            publish=True,
        )

        result = redeem_promo_code(
            db,
            user_id=user_id,
            code="STUDENT-FIRST-2026",
        )

        assert result["outcome"] == (
            "granted"
        )

        assert result["plan"] == (
            "pro_student"
        )

        duration = (
            result["access_expires_at"]
            - result["access_started_at"]
        )

        assert duration == timedelta(
            days=7
        )

        assert (
            captured[
                "entitlement_lookup_key"
            ]
            == "pro_student"
        )

        assert (
            captured["user_id"]
            == user_id
        )

        original_expiry = (
            result["access_expires_at"]
        )

        retire_campaign(
            db,
            campaign_id=first.id,
            admin_user_id=admin_id,
        )

        create_campaign(
            db,
            audience="student",
            code=(
                "STUDENT-SECOND-2026"
            ),
            admin_user_id=admin_id,
            publish=True,
        )

        with pytest.raises(
            PromoCodeAlreadyRedeemed
        ):
            redeem_promo_code(
                db,
                user_id=user_id,
                code=(
                    "STUDENT-SECOND-2026"
                ),
            )

        redemption = (
            PromoCodeRepository
            .get_redemption(
                db,
                user_id=user_id,
                audience="student",
            )
        )

        assert redemption is not None
        assert (
            redemption.status
            == "redeemed"
        )

        stored_expiry = (
            redemption.access_expires_at
        )

        if stored_expiry.tzinfo is None:
            stored_expiry = (
                stored_expiry.replace(
                    tzinfo=timezone.utc
                )
            )

        assert stored_expiry == (
            original_expiry
        )


def test_provider_failure_does_not_consume_one_time_redemption(
    monkeypatch,
):
    _configure_promo(
        monkeypatch
    )

    user_id = uuid4()
    admin_id = uuid4()

    _create_profile(
        user_id=user_id,
        account_type="intern",
    )

    with TestingSessionLocal() as db:
        create_campaign(
            db,
            audience="student",
            code=(
                "STUDENT-RETRY-2026"
            ),
            admin_user_id=admin_id,
            publish=True,
        )

        def fail_grant(
            **_kwargs,
        ):
            raise (
                RevenueCatPromoProviderError(
                    "provider unavailable"
                )
            )

        monkeypatch.setattr(
            "app.services.promo_codes."
            "grant_revenuecat_promotional_entitlement",
            fail_grant,
        )

        with pytest.raises(
            PromoCodeProviderUnavailable
        ):
            redeem_promo_code(
                db,
                user_id=user_id,
                code=(
                    "STUDENT-RETRY-2026"
                ),
            )

        failed = (
            PromoCodeRepository
            .get_redemption(
                db,
                user_id=user_id,
                audience="student",
            )
        )

        assert failed is not None
        assert failed.status == "failed"
        assert (
            failed.access_expires_at
            is None
        )

    _mock_successful_provider(
        monkeypatch
    )

    with TestingSessionLocal() as db:
        result = redeem_promo_code(
            db,
            user_id=user_id,
            code="STUDENT-RETRY-2026",
        )

        assert result["outcome"] == (
            "granted"
        )


def test_retiring_code_never_mutates_existing_redemption(
    monkeypatch,
):
    _configure_promo(
        monkeypatch
    )

    _mock_successful_provider(
        monkeypatch
    )

    user_id = uuid4()
    admin_id = uuid4()

    _create_profile(
        user_id=user_id,
        account_type="employer",
    )

    with TestingSessionLocal() as db:
        campaign = create_campaign(
            db,
            audience="employer",
            code=(
                "EMPLOYER-WEEK-2026"
            ),
            admin_user_id=admin_id,
            publish=True,
        )

        result = redeem_promo_code(
            db,
            user_id=user_id,
            code="EMPLOYER-WEEK-2026",
        )

        expires_before = (
            result["access_expires_at"]
        )

        retire_campaign(
            db,
            campaign_id=campaign.id,
            admin_user_id=admin_id,
        )

        redemption = (
            PromoCodeRepository
            .get_redemption(
                db,
                user_id=user_id,
                audience="employer",
            )
        )

        assert redemption is not None
        assert (
            redemption.status
            == "redeemed"
        )

        expires_after = (
            redemption.access_expires_at
        )

        if expires_after.tzinfo is None:
            expires_after = (
                expires_after.replace(
                    tzinfo=timezone.utc
                )
            )

        assert expires_after == (
            expires_before
        )


def test_admin_api_never_returns_digest_or_raw_code(
    client,
    mock_supabase_auth,
    monkeypatch,
):
    _configure_promo(
        monkeypatch
    )

    admin_id = uuid4()

    monkeypatch.setattr(
        settings,
        "ADMIN_USER_IDS",
        str(admin_id),
    )

    response = client.post(
        "/api/v1/admin/promo-codes",
        headers={
            "Authorization":
                f"Bearer valid-user-{admin_id}",
        },
        json={
            "audience": "student",
            "code": (
                "ADMIN-STUDENT-2026"
            ),
            "publish": True,
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert "code_digest" not in body
    assert "code" not in body
    assert body["audience"] == "student"
    assert body["status"] == "published"
    assert "***" in body["code_hint"]


def test_non_admin_cannot_manage_campaigns(
    client,
    mock_supabase_auth,
    monkeypatch,
):
    _configure_promo(
        monkeypatch
    )

    real_admin_id = uuid4()
    non_admin_id = uuid4()

    monkeypatch.setattr(
        settings,
        "ADMIN_USER_IDS",
        str(real_admin_id),
    )

    response = client.post(
        "/api/v1/admin/promo-codes",
        headers={
            "Authorization":
                f"Bearer valid-user-{non_admin_id}",
        },
        json={
            "audience": "student",
            "code": (
                "BLOCKED-STUDENT-2026"
            ),
            "publish": True,
        },
    )

    assert response.status_code == 403


def test_user_redeem_endpoint_derives_audience_from_backend_profile(
    client,
    mock_supabase_auth,
    monkeypatch,
):
    _configure_promo(
        monkeypatch
    )

    _mock_successful_provider(
        monkeypatch
    )

    user_id = uuid4()
    admin_id = uuid4()

    _create_profile(
        user_id=user_id,
        account_type="employer",
    )

    with TestingSessionLocal() as db:
        create_campaign(
            db,
            audience="employer",
            code=(
                "EMPLOYER-ENDPOINT-2026"
            ),
            admin_user_id=admin_id,
            publish=True,
        )

    response = client.post(
        "/api/v1/promo-codes/redeem",
        headers={
            "Authorization":
                f"Bearer valid-user-{user_id}",
        },
        json={
            "code":
                "EMPLOYER-ENDPOINT-2026",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["audience"] == (
        "employer"
    )

    assert body["plan"] == (
        "employer_pro"
    )


def test_migration_has_no_plaintext_code_column():
    migration = (
        (
            __import__("pathlib")
            .Path(__file__)
            .resolve()
            .parents[1]
            / "database/migrations/"
            "028_promo_campaigns.sql"
        )
        .read_text(
            encoding="utf-8"
        )
    )

    assert "code_digest" in migration
    assert "code_hint" in migration

    assert not re_search_plain_code_column(
        migration
    )

    assert (
        "ENABLE ROW LEVEL SECURITY"
        in migration
    )

    assert (
        "uq_promo_redemptions_user_audience"
        in migration
    )


def re_search_plain_code_column(
    migration: str,
) -> bool:
    import re

    return (
        re.search(
            r"(?mi)^\s*code\s+"
            r"(?:text|varchar|character|char)",
            migration,
        )
        is not None
    )
