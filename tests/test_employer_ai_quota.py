"""Employer AI durable quota lifecycle tests."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.db.models import (
    AIQuotaOperation,
    AIQuotaPeriod,
)
from app.services.ai_quota import (
    AIQuotaExceededError,
    AIQuotaIdempotencyConflictError,
)
from app.services.employer_ai_quota import (
    EMPLOYER_CANDIDATE_INSIGHT,
    EMPLOYER_INTERVIEW_KIT,
    release_employer_ai_quota_operation,
    reserve_employer_ai_quota,
    settle_employer_ai_quota_operation,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.conftest import test_engine


def _free_subscription(db, user_id):
    return {
        "plan": "free",
        "is_active": False,
    }


def _configure_free(monkeypatch, *, limit="2"):
    monkeypatch.setenv(
        "INTERNMATCH_EMPLOYER_FREE_"
        "CANDIDATE_INSIGHT_LIMIT",
        limit,
    )
    monkeypatch.setenv(
        "INTERNMATCH_EMPLOYER_FREE_AI_WINDOW_DAYS",
        "30",
    )
    monkeypatch.setattr(
        (
            "app.services.employer_ai_quota."
            "get_employer_subscription_snapshot"
        ),
        _free_subscription,
    )


def _configure_pro(monkeypatch, *, limit="5"):
    now = datetime.now(timezone.utc)

    monkeypatch.setenv(
        "INTERNMATCH_EMPLOYER_PRO_"
        "INTERVIEW_KIT_LIMIT",
        limit,
    )

    monkeypatch.setattr(
        (
            "app.services.employer_ai_quota."
            "get_employer_subscription_snapshot"
        ),
        lambda db, user_id: {
            "plan": "employer_pro",
            "is_active": True,
        },
    )

    monkeypatch.setattr(
        (
            "app.services.employer_ai_quota."
            "SubscriptionRepository.get_entitlement"
        ),
        lambda db, user_id, entitlement_id: (
            SimpleNamespace(
                current_period_started_at=(
                    now - timedelta(days=1)
                ),
                expires_at=(
                    now + timedelta(days=29)
                ),
            )
        ),
    )


def test_free_candidate_insight_reserve_settle(
    monkeypatch,
):
    _configure_free(monkeypatch)

    user_id = uuid4()

    with Session(test_engine) as db:
        reservation = reserve_employer_ai_quota(
            db,
            user_id=user_id,
            feature_key=EMPLOYER_CANDIDATE_INSIGHT,
            idempotency_key="request-1",
            request_fingerprint="fingerprint-1",
        )

        operation_id = reservation[
            "operation"
        ].id

        assert (
            reservation["period"].plan_key
            == "free"
        )
        assert (
            reservation["period"].reserved_count
            == 1
        )

        settle_employer_ai_quota_operation(
            db,
            operation_id=operation_id,
        )

        period = db.scalar(
            select(AIQuotaPeriod).where(
                AIQuotaPeriod.user_id == user_id,
                AIQuotaPeriod.feature_key
                == EMPLOYER_CANDIDATE_INSIGHT,
            )
        )

        assert period is not None
        assert period.used_count == 1
        assert period.reserved_count == 0


def test_failed_operation_releases_capacity(
    monkeypatch,
):
    _configure_free(
        monkeypatch,
        limit="1",
    )

    user_id = uuid4()

    with Session(test_engine) as db:
        reservation = reserve_employer_ai_quota(
            db,
            user_id=user_id,
            feature_key=EMPLOYER_CANDIDATE_INSIGHT,
            idempotency_key="request-release",
            request_fingerprint="fingerprint",
        )

        operation_id = reservation[
            "operation"
        ].id

        release_employer_ai_quota_operation(
            db,
            operation_id=operation_id,
            reason="provider_failure",
        )

        period = db.scalar(
            select(AIQuotaPeriod).where(
                AIQuotaPeriod.user_id == user_id,
                AIQuotaPeriod.feature_key
                == EMPLOYER_CANDIDATE_INSIGHT,
            )
        )

        operation = db.get(
            AIQuotaOperation,
            operation_id,
        )

        assert period is not None
        assert period.used_count == 0
        assert period.reserved_count == 0
        assert operation is not None
        assert operation.status == "released"


def test_duplicate_request_does_not_double_reserve(
    monkeypatch,
):
    _configure_free(monkeypatch)

    user_id = uuid4()

    with Session(test_engine) as db:
        first = reserve_employer_ai_quota(
            db,
            user_id=user_id,
            feature_key=EMPLOYER_CANDIDATE_INSIGHT,
            idempotency_key="same-key",
            request_fingerprint="same-fingerprint",
        )

        second = reserve_employer_ai_quota(
            db,
            user_id=user_id,
            feature_key=EMPLOYER_CANDIDATE_INSIGHT,
            idempotency_key="same-key",
            request_fingerprint="same-fingerprint",
        )

        assert (
            first["operation"].id
            == second["operation"].id
        )
        assert (
            second["period"].reserved_count
            == 1
        )


def test_same_key_different_payload_conflicts(
    monkeypatch,
):
    _configure_free(monkeypatch)

    user_id = uuid4()

    with Session(test_engine) as db:
        reserve_employer_ai_quota(
            db,
            user_id=user_id,
            feature_key=EMPLOYER_CANDIDATE_INSIGHT,
            idempotency_key="same-key",
            request_fingerprint="first",
        )

        with pytest.raises(
            AIQuotaIdempotencyConflictError
        ):
            reserve_employer_ai_quota(
                db,
                user_id=user_id,
                feature_key=EMPLOYER_CANDIDATE_INSIGHT,
                idempotency_key="same-key",
                request_fingerprint="different",
            )


def test_free_limit_counts_reserved_capacity(
    monkeypatch,
):
    _configure_free(
        monkeypatch,
        limit="1",
    )

    user_id = uuid4()

    with Session(test_engine) as db:
        reserve_employer_ai_quota(
            db,
            user_id=user_id,
            feature_key=EMPLOYER_CANDIDATE_INSIGHT,
            idempotency_key="first",
            request_fingerprint="one",
        )

        with pytest.raises(
            AIQuotaExceededError
        ):
            reserve_employer_ai_quota(
                db,
                user_id=user_id,
                feature_key=EMPLOYER_CANDIDATE_INSIGHT,
                idempotency_key="second",
                request_fingerprint="two",
            )


def test_employer_pro_uses_revenuecat_billing_period(
    monkeypatch,
):
    _configure_pro(monkeypatch)

    user_id = uuid4()

    with Session(test_engine) as db:
        reservation = reserve_employer_ai_quota(
            db,
            user_id=user_id,
            feature_key=EMPLOYER_INTERVIEW_KIT,
            idempotency_key="pro-request",
            request_fingerprint="pro-fingerprint",
        )

        period = reservation["period"]

        assert period.plan_key == "employer_pro"
        assert reservation["limit"] == 5
        assert period.reserved_count == 1


def test_quota_migration_contains_employer_keys():
    migration = (
        __import__("pathlib")
        .Path(
            "database/migrations/"
            "026_expand_ai_quota_for_employer.sql"
        )
        .read_text(
            encoding="utf-8"
        )
    )

    assert "employer_candidate_insight" in migration
    assert "employer_interview_kit" in migration
    assert "employer_shortlist_comparison" in migration
    assert "employer_internship_description" in migration
    assert "'employer_pro'" in migration
