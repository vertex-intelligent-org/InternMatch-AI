"""RQ task that creates candidate alerts for a newly published opportunity."""

from uuid import UUID

from app.db.session import SessionLocal
from app.services.opportunity_alerts import (
    create_new_opportunity_alerts,
)


def run_new_opportunity_alert_fanout(
    internship_id: str,
):
    normalized_id = UUID(
        internship_id
    )

    db = SessionLocal()

    try:
        ensured = (
            create_new_opportunity_alerts(
                db,
                internship_id=normalized_id,
            )
        )

        db.commit()

        return {
            "internship_id": internship_id,
            "alerts_ensured": ensured,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
