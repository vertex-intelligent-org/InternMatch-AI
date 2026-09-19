"""Candidate engagement notifications for newly published opportunities."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    InternshipListing,
    StudentProfile,
)
from app.repositories.notification import (
    NotificationRepository,
)

NEW_OPPORTUNITY_ALERT_PREFERENCE = (
    "new_opportunity_alerts_enabled"
)


def _candidate_opted_in(
    preferences: dict[str, Any] | None,
) -> bool:
    """
    Fail closed for promotional opportunity alerts.

    Missing preference means the user has not explicitly opted in.
    Employer accounts never receive candidate opportunity alerts.
    """
    if not isinstance(preferences, dict):
        return False

    if (
        preferences.get(
            NEW_OPPORTUNITY_ALERT_PREFERENCE
        )
        is not True
    ):
        return False

    account_type = str(
        preferences.get(
            "account_type",
            "intern",
        )
        or "intern"
    ).strip().lower()

    return account_type != "employer"


def create_new_opportunity_alerts(
    db: Session,
    *,
    internship_id: UUID,
) -> int:
    """
    Ensure one durable alert per opted-in candidate for a published listing.

    The deterministic dedupe key prevents duplicate alerts for the same
    candidate/listing pair. Email delivery is intentionally not enabled for
    this engagement event.
    """
    listing = db.get(
        InternshipListing,
        internship_id,
    )

    if (
        listing is None
        or listing.publication_status
        != "published"
    ):
        return 0

    recipients = db.execute(
        select(
            StudentProfile.user_id,
            StudentProfile.preferences,
        ).order_by(
            StudentProfile.user_id.asc()
        )
    ).all()

    ensured = 0

    for user_id, preferences in recipients:
        if (
            listing.employer_user_id is not None
            and user_id
            == listing.employer_user_id
        ):
            continue

        if not _candidate_opted_in(
            preferences
        ):
            continue

        NotificationRepository.create(
            db,
            recipient_user_id=user_id,
            event_type=(
                "new_opportunity_published"
            ),
            entity_type="internship",
            entity_id=listing.id,
            data={
                "internship_id": str(
                    listing.id
                ),
                "company": listing.company,
                "title": listing.title,
                "location": listing.location,
                "work_type": listing.work_type,
            },
            dedupe_key=(
                f"internship:{listing.id}:"
                "new-opportunity:"
                f"user:{user_id}"
            ),
        )

        ensured += 1

    return ensured
