"""RevenueCat webhook authentication, idempotency, and entitlement state updates."""

import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import RevenueCatWebhookEvent, SubscriptionEntitlement
from app.repositories.subscription import SubscriptionRepository
from app.services.subscription import PRO_STUDENT_ENTITLEMENT_ID

SUPPORTED_STATE_EVENTS = {
    "INITIAL_PURCHASE",
    "RENEWAL",
    "CANCELLATION",
    "UNCANCELLATION",
    "BILLING_ISSUE",
    "SUBSCRIPTION_PAUSED",
    "EXPIRATION",
}


class RevenueCatWebhookConfigurationError(RuntimeError):
    """Webhook security is not configured server-side."""


class RevenueCatWebhookAuthenticationError(ValueError):
    """Webhook request could not be authenticated."""


def verify_revenuecat_webhook_request(
    *,
    raw_body: bytes,
    authorization: str | None,
    signature_header: str | None,
    tolerance_seconds: int = 300,
) -> None:
    """
    Verify RevenueCat Authorization and, when configured, HMAC signature.

    HMAC is calculated over the raw request bytes exactly as received.
    """

    auth_token = (settings.REVENUECAT_WEBHOOK_AUTH_TOKEN or "").strip()
    if not auth_token:
        raise RevenueCatWebhookConfigurationError(
            "RevenueCat webhook authorization is not configured."
        )

    expected_authorization = f"Bearer {auth_token}"
    if not authorization or not hmac.compare_digest(
        authorization.strip(),
        expected_authorization,
    ):
        raise RevenueCatWebhookAuthenticationError(
            "Invalid RevenueCat webhook authorization."
        )

    signing_secret = (
        settings.REVENUECAT_WEBHOOK_SIGNING_SECRET or ""
    ).strip()

    # Authorization is mandatory. HMAC becomes mandatory when a signing
    # secret has been configured for the RevenueCat webhook integration.
    if not signing_secret:
        return

    if not signature_header:
        raise RevenueCatWebhookAuthenticationError(
            "Missing RevenueCat webhook signature."
        )

    try:
        parts: dict[str, str] = {}
        for item in signature_header.split(","):
            key, value = item.strip().split("=", 1)
            parts[key] = value

        timestamp = parts["t"]
        expected_signature = parts["v1"]
        timestamp_int = int(timestamp)
    except (KeyError, ValueError):
        raise RevenueCatWebhookAuthenticationError(
            "Malformed RevenueCat webhook signature."
        ) from None

    signed_payload = f"{timestamp}.".encode("utf-8") + raw_body
    computed_signature = hmac.new(
        signing_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_signature, expected_signature):
        raise RevenueCatWebhookAuthenticationError(
            "Invalid RevenueCat webhook signature."
        )

    if abs(time.time() - timestamp_int) > tolerance_seconds:
        raise RevenueCatWebhookAuthenticationError(
            "RevenueCat webhook signature timestamp is outside tolerance."
        )


def _milliseconds_to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return None

    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)


def _future_access(expiration: datetime | None) -> bool:
    if expiration is None:
        return False
    return expiration > datetime.now(timezone.utc)


def _parse_uuid(value: Any) -> UUID | None:
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return UUID(value.strip())
    except ValueError:
        return None


def _resolve_internal_user_id(event: dict[str, Any]) -> UUID | None:
    """
    Resolve the application's Supabase UUID from RevenueCat identity fields.

    Current App User ID wins when it is a UUID. Otherwise use the original
    ID / aliases only when they resolve unambiguously to one UUID.
    """

    current_user_id = _parse_uuid(event.get("app_user_id"))
    if current_user_id is not None:
        return current_user_id

    candidates: set[UUID] = set()

    original_user_id = _parse_uuid(event.get("original_app_user_id"))
    if original_user_id is not None:
        candidates.add(original_user_id)

    aliases = event.get("aliases")
    if isinstance(aliases, list):
        for alias in aliases:
            parsed = _parse_uuid(alias)
            if parsed is not None:
                candidates.add(parsed)

    if len(candidates) == 1:
        return next(iter(candidates))

    return None


