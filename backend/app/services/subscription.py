"""Backend-authoritative subscription snapshot service."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.subscription import SubscriptionRepository

PRO_STUDENT_ENTITLEMENT_ID = "pro_student"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_student_subscription_snapshot(
    db: Session,
    *,
    user_id: UUID,
) -> dict[str, Any]:
    """Return backend-authoritative Student Free/Pro subscription state."""

    entitlement = SubscriptionRepository.get_entitlement(
        db,
        user_id=user_id,
        entitlement_id=PRO_STUDENT_ENTITLEMENT_ID,
    )

    if entitlement is None:
        return {
            "plan": "free",
            "entitlement_id": PRO_STUDENT_ENTITLEMENT_ID,
            "is_active": False,
            "status": "free",
            "will_renew": False,
            "expires_at": None,
            "product_id": None,
            "environment": None,
            "store": None,
            "last_event_type": None,
        }

    now = datetime.now(timezone.utc)
    expires_at = _as_utc(entitlement.expires_at)

    active = bool(entitlement.is_active)
    if expires_at is not None and expires_at <= now:
        active = False

    status = entitlement.status
    if not active and expires_at is not None and expires_at <= now:
        status = "expired"

    return {
        "plan": "pro_student" if active else "free",
        "entitlement_id": entitlement.entitlement_id,
        "is_active": active,
        "status": status,
        "will_renew": bool(entitlement.will_renew) if active else False,
        "expires_at": expires_at,
        "product_id": entitlement.product_id,
        "environment": entitlement.environment,
        "store": entitlement.store,
        "last_event_type": entitlement.last_event_type,
    }
