"""Persistence helpers for server-authoritative subscription state."""

from uuid import UUID

from app.db.models import RevenueCatWebhookEvent, SubscriptionEntitlement
from sqlalchemy import select
from sqlalchemy.orm import Session


class SubscriptionRepository:
    """SQLAlchemy repository for RevenueCat subscription state."""

    @staticmethod
    def get_entitlement(
        db: Session,
        *,
        user_id: UUID,
        entitlement_id: str,
    ) -> SubscriptionEntitlement | None:
        stmt = select(SubscriptionEntitlement).where(
            SubscriptionEntitlement.user_id == user_id,
            SubscriptionEntitlement.entitlement_id == entitlement_id,
        )
        return db.scalar(stmt)

    @staticmethod
    def get_webhook_event(
        db: Session,
        *,
        event_id: str,
    ) -> RevenueCatWebhookEvent | None:
        stmt = select(RevenueCatWebhookEvent).where(
            RevenueCatWebhookEvent.event_id == event_id
        )
        return db.scalar(stmt)