def _contains_pro_student_entitlement(event: dict[str, Any]) -> bool:
    entitlement_ids = event.get("entitlement_ids")

    if isinstance(entitlement_ids, list):
        if PRO_STUDENT_ENTITLEMENT_ID in entitlement_ids:
            return True

    # Backward-compatible fallback for RevenueCat's deprecated singular field.
    return event.get("entitlement_id") == PRO_STUDENT_ENTITLEMENT_ID


def _update_common_fields(
    entitlement: SubscriptionEntitlement,
    event: dict[str, Any],
) -> None:
    product_id = event.get("product_id")
    if isinstance(product_id, str) and product_id:
        entitlement.product_id = product_id

    environment = event.get("environment")
    if isinstance(environment, str):
        entitlement.environment = environment

    store = event.get("store")
    if isinstance(store, str):
        entitlement.store = store

    original_transaction_id = event.get("original_transaction_id")
    if isinstance(original_transaction_id, str):
        entitlement.original_transaction_id = original_transaction_id

    purchased_at = _milliseconds_to_datetime(event.get("purchased_at_ms"))
    if purchased_at is not None:
        entitlement.current_period_started_at = purchased_at

    expiration = _milliseconds_to_datetime(event.get("expiration_at_ms"))
    if expiration is not None:
        entitlement.expires_at = expiration


def _apply_state_event(
    entitlement: SubscriptionEntitlement,
    *,
    event: dict[str, Any],
    event_type: str,
    event_id: str,
    event_timestamp_ms: int,
) -> None:
    _update_common_fields(entitlement, event)

    expiration = _milliseconds_to_datetime(event.get("expiration_at_ms"))

    if event_type in {"INITIAL_PURCHASE", "RENEWAL", "UNCANCELLATION"}:
        entitlement.status = "active"
        entitlement.is_active = _future_access(expiration)
        entitlement.will_renew = True
        entitlement.cancellation_reason = None
        entitlement.expiration_reason = None

    elif event_type == "CANCELLATION":
        # Cancellation disables renewal but does NOT revoke paid access
        # before the already-paid subscription period expires.
        entitlement.status = "cancelled"
        entitlement.is_active = _future_access(expiration)
        entitlement.will_renew = False

        reason = event.get("cancel_reason")
        entitlement.cancellation_reason = (
            reason if isinstance(reason, str) else None
        )

    elif event_type == "BILLING_ISSUE":
        # Access may continue through a configured grace period.
        grace_expiration = _milliseconds_to_datetime(
            event.get("grace_period_expiration_at_ms")
        )
        access_until = grace_expiration or expiration

        if access_until is not None:
            entitlement.expires_at = access_until

        entitlement.status = "billing_issue"
        entitlement.is_active = _future_access(access_until)
        entitlement.will_renew = True

    elif event_type == "SUBSCRIPTION_PAUSED":
        # RevenueCat explicitly says not to revoke until EXPIRATION.
        entitlement.status = "paused"
        entitlement.is_active = _future_access(expiration)
        entitlement.will_renew = False

    elif event_type == "EXPIRATION":
        entitlement.status = "expired"
        entitlement.is_active = False
        entitlement.will_renew = False

        reason = event.get("expiration_reason")
        entitlement.expiration_reason = (
            reason if isinstance(reason, str) else None
        )

    entitlement.last_event_id = event_id
    entitlement.last_event_type = event_type
    entitlement.last_event_timestamp_ms = event_timestamp_ms


