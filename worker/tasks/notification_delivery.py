
"""RQ task for Expo push notification delivery."""

from uuid import UUID

from app.db.session import SessionLocal
from app.services.notification_delivery import (
    deliver_notification,
)


def run_notification_delivery(
    notification_id: str,
):
    normalized_id = UUID(
        notification_id
    )

    db = SessionLocal()

    try:
        result = deliver_notification(
            db,
            notification_id=normalized_id,
        )

        db.commit()

        return {
            "notification_id":
                notification_id,
            "attempted":
                result.attempted,
            "accepted":
                result.accepted,
            "disabled":
                result.disabled,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
