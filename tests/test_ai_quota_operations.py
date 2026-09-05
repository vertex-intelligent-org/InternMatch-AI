"""SUB-3 atomic AI quota reservation lifecycle tests."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.db.models import (
    AIQuotaOperation,
    AIQuotaPeriod,
    SubscriptionEntitlement,
)
from app.services.ai_quota import (
    FEATURE_CV_ANALYSIS,
    FEATURE_MATCH_EXPLANATION,
    AIQuotaExceededError,
    AIQuotaIdempotencyConflictError,
    get_ai_usage_snapshot,
    release_ai_quota_operation,
    reserve_ai_quota,
    settle_ai_quota_operation,
)

from tests.db import TestingSessionLocal


@pytest.fixture(autouse=True)
def clean_quota_operation_state():
    db = TestingSessionLocal()

    try:
        db.query(AIQuotaOperation).delete()
        db.query(AIQuotaPeriod).delete()
        db.query(SubscriptionEntitlement).delete()
        db.commit()
    finally:
        db.close()

    yield

    db = TestingSessionLocal()

    try:
        db.query(AIQuotaOperation).delete()
        db.query(AIQuotaPeriod).delete()
        db.query(SubscriptionEntitlement).delete()
        db.commit()
    finally:
        db.close()


def _feature(snapshot, feature_key):
    return next(
        item
        for item in snapshot["features"]
        if item["feature_key"] == feature_key
    )


def test_free_reservation_creates_period_and_reduces_remaining():
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        result = reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="request-1",
            request_fingerprint="context-a",
        )
        db.commit()

        assert result["outcome"] == "reserved"
        assert result["operation"].status == "reserved"

        period = db.query(AIQuotaPeriod).one()

        assert period.plan_key == "free"
        assert period.used_count == 0
        assert period.reserved_count == 1

        snapshot = get_ai_usage_snapshot(
            db,
            user_id=user_id,
        )

        feature = _feature(
            snapshot,
            FEATURE_MATCH_EXPLANATION,
        )

        assert feature["limit"] == 5
        assert feature["used"] == 0
        assert feature["remaining"] == 4
    finally:
        db.close()


def test_successful_settlement_moves_reserved_to_used():
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        reservation = reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="settle-1",
        )
        operation_id = reservation["operation"].id
        db.commit()

        result = settle_ai_quota_operation(
            db,
            operation_id=operation_id,
        )
        db.commit()

        assert result["outcome"] == "settled"

        period = db.query(AIQuotaPeriod).one()

        assert period.reserved_count == 0
        assert period.used_count == 1

        operation = db.query(AIQuotaOperation).one()

        assert operation.status == "settled"
        assert operation.settled_at is not None
    finally:
        db.close()


def test_failed_operation_release_returns_capacity():
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        reservation = reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="release-1",
        )
        operation_id = reservation["operation"].id
        db.commit()

        result = release_ai_quota_operation(
            db,
            operation_id=operation_id,
            reason="provider_failure",
        )
        db.commit()

        assert result["outcome"] == "released"

        period = db.query(AIQuotaPeriod).one()

        assert period.reserved_count == 0
        assert period.used_count == 0

        operation = db.query(AIQuotaOperation).one()

        assert operation.status == "released"
        assert operation.release_reason == "provider_failure"
    finally:
        db.close()


def test_duplicate_reserved_request_does_not_double_reserve():
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        first = reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="duplicate-1",
            request_fingerprint="same-request",
        )
        db.commit()

        second = reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="duplicate-1",
            request_fingerprint="same-request",
        )
        db.commit()

        assert first["outcome"] == "reserved"
        assert second["outcome"] == "duplicate_reserved"
        assert (
            first["operation"].id
            == second["operation"].id
        )

        period = db.query(AIQuotaPeriod).one()

        assert period.reserved_count == 1
        assert db.query(AIQuotaOperation).count() == 1
    finally:
        db.close()


def test_duplicate_settlement_is_idempotent():
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        reservation = reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="settle-repeat",
        )
        operation_id = reservation["operation"].id
        db.commit()

        first = settle_ai_quota_operation(
            db,
            operation_id=operation_id,
        )
        db.commit()

        second = settle_ai_quota_operation(
            db,
            operation_id=operation_id,
        )
        db.commit()

        assert first["outcome"] == "settled"
        assert second["outcome"] == "already_settled"

        period = db.query(AIQuotaPeriod).one()

        assert period.used_count == 1
        assert period.reserved_count == 0
    finally:
        db.close()


def test_duplicate_release_is_idempotent():
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        reservation = reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="release-repeat",
        )
        operation_id = reservation["operation"].id
        db.commit()

        first = release_ai_quota_operation(
            db,
            operation_id=operation_id,
        )
        db.commit()

        second = release_ai_quota_operation(
            db,
            operation_id=operation_id,
        )
        db.commit()

        assert first["outcome"] == "released"
        assert second["outcome"] == "already_released"

        period = db.query(AIQuotaPeriod).one()

        assert period.used_count == 0
        assert period.reserved_count == 0
    finally:
        db.close()


def test_released_operation_can_be_safely_re_reserved():
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        first = reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="retry-after-failure",
            request_fingerprint="same-request",
        )
        operation_id = first["operation"].id
        db.commit()

        release_ai_quota_operation(
            db,
            operation_id=operation_id,
            reason="gemini_failure",
        )
        db.commit()

        retry = reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="retry-after-failure",
            request_fingerprint="same-request",
        )
        db.commit()

        assert retry["outcome"] == "re_reserved"
        assert retry["operation"].id == operation_id

        period = db.query(AIQuotaPeriod).one()

        assert period.used_count == 0
        assert period.reserved_count == 1
    finally:
        db.close()


def test_same_idempotency_key_with_different_request_is_rejected():
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="same-key",
            request_fingerprint="request-a",
        )
        db.commit()

        with pytest.raises(
            AIQuotaIdempotencyConflictError
        ):
            reserve_ai_quota(
                db,
                user_id=user_id,
                feature_key=FEATURE_MATCH_EXPLANATION,
                idempotency_key="same-key",
                request_fingerprint="request-b",
            )

        db.rollback()

        period = db.query(AIQuotaPeriod).one()

        assert period.reserved_count == 1
        assert db.query(AIQuotaOperation).count() == 1
    finally:
        db.close()


def test_free_quota_limit_blocks_first_request_over_limit():
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        for index in range(5):
            reserve_ai_quota(
                db,
                user_id=user_id,
                feature_key=FEATURE_MATCH_EXPLANATION,
                idempotency_key=f"limit-{index}",
            )

        db.commit()

        with pytest.raises(AIQuotaExceededError) as exc_info:
            reserve_ai_quota(
                db,
                user_id=user_id,
                feature_key=FEATURE_MATCH_EXPLANATION,
                idempotency_key="limit-over",
            )

        db.rollback()

        exc = exc_info.value

        assert exc.feature_key == FEATURE_MATCH_EXPLANATION
        assert exc.plan == "free"
        assert exc.limit == 5
        assert exc.used == 0
        assert exc.reserved == 5
        assert exc.remaining == 0
    finally:
        db.close()


def test_pro_reservation_uses_revenuecat_billing_period():
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    period_start = now - timedelta(days=3)
    period_end = now + timedelta(days=27)

    db = TestingSessionLocal()

    try:
        db.add(
            SubscriptionEntitlement(
                user_id=user_id,
                entitlement_id="pro_student",
                status="active",
                is_active=True,
                will_renew=True,
                current_period_started_at=period_start,
                expires_at=period_end,
            )
        )
        db.commit()

        reservation = reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_CV_ANALYSIS,
            idempotency_key="pro-cv-1",
        )
        db.commit()

        assert reservation["limit"] == 10

        quota_period = db.query(AIQuotaPeriod).one()

        assert quota_period.plan_key == "pro_student"

        assert abs(
            (
                quota_period.period_start.replace(
                    tzinfo=timezone.utc
                )
                - period_start
            ).total_seconds()
        ) < 1

        assert abs(
            (
                quota_period.period_end.replace(
                    tzinfo=timezone.utc
                )
                - period_end
            ).total_seconds()
        ) < 1
    finally:
        db.close()


def test_old_operation_settlement_cannot_consume_new_period():
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        first = reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="old-period",
        )
        old_operation_id = first["operation"].id
        db.commit()

        period = db.query(AIQuotaPeriod).one()

        period.period_start = (
            datetime.now(timezone.utc)
            - timedelta(days=8)
        )
        period.period_end = (
            datetime.now(timezone.utc)
            - timedelta(days=1)
        )
        period.used_count = 0
        period.reserved_count = 1
        db.commit()

        reserve_ai_quota(
            db,
            user_id=user_id,
            feature_key=FEATURE_MATCH_EXPLANATION,
            idempotency_key="new-period",
        )
        db.commit()

        new_period = db.query(AIQuotaPeriod).one()

        assert new_period.reserved_count == 1
        assert new_period.used_count == 0

        result = settle_ai_quota_operation(
            db,
            operation_id=old_operation_id,
        )
        db.commit()

        assert result["outcome"] == "settled"

        refreshed = db.query(AIQuotaPeriod).one()

        # Old in-flight work belongs to the previous quota window and must
        # not alter the new current period.
        assert refreshed.reserved_count == 1
        assert refreshed.used_count == 0
    finally:
        db.close()