def process_revenuecat_webhook(
    db: Session,
    *,
    payload: dict[str, Any],
) -> dict[str, str]:
    """
    Persist one RevenueCat event exactly once and update pro_student state.

    Unknown/unrelated events are acknowledged and recorded without mutating
    entitlement authority.
    """

    event = payload.get("event")
    if not isinstance(event, dict):
        raise ValueError("RevenueCat payload is missing event object.")

    event_id = event.get("id")
    event_type = event.get("type")
    event_timestamp_raw = event.get("event_timestamp_ms")

    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("RevenueCat event id is missing.")

    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("RevenueCat event type is missing.")

    try:
        event_timestamp_ms = int(event_timestamp_raw)
    except (TypeError, ValueError):
        raise ValueError("RevenueCat event timestamp is invalid.") from None

    event_id = event_id.strip()
    event_type = event_type.strip().upper()

    existing_event = SubscriptionRepository.get_webhook_event(
        db,
        event_id=event_id,
    )
    if existing_event is not None:
        return {
            "status": "ok",
            "event_id": event_id,
            "event_type": event_type,
            "outcome": "duplicate",
        }

    ledger_event = RevenueCatWebhookEvent(
        event_id=event_id,
        event_type=event_type,
        event_timestamp_ms=event_timestamp_ms,
        outcome="received",
    )
    db.add(ledger_event)

    # Flush early so concurrent delivery of the same RevenueCat event ID
    # is protected by the database primary key.
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {
            "status": "ok",
            "event_id": event_id,
            "event_type": event_type,
            "outcome": "duplicate",
        }

    now = datetime.now(timezone.utc)

    if event_type == "TEST":
        ledger_event.outcome = "ignored_test"
        ledger_event.processed_at = now
        db.commit()
        return {
            "status": "ok",
            "event_id": event_id,
            "event_type": event_type,
            "outcome": ledger_event.outcome,
        }

    if not _contains_pro_student_entitlement(event):
        ledger_event.outcome = "ignored_entitlement"
        ledger_event.processed_at = now
        db.commit()
        return {
            "status": "ok",
            "event_id": event_id,
            "event_type": event_type,
            "outcome": ledger_event.outcome,
        }

    if event_type not in SUPPORTED_STATE_EVENTS:
        ledger_event.outcome = "ignored_event_type"
        ledger_event.processed_at = now
        db.commit()
        return {
            "status": "ok",
            "event_id": event_id,
            "event_type": event_type,
            "outcome": ledger_event.outcome,
        }

    user_id = _resolve_internal_user_id(event)
    if user_id is None:
        ledger_event.outcome = "ignored_identity"
        ledger_event.processed_at = now
        db.commit()
        return {
            "status": "ok",
            "event_id": event_id,
            "event_type": event_type,
            "outcome": ledger_event.outcome,
        }

    ledger_event.user_id = user_id

    entitlement = SubscriptionRepository.get_entitlement(
        db,
        user_id=user_id,
        entitlement_id=PRO_STUDENT_ENTITLEMENT_ID,
    )

    if (
        entitlement is not None
        and entitlement.last_event_timestamp_ms is not None
        and event_timestamp_ms <= entitlement.last_event_timestamp_ms
    ):
        ledger_event.outcome = "ignored_stale"
        ledger_event.processed_at = now
        db.commit()
        return {
            "status": "ok",
            "event_id": event_id,
            "event_type": event_type,
            "outcome": ledger_event.outcome,
        }

    if entitlement is None:
        entitlement = SubscriptionEntitlement(
            user_id=user_id,
            entitlement_id=PRO_STUDENT_ENTITLEMENT_ID,
        )
        db.add(entitlement)

    _apply_state_event(
        entitlement,
        event=event,
        event_type=event_type,
        event_id=event_id,
        event_timestamp_ms=event_timestamp_ms,
    )

    ledger_event.outcome = "processed"
    ledger_event.processed_at = now

    db.commit()

    return {
        "status": "ok",
        "event_id": event_id,
        "event_type": event_type,
        "outcome": ledger_event.outcome,
    }
