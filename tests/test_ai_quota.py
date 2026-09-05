"""SUB-2 backend-controlled Student AI quota policy coverage."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.db.models import AIQuotaPeriod, SubscriptionEntitlement
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from tests.db import TestingSessionLocal

pytestmark = pytest.mark.usefixtures("mock_supabase_auth")


@pytest.fixture(autouse=True)
def clean_ai_quota_state():
    db = TestingSessionLocal()

    try:
        db.query(AIQuotaPeriod).delete()
        db.query(SubscriptionEntitlement).delete()
        db.commit()
    finally:
        db.close()

    yield

    db = TestingSessionLocal()

    try:
        db.query(AIQuotaPeriod).delete()
        db.query(SubscriptionEntitlement).delete()
        db.commit()
    finally:
        db.close()


def _auth_headers(user_id):
    return {
        "Authorization": f"Bearer valid-user-{user_id}",
    }


def _feature(body, feature_key):
    return next(
        item
        for item in body["features"]
        if item["feature_key"] == feature_key
    )


def _parse_datetime(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def test_ai_usage_requires_authentication(
    client: TestClient,
):
    response = client.get("/api/v1/me/ai-usage")

    assert response.status_code == 401


def test_free_plan_returns_backend_controlled_feature_limits(
    client: TestClient,
):
    user_id = uuid4()
    before = datetime.now(timezone.utc)

    response = client.get(
        "/api/v1/me/ai-usage",
        headers=_auth_headers(user_id),
    )

    after = datetime.now(timezone.utc)

    assert response.status_code == 200

    body = response.json()

    assert body["plan"] == "free"
    assert [
        feature["feature_key"]
        for feature in body["features"]
    ] == [
        "cv_analysis",
        "match_explanation",
        "application_support",
        "interview_prep",
    ]

    expected = {
        "cv_analysis": (1, "30_days", 30),
        "match_explanation": (5, "7_days", 7),
        "application_support": (3, "7_days", 7),
        "interview_prep": (2, "7_days", 7),
    }

    for feature_key, (
        limit,
        reset_policy,
        window_days,
    ) in expected.items():
        feature = _feature(body, feature_key)

        assert feature["limit"] == limit
        assert feature["used"] == 0
        assert feature["remaining"] == limit
        assert feature["reset_policy"] == reset_policy

        reset_at = _parse_datetime(
            feature["reset_at"]
        )

        assert (
            before + timedelta(days=window_days)
            <= reset_at
            <= after + timedelta(days=window_days)
        )


def test_free_usage_reads_existing_period_and_reserved_capacity(
    client: TestClient,
):
    user_id = uuid4()

    period_start = (
        datetime.now(timezone.utc)
        - timedelta(days=1)
    )
    period_end = (
        datetime.now(timezone.utc)
        + timedelta(days=6)
    )

    db = TestingSessionLocal()

    try:
        db.add(
            AIQuotaPeriod(
                user_id=user_id,
                feature_key="match_explanation",
                plan_key="free",
                period_start=period_start,
                period_end=period_end,
                used_count=3,
                reserved_count=1,
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/api/v1/me/ai-usage",
        headers=_auth_headers(user_id),
    )

    assert response.status_code == 200

    feature = _feature(
        response.json(),
        "match_explanation",
    )

    assert feature["limit"] == 5
    assert feature["used"] == 3

    # 5 total - 3 settled - 1 in-flight reservation.
    assert feature["remaining"] == 1
    assert feature["reset_policy"] == "7_days"

    assert abs(
        (
            _parse_datetime(feature["reset_at"])
            - period_end
        ).total_seconds()
    ) < 1


def test_pro_plan_uses_revenuecat_billing_period_and_pro_limits(
    client: TestClient,
):
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    period_start = now - timedelta(days=5)
    period_end = now + timedelta(days=25)

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
                product_id="internmatch_pro_student_monthly",
                environment="SANDBOX",
                store="TEST_STORE",
            )
        )

        db.add(
            AIQuotaPeriod(
                user_id=user_id,
                feature_key="application_support",
                plan_key="pro_student",
                period_start=period_start,
                period_end=period_end,
                used_count=7,
                reserved_count=2,
            )
        )

        db.commit()
    finally:
        db.close()

    response = client.get(
        "/api/v1/me/ai-usage",
        headers=_auth_headers(user_id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["plan"] == "pro_student"

    assert _feature(
        body,
        "cv_analysis",
    )["limit"] == 10

    assert _feature(
        body,
        "match_explanation",
    )["limit"] == 100

    application_support = _feature(
        body,
        "application_support",
    )

    assert application_support["limit"] == 50
    assert application_support["used"] == 7
    assert application_support["remaining"] == 41
    assert (
        application_support["reset_policy"]
        == "billing_period"
    )

    assert _feature(
        body,
        "interview_prep",
    )["limit"] == 20

    assert abs(
        (
            _parse_datetime(
                application_support["reset_at"]
            )
            - period_end
        ).total_seconds()
    ) < 1


def test_expired_pro_entitlement_falls_back_to_free_policy(
    client: TestClient,
):
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    db = TestingSessionLocal()

    try:
        db.add(
            SubscriptionEntitlement(
                user_id=user_id,
                entitlement_id="pro_student",
                status="expired",
                is_active=False,
                will_renew=False,
                current_period_started_at=(
                    now - timedelta(days=31)
                ),
                expires_at=(
                    now - timedelta(days=1)
                ),
                product_id="internmatch_pro_student_monthly",
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/api/v1/me/ai-usage",
        headers=_auth_headers(user_id),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["plan"] == "free"
    assert _feature(
        body,
        "cv_analysis",
    )["limit"] == 1
    assert _feature(
        body,
        "match_explanation",
    )["limit"] == 5


def test_malformed_active_pro_period_fails_closed(
    client: TestClient,
):
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    db = TestingSessionLocal()

    try:
        db.add(
            SubscriptionEntitlement(
                user_id=user_id,
                entitlement_id="pro_student",
                status="active",
                is_active=True,
                will_renew=True,
                current_period_started_at=None,
                expires_at=now + timedelta(days=20),
            )
        )
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/api/v1/me/ai-usage",
        headers=_auth_headers(user_id),
    )

    assert response.status_code == 503
    assert (
        response.json()["detail"]
        == "AI usage policy is temporarily unavailable."
    )


def test_ai_usage_read_does_not_create_quota_rows(
    client: TestClient,
):
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        before = db.query(AIQuotaPeriod).count()
    finally:
        db.close()

    assert before == 0

    response = client.get(
        "/api/v1/me/ai-usage",
        headers=_auth_headers(user_id),
    )

    assert response.status_code == 200

    db = TestingSessionLocal()

    try:
        after = db.query(AIQuotaPeriod).count()
    finally:
        db.close()

    assert after == 0


def test_quota_state_allows_only_one_current_row_per_user_feature():
    user_id = uuid4()
    now = datetime.now(timezone.utc)

    db = TestingSessionLocal()

    try:
        db.add(
            AIQuotaPeriod(
                user_id=user_id,
                feature_key="match_explanation",
                plan_key="free",
                period_start=now,
                period_end=now + timedelta(days=7),
                used_count=1,
                reserved_count=0,
            )
        )
        db.commit()

        # A different plan/period must update the same authoritative
        # feature state in SUB-3, not create a parallel quota window.
        db.add(
            AIQuotaPeriod(
                user_id=user_id,
                feature_key="match_explanation",
                plan_key="pro_student",
                period_start=now + timedelta(seconds=1),
                period_end=now + timedelta(days=30),
                used_count=0,
                reserved_count=0,
            )
        )

        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()
    finally:
        db.close()
