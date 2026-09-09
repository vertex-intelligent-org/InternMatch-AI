"""SUB-1 backend-authoritative RevenueCat subscription tests."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.core.config import settings
from app.db.models import RevenueCatWebhookEvent
from sqlalchemy import func, select

from tests.db import TestingSessionLocal


@pytest.fixture(autouse=True)
def configure_revenuecat_webhook_security():
    original_auth = settings.REVENUECAT_WEBHOOK_AUTH_TOKEN
    original_signing = settings.REVENUECAT_WEBHOOK_SIGNING_SECRET

    settings.REVENUECAT_WEBHOOK_AUTH_TOKEN = "unit-test-webhook-token"
    settings.REVENUECAT_WEBHOOK_SIGNING_SECRET = "unit-test-signing-secret"

    yield

    settings.REVENUECAT_WEBHOOK_AUTH_TOKEN = original_auth
    settings.REVENUECAT_WEBHOOK_SIGNING_SECRET = original_signing


def _raw_payload(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _signed_headers(raw_body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.".encode("utf-8") + raw_body
    signature = hmac.new(
        settings.REVENUECAT_WEBHOOK_SIGNING_SECRET.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    return {
        "Authorization": f"Bearer {settings.REVENUECAT_WEBHOOK_AUTH_TOKEN}",
        "X-RevenueCat-Webhook-Signature": f"t={timestamp},v1={signature}",
        "Content-Type": "application/json",
    }


def _event_payload(
    *,
    user_id,
    event_id: str,
    event_type: str,
    event_timestamp_ms: int,
    expiration_at_ms: int,
    cancel_reason: str | None = None,
    expiration_reason: str | None = None,
) -> dict:
    event = {
        "id": event_id,
        "type": event_type,
        "event_timestamp_ms": event_timestamp_ms,
        "app_user_id": str(user_id),
        "original_app_user_id": str(user_id),
        "aliases": [str(user_id)],
        "entitlement_id": "pro_student",
        "entitlement_ids": ["pro_student"],
        "product_id": "internmatch_pro_student_monthly",
        "purchased_at_ms": event_timestamp_ms - 1_000,
        "expiration_at_ms": expiration_at_ms,
        "environment": "SANDBOX",
        "store": "TEST_STORE",
        "original_transaction_id": f"original-{user_id}",
    }

    if cancel_reason is not None:
        event["cancel_reason"] = cancel_reason

    if expiration_reason is not None:
        event["expiration_reason"] = expiration_reason

    return {"api_version": "1.0", "event": event}


def _post_webhook(client, payload: dict):
    raw_body = _raw_payload(payload)
    return client.post(
        "/api/v1/webhooks/revenuecat",
        content=raw_body,
        headers=_signed_headers(raw_body),
    )


def _auth_headers(user_id) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-user-{user_id}"}


def test_subscription_defaults_to_free(
    client,
    mock_supabase_auth,
):
    user_id = uuid4()

    response = client.get(
        "/api/v1/me/subscription",
        headers=_auth_headers(user_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "free"
    assert body["entitlement_id"] == "pro_student"
    assert body["is_active"] is False
    assert body["status"] == "free"
    assert body["will_renew"] is False


def test_webhook_rejects_invalid_authorization(client):
    payload = {"api_version": "1.0", "event": {}}
    raw_body = _raw_payload(payload)

    response = client.post(
        "/api/v1/webhooks/revenuecat",
        content=raw_body,
        headers={
            "Authorization": "Bearer wrong-token",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 401


def test_webhook_rejects_invalid_hmac_signature(client):
    payload = {"api_version": "1.0", "event": {}}
    raw_body = _raw_payload(payload)
    timestamp = str(int(time.time()))

    response = client.post(
        "/api/v1/webhooks/revenuecat",
        content=raw_body,
        headers={
            "Authorization": f"Bearer {settings.REVENUECAT_WEBHOOK_AUTH_TOKEN}",
            "X-RevenueCat-Webhook-Signature": f"t={timestamp},v1={'0' * 64}",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 401


def test_initial_purchase_creates_backend_pro_entitlement(
    client,
    mock_supabase_auth,
):
    user_id = uuid4()
    now_ms = int(time.time() * 1000)
    expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp() * 1000
    )

    payload = _event_payload(
        user_id=user_id,
        event_id=f"initial-{uuid4()}",
        event_type="INITIAL_PURCHASE",
        event_timestamp_ms=now_ms,
        expiration_at_ms=expiry_ms,
    )

    webhook_response = _post_webhook(client, payload)
    assert webhook_response.status_code == 200
    assert webhook_response.json()["outcome"] == "processed"

    response = client.get(
        "/api/v1/me/subscription",
        headers=_auth_headers(user_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "pro_student"
    assert body["is_active"] is True
    assert body["status"] == "active"
    assert body["will_renew"] is True
    assert body["product_id"] == "internmatch_pro_student_monthly"


def test_duplicate_revenuecat_event_is_idempotent(client):
    user_id = uuid4()
    now_ms = int(time.time() * 1000)
    expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp() * 1000
    )
    event_id = f"duplicate-{uuid4()}"

    payload = _event_payload(
        user_id=user_id,
        event_id=event_id,
        event_type="INITIAL_PURCHASE",
        event_timestamp_ms=now_ms,
        expiration_at_ms=expiry_ms,
    )

    first = _post_webhook(client, payload)
    second = _post_webhook(client, payload)

    assert first.status_code == 200
    assert first.json()["outcome"] == "processed"
    assert second.status_code == 200
    assert second.json()["outcome"] == "duplicate"

    with TestingSessionLocal() as db:
        count = db.scalar(
            select(func.count())
            .select_from(RevenueCatWebhookEvent)
            .where(RevenueCatWebhookEvent.event_id == event_id)
        )

    assert count == 1


def test_cancellation_keeps_pro_until_expiration(
    client,
    mock_supabase_auth,
):
    user_id = uuid4()
    now_ms = int(time.time() * 1000)
    expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp() * 1000
    )

    initial = _event_payload(
        user_id=user_id,
        event_id=f"initial-{uuid4()}",
        event_type="INITIAL_PURCHASE",
        event_timestamp_ms=now_ms,
        expiration_at_ms=expiry_ms,
    )
    cancellation = _event_payload(
        user_id=user_id,
        event_id=f"cancel-{uuid4()}",
        event_type="CANCELLATION",
        event_timestamp_ms=now_ms + 1,
        expiration_at_ms=expiry_ms,
        cancel_reason="UNSUBSCRIBE",
    )

    assert _post_webhook(client, initial).status_code == 200
    cancel_response = _post_webhook(client, cancellation)

    assert cancel_response.status_code == 200
    assert cancel_response.json()["outcome"] == "processed"

    response = client.get(
        "/api/v1/me/subscription",
        headers=_auth_headers(user_id),
    )

    body = response.json()
    assert body["plan"] == "pro_student"
    assert body["is_active"] is True
    assert body["status"] == "cancelled"
    assert body["will_renew"] is False


def test_expiration_revokes_pro_access(
    client,
    mock_supabase_auth,
):
    user_id = uuid4()
    now_ms = int(time.time() * 1000)
    future_expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp() * 1000
    )
    expired_ms = int(
        (datetime.now(timezone.utc) - timedelta(seconds=1)).timestamp() * 1000
    )

    initial = _event_payload(
        user_id=user_id,
        event_id=f"initial-{uuid4()}",
        event_type="INITIAL_PURCHASE",
        event_timestamp_ms=now_ms,
        expiration_at_ms=future_expiry_ms,
    )
    expiration = _event_payload(
        user_id=user_id,
        event_id=f"expiry-{uuid4()}",
        event_type="EXPIRATION",
        event_timestamp_ms=now_ms + 2,
        expiration_at_ms=expired_ms,
        expiration_reason="UNSUBSCRIBE",
    )

    assert _post_webhook(client, initial).status_code == 200
    expire_response = _post_webhook(client, expiration)

    assert expire_response.status_code == 200
    assert expire_response.json()["outcome"] == "processed"

    response = client.get(
        "/api/v1/me/subscription",
        headers=_auth_headers(user_id),
    )

    body = response.json()
    assert body["plan"] == "free"
    assert body["is_active"] is False
    assert body["status"] == "expired"
    assert body["will_renew"] is False


def test_older_event_cannot_override_newer_entitlement_state(
    client,
    mock_supabase_auth,
):
    user_id = uuid4()
    now_ms = int(time.time() * 1000)
    expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp() * 1000
    )
    already_expired_ms = int(
        (datetime.now(timezone.utc) - timedelta(days=1)).timestamp() * 1000
    )

    renewal = _event_payload(
        user_id=user_id,
        event_id=f"renewal-{uuid4()}",
        event_type="RENEWAL",
        event_timestamp_ms=now_ms + 100,
        expiration_at_ms=expiry_ms,
    )
    stale_expiration = _event_payload(
        user_id=user_id,
        event_id=f"stale-expiry-{uuid4()}",
        event_type="EXPIRATION",
        event_timestamp_ms=now_ms,
        expiration_at_ms=already_expired_ms,
        expiration_reason="UNSUBSCRIBE",
    )

    assert _post_webhook(client, renewal).status_code == 200

    stale_response = _post_webhook(client, stale_expiration)

    assert stale_response.status_code == 200
    assert stale_response.json()["outcome"] == "ignored_stale"

    response = client.get(
        "/api/v1/me/subscription",
        headers=_auth_headers(user_id),
    )

    body = response.json()
    assert body["plan"] == "pro_student"
    assert body["is_active"] is True
    assert body["status"] == "active"


def _revenuecat_v2_subscription(
    *,
    user_id,
    gives_access: bool,
    status: str,
    auto_renewal_status: str,
    ends_at_ms: int,
) -> dict:
    internal_product_id = "prod_test_student_monthly"

    return {
        "object": "subscription",
        "id": f"sub-{user_id}",
        "customer_id": str(user_id),
        "original_customer_id": str(user_id),
        "product_id": internal_product_id,
        "starts_at": ends_at_ms - 60_000,
        "current_period_starts_at": ends_at_ms - 60_000,
        "current_period_ends_at": ends_at_ms,
        "ends_at": ends_at_ms,
        "gives_access": gives_access,
        "pending_payment": False,
        "auto_renewal_status": auto_renewal_status,
        "status": status,
        "entitlements": {
            "object": "list",
            "items": [
                {
                    "state": "active",
                    "object": "entitlement",
                    "id": "entl-test-pro-student",
                    "lookup_key": "pro_student",
                    "display_name": "Pro Student",
                    "products": {
                        "object": "list",
                        "items": [
                            {
                                "state": "active",
                                "object": "product",
                                "id": internal_product_id,
                                "store_identifier": (
                                    "internmatch_pro_student_monthly"
                                ),
                                "type": "subscription",
                            }
                        ],
                        "next_page": None,
                        "url": "/test/products",
                    },
                }
            ],
            "next_page": None,
            "url": "/test/entitlements",
        },
        "environment": "sandbox",
        "store": "test_store",
    }


def _active_pro_student_entitlement(
    *,
    expires_at_ms: int,
) -> dict:
    return {
        "object": "customer.active_entitlement",
        "entitlement_id": "entl-test-pro-student",
        "expires_at": expires_at_ms,
    }


def test_revenuecat_v2_requests_are_environment_scoped(
    monkeypatch,
):
    from app.services import revenuecat_reconciliation

    user_id = uuid4()
    requested_urls = []

    monkeypatch.setattr(
        settings,
        "REVENUECAT_PROJECT_ID",
        "proj_test",
    )
    monkeypatch.setattr(
        settings,
        "REVENUECAT_SECRET_KEY",
        "sk_test",
    )
    monkeypatch.setattr(
        settings,
        "REVENUECAT_ENVIRONMENT",
        "sandbox",
    )

    def fake_request_json(*, url, api_key):
        requested_urls.append(url)

        if "/subscriptions" in url:
            return {
                "object": "list",
                "items": [],
                "next_page": None,
            }

        raise AssertionError(
            "active_entitlements should not be fetched "
            "without a Test Store subscription."
        )

    monkeypatch.setattr(
        revenuecat_reconciliation,
        "_request_json",
        fake_request_json,
    )

    subscriptions, active_entitlements, _ = (
        revenuecat_reconciliation._fetch_revenuecat_subscriptions(
            user_id=user_id,
        )
    )

    assert subscriptions == []
    assert active_entitlements == []
    assert len(requested_urls) == 1
    assert (
        requested_urls[0].endswith(
            "/subscriptions?environment=sandbox"
        )
    )


def test_reconciliation_rejects_invalid_environment(
    client,
    mock_supabase_auth,
    monkeypatch,
):
    from app.services import revenuecat_reconciliation

    user_id = uuid4()

    monkeypatch.setattr(
        settings,
        "REVENUECAT_PROJECT_ID",
        "proj_test",
    )
    monkeypatch.setattr(
        settings,
        "REVENUECAT_SECRET_KEY",
        "sk_test",
    )
    monkeypatch.setattr(
        settings,
        "REVENUECAT_ENVIRONMENT",
        "invalid",
    )
    monkeypatch.setattr(
        revenuecat_reconciliation,
        "RECONCILIATION_MIN_INTERVAL_SECONDS",
        0,
    )

    response = client.post(
        "/api/v1/me/subscription/reconcile",
        headers=_auth_headers(user_id),
    )

    assert response.status_code == 503


def test_reconciliation_requires_v2_server_configuration(
    client,
    mock_supabase_auth,
    monkeypatch,
):
    from app.services import revenuecat_reconciliation

    user_id = uuid4()

    monkeypatch.setattr(settings, "REVENUECAT_PROJECT_ID", "")
    monkeypatch.setattr(settings, "REVENUECAT_SECRET_KEY", "")
    monkeypatch.setattr(
        settings,
        "REVENUECAT_ENVIRONMENT",
        "sandbox",
    )

    monkeypatch.setattr(
        revenuecat_reconciliation,
        "RECONCILIATION_MIN_INTERVAL_SECONDS",
        0,
    )

    response = client.post(
        "/api/v1/me/subscription/reconcile",
        headers=_auth_headers(user_id),
    )

    assert response.status_code == 503


def test_reconciliation_recovers_lost_purchase(
    client,
    mock_supabase_auth,
    monkeypatch,
):
    from app.services import revenuecat_reconciliation

    user_id = uuid4()
    now_ms = int(time.time() * 1000)
    future_expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp() * 1000
    )

    subscription = _revenuecat_v2_subscription(
        user_id=user_id,
        gives_access=True,
        status="active",
        auto_renewal_status="will_renew",
        ends_at_ms=future_expiry_ms,
    )

    monkeypatch.setattr(
        revenuecat_reconciliation,
        "_fetch_revenuecat_subscriptions",
        lambda *, user_id: (
            [subscription],
            [
                _active_pro_student_entitlement(
                    expires_at_ms=future_expiry_ms,
                )
            ],
            now_ms,
        ),
    )

    response = client.post(
        "/api/v1/me/subscription/reconcile",
        headers=_auth_headers(user_id),
    )

    assert response.status_code == 200
    body = response.json()

    assert body["outcome"] == "reconciled"
    assert body["subscription"]["plan"] == "pro_student"
    assert body["subscription"]["is_active"] is True
    assert body["subscription"]["status"] == "active"
    assert body["subscription"]["will_renew"] is True
    assert (
        body["subscription"]["product_id"]
        == "internmatch_pro_student_monthly"
    )
    assert body["subscription"]["environment"] == "SANDBOX"
    assert body["subscription"]["store"] == "TEST_STORE"


def test_reconciliation_revokes_stale_pro_state(
    client,
    mock_supabase_auth,
    monkeypatch,
):
    from app.services import revenuecat_reconciliation

    user_id = uuid4()
    now_ms = int(time.time() * 1000)

    future_expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp() * 1000
    )

    initial = _event_payload(
        user_id=user_id,
        event_id=f"initial-{uuid4()}",
        event_type="INITIAL_PURCHASE",
        event_timestamp_ms=now_ms,
        expiration_at_ms=future_expiry_ms,
    )

    assert _post_webhook(client, initial).status_code == 200

    expired_ms = int(
        (datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp() * 1000
    )

    subscription = _revenuecat_v2_subscription(
        user_id=user_id,
        gives_access=True,
        status="active",
        auto_renewal_status="will_not_renew",
        ends_at_ms=expired_ms,
    )

    monkeypatch.setattr(
        revenuecat_reconciliation,
        "_fetch_revenuecat_subscriptions",
        lambda *, user_id: (
            [subscription],
            [],
            now_ms + 10_000,
        ),
    )

    with TestingSessionLocal() as db:
        result = revenuecat_reconciliation.reconcile_student_subscription(
            db,
            user_id=user_id,
            min_interval_seconds=0,
        )

    assert result["outcome"] == "reconciled"
    assert result["subscription"]["plan"] == "free"
    assert result["subscription"]["is_active"] is False
    assert result["subscription"]["status"] == "expired"
    assert result["subscription"]["will_renew"] is False


def test_webhook_older_than_reconciliation_snapshot_is_ignored(
    client,
    mock_supabase_auth,
    monkeypatch,
):
    from app.services import revenuecat_reconciliation

    user_id = uuid4()
    now_ms = int(time.time() * 1000)
    reconciliation_ms = now_ms + 20_000

    expired_ms = int(
        (datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp() * 1000
    )

    subscription = _revenuecat_v2_subscription(
        user_id=user_id,
        gives_access=False,
        status="expired",
        auto_renewal_status="will_not_renew",
        ends_at_ms=expired_ms,
    )

    monkeypatch.setattr(
        revenuecat_reconciliation,
        "_fetch_revenuecat_subscriptions",
        lambda *, user_id: (
            [subscription],
            [],
            reconciliation_ms,
        ),
    )

    with TestingSessionLocal() as db:
        revenuecat_reconciliation.reconcile_student_subscription(
            db,
            user_id=user_id,
            min_interval_seconds=0,
        )

    delayed_renewal_expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp() * 1000
    )

    delayed_renewal = _event_payload(
        user_id=user_id,
        event_id=f"delayed-renewal-{uuid4()}",
        event_type="RENEWAL",
        event_timestamp_ms=reconciliation_ms - 1,
        expiration_at_ms=delayed_renewal_expiry_ms,
    )

    response = _post_webhook(client, delayed_renewal)

    assert response.status_code == 200
    assert response.json()["outcome"] == "ignored_stale"

    subscription_state = client.get(
        "/api/v1/me/subscription",
        headers=_auth_headers(user_id),
    ).json()

    assert subscription_state["plan"] == "free"
    assert subscription_state["is_active"] is False


def test_reconciliation_is_throttled_when_state_is_recent(
    client,
    mock_supabase_auth,
    monkeypatch,
):
    from app.services import revenuecat_reconciliation

    user_id = uuid4()
    now_ms = int(time.time() * 1000)
    future_expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp() * 1000
    )

    subscription = _revenuecat_v2_subscription(
        user_id=user_id,
        gives_access=True,
        status="active",
        auto_renewal_status="will_renew",
        ends_at_ms=future_expiry_ms,
    )

    calls = {"count": 0}

    def fake_fetch(*, user_id):
        calls["count"] += 1
        return (
            [subscription],
            [
                _active_pro_student_entitlement(
                    expires_at_ms=future_expiry_ms,
                )
            ],
            now_ms,
        )

    monkeypatch.setattr(
        revenuecat_reconciliation,
        "_fetch_revenuecat_subscriptions",
        fake_fetch,
    )

    first = client.post(
        "/api/v1/me/subscription/reconcile",
        headers=_auth_headers(user_id),
    )
    second = client.post(
        "/api/v1/me/subscription/reconcile",
        headers=_auth_headers(user_id),
    )

    assert first.status_code == 200
    assert first.json()["outcome"] == "reconciled"

    assert second.status_code == 200
    assert second.json()["outcome"] == "skipped_recent"

    assert calls["count"] == 1

def test_active_entitlement_does_not_override_provider_denial(
    client,
    mock_supabase_auth,
    monkeypatch,
):
    from app.services import revenuecat_reconciliation

    user_id = uuid4()
    now_ms = int(time.time() * 1000)
    future_expiry_ms = int(
        (
            datetime.now(timezone.utc)
            + timedelta(days=30)
        ).timestamp()
        * 1000
    )

    subscription = _revenuecat_v2_subscription(
        user_id=user_id,
        gives_access=False,
        status="in_billing_retry",
        auto_renewal_status="will_renew",
        ends_at_ms=future_expiry_ms,
    )

    monkeypatch.setattr(
        revenuecat_reconciliation,
        "_fetch_revenuecat_subscriptions",
        lambda *, user_id: (
            [subscription],
            [
                _active_pro_student_entitlement(
                    expires_at_ms=future_expiry_ms,
                )
            ],
            now_ms,
        ),
    )

    response = client.post(
        "/api/v1/me/subscription/reconcile",
        headers=_auth_headers(user_id),
    )

    assert response.status_code == 200

    body = response.json()["subscription"]

    assert body["plan"] == "free"
    assert body["is_active"] is False
    assert body["status"] == "billing_issue"

# -----------------------------------------------------------------------------
# Employer Pro billing authority
# -----------------------------------------------------------------------------


def _as_employer_event(payload: dict) -> dict:
    """Convert a fresh Student RevenueCat webhook fixture to Employer Pro."""

    event = payload["event"]
    event["entitlement_id"] = "pro_employer"
    event["entitlement_ids"] = ["pro_employer"]
    event["product_id"] = "internmatch_pro_employer_monthly:monthly-v2"
    return payload


def _as_employer_revenuecat_fixture(value):
    """Convert existing Student RevenueCat v2 fixtures to Employer equivalents."""

    if isinstance(value, dict):
        return {
            key: _as_employer_revenuecat_fixture(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _as_employer_revenuecat_fixture(item)
            for item in value
        ]

    if isinstance(value, str):
        return (
            value
            .replace(
                "internmatch_pro_student_monthly",
                "internmatch_pro_employer_monthly:monthly-v2",
            )
            .replace("pro_student", "pro_employer")
            .replace("pro-student", "pro-employer")
        )

    return value


def test_employer_subscription_defaults_to_free():
    from app.services.subscription import get_employer_subscription_snapshot

    user_id = uuid4()

    with TestingSessionLocal() as db:
        body = get_employer_subscription_snapshot(
            db,
            user_id=user_id,
        )

    assert body["plan"] == "free"
    assert body["entitlement_id"] == "pro_employer"
    assert body["is_active"] is False
    assert body["status"] == "free"
    assert body["will_renew"] is False


def test_employer_initial_purchase_creates_backend_pro_entitlement(client):
    from app.services.subscription import get_employer_subscription_snapshot

    user_id = uuid4()
    now_ms = int(time.time() * 1000)
    expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
        * 1000
    )

    payload = _as_employer_event(
        _event_payload(
            user_id=user_id,
            event_id=f"employer-initial-{uuid4()}",
            event_type="INITIAL_PURCHASE",
            event_timestamp_ms=now_ms,
            expiration_at_ms=expiry_ms,
        )
    )

    response = _post_webhook(client, payload)

    assert response.status_code == 200
    assert response.json()["outcome"] == "processed"

    with TestingSessionLocal() as db:
        body = get_employer_subscription_snapshot(
            db,
            user_id=user_id,
        )

    assert body["plan"] == "employer_pro"
    assert body["entitlement_id"] == "pro_employer"
    assert body["is_active"] is True
    assert body["status"] == "active"
    assert body["will_renew"] is True
    assert (
        body["product_id"]
        == "internmatch_pro_employer_monthly:monthly-v2"
    )


def test_employer_cancellation_keeps_access_until_expiration(client):
    from app.services.subscription import get_employer_subscription_snapshot

    user_id = uuid4()
    now_ms = int(time.time() * 1000)
    expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
        * 1000
    )

    initial = _as_employer_event(
        _event_payload(
            user_id=user_id,
            event_id=f"employer-initial-{uuid4()}",
            event_type="INITIAL_PURCHASE",
            event_timestamp_ms=now_ms,
            expiration_at_ms=expiry_ms,
        )
    )

    cancellation = _as_employer_event(
        _event_payload(
            user_id=user_id,
            event_id=f"employer-cancel-{uuid4()}",
            event_type="CANCELLATION",
            event_timestamp_ms=now_ms + 1,
            expiration_at_ms=expiry_ms,
            cancel_reason="UNSUBSCRIBE",
        )
    )

    assert _post_webhook(client, initial).status_code == 200

    cancel_response = _post_webhook(client, cancellation)

    assert cancel_response.status_code == 200
    assert cancel_response.json()["outcome"] == "processed"

    with TestingSessionLocal() as db:
        body = get_employer_subscription_snapshot(
            db,
            user_id=user_id,
        )

    assert body["plan"] == "employer_pro"
    assert body["is_active"] is True
    assert body["status"] == "cancelled"
    assert body["will_renew"] is False


def test_employer_expiration_revokes_pro_access(client):
    from app.services.subscription import get_employer_subscription_snapshot

    user_id = uuid4()
    now_ms = int(time.time() * 1000)

    future_expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
        * 1000
    )
    expired_ms = int(
        (datetime.now(timezone.utc) - timedelta(seconds=1)).timestamp()
        * 1000
    )

    initial = _as_employer_event(
        _event_payload(
            user_id=user_id,
            event_id=f"employer-initial-{uuid4()}",
            event_type="INITIAL_PURCHASE",
            event_timestamp_ms=now_ms,
            expiration_at_ms=future_expiry_ms,
        )
    )

    expiration = _as_employer_event(
        _event_payload(
            user_id=user_id,
            event_id=f"employer-expiry-{uuid4()}",
            event_type="EXPIRATION",
            event_timestamp_ms=now_ms + 2,
            expiration_at_ms=expired_ms,
            expiration_reason="UNSUBSCRIBE",
        )
    )

    assert _post_webhook(client, initial).status_code == 200

    expire_response = _post_webhook(client, expiration)

    assert expire_response.status_code == 200
    assert expire_response.json()["outcome"] == "processed"

    with TestingSessionLocal() as db:
        body = get_employer_subscription_snapshot(
            db,
            user_id=user_id,
        )

    assert body["plan"] == "free"
    assert body["entitlement_id"] == "pro_employer"
    assert body["is_active"] is False
    assert body["status"] == "expired"
    assert body["will_renew"] is False


def test_employer_reconciliation_recovers_lost_purchase(monkeypatch):
    from app.services import revenuecat_reconciliation

    user_id = uuid4()
    now_ms = int(time.time() * 1000)
    future_expiry_ms = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
        * 1000
    )

    student_subscription = _revenuecat_v2_subscription(
        user_id=user_id,
        gives_access=True,
        status="active",
        auto_renewal_status="will_renew",
        ends_at_ms=future_expiry_ms,
    )
    employer_subscription = _as_employer_revenuecat_fixture(
        student_subscription
    )

    student_active_entitlement = _active_pro_student_entitlement(
        expires_at_ms=future_expiry_ms,
    )
    employer_active_entitlement = _as_employer_revenuecat_fixture(
        student_active_entitlement
    )

    monkeypatch.setattr(
        revenuecat_reconciliation,
        "_fetch_revenuecat_subscriptions",
        lambda *, user_id: (
            [employer_subscription],
            [employer_active_entitlement],
            now_ms,
        ),
    )

    with TestingSessionLocal() as db:
        result = revenuecat_reconciliation.reconcile_employer_subscription(
            db,
            user_id=user_id,
            min_interval_seconds=0,
        )

    assert result["outcome"] == "reconciled"

    body = result["subscription"]

    assert body["plan"] == "employer_pro"
    assert body["entitlement_id"] == "pro_employer"
    assert body["is_active"] is True
    assert body["status"] == "active"
    assert body["will_renew"] is True
    assert (
        body["product_id"]
        == "internmatch_pro_employer_monthly:monthly-v2"
    )
