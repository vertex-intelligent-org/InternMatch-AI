"""RQ task for user-facing transactional notification emails."""

from uuid import UUID

from app.db.session import SessionLocal
from app.services.notification_user_email_delivery import (
    deliver_user_notification_email,
)


def run_user_notification_email_delivery(
    notification_id: str,
):
    normalized_id = UUID(
        notification_id
    )

    db = SessionLocal()

    try:
        result = (
            deliver_user_notification_email(
                db,
                notification_id=normalized_id,
            )
        )

        return {
            "notification_id":
                notification_id,
            "attempted":
                result.attempted,
            "sent":
                result.sent,
        }
    finally:
        db.close()
