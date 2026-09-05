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
