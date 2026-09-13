"""Deterministic Employer hiring-pipeline analytics.

This is a current-state operational snapshot. It does not use AI and does not
infer candidate quality, hiring suitability, or historical funnel transitions.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Application, InternshipListing


class EmployerPipelineAnalyticsResponse(BaseModel):
    """Current employer-owned listing/application pipeline snapshot."""

    model_config = ConfigDict(extra="forbid")

    analytics_scope: Literal[
        "current_pipeline_snapshot"
    ] = "current_pipeline_snapshot"

    total_listings: int
    draft_listings: int
    under_review_listings: int
    published_listings: int
    closed_listings: int

    total_submitted_applications: int
    applied: int
    interviewing: int
    accepted: int
    rejected: int

    interviewing_share_percent: float
    decision_share_percent: float
    acceptance_share_among_decisions_percent: float | None


def _percentage(
    numerator: int,
    denominator: int,
) -> float:
    if denominator <= 0:
        return 0.0

    return round(
        numerator * 100.0 / denominator,
        1,
    )


def get_employer_pipeline_analytics(
    db: Session,
    *,
    employer_user_id: UUID,
) -> EmployerPipelineAnalyticsResponse:
    """Return tenant-scoped deterministic current pipeline counts."""

    listing_stmt = (
        select(
            InternshipListing.publication_status,
            func.count(InternshipListing.id),
        )
        .where(
            InternshipListing.employer_user_id
            == employer_user_id
        )
        .group_by(
            InternshipListing.publication_status
        )
    )

    listing_rows = db.execute(
        listing_stmt
    ).all()

    listing_counts = {
        "draft": 0,
        "under_review": 0,
        "published": 0,
        "closed": 0,
    }

    for publication_status, count in listing_rows:
        if publication_status in listing_counts:
            listing_counts[publication_status] = int(
                count or 0
            )

    application_stmt = (
        select(
            Application.status,
            func.count(Application.id),
        )
        .join(
            InternshipListing,
            Application.internship_id
            == InternshipListing.id,
        )
        .where(
            InternshipListing.employer_user_id
            == employer_user_id,
            Application.status != "saved",
        )
        .group_by(
            Application.status
        )
    )

    application_rows = db.execute(
        application_stmt
    ).all()

    application_counts = {
        "applied": 0,
        "interviewing": 0,
        "accepted": 0,
        "rejected": 0,
    }

    for application_status, count in application_rows:
        if application_status in application_counts:
            application_counts[application_status] = int(
                count or 0
            )

    total_listings = sum(
        listing_counts.values()
    )

    total_submitted = sum(
        application_counts.values()
    )

    decisions = (
        application_counts["accepted"]
        + application_counts["rejected"]
    )

    acceptance_share = (
        _percentage(
            application_counts["accepted"],
            decisions,
        )
        if decisions > 0
        else None
    )

    return EmployerPipelineAnalyticsResponse(
        total_listings=total_listings,
        draft_listings=listing_counts["draft"],
        under_review_listings=(
            listing_counts["under_review"]
        ),
        published_listings=(
            listing_counts["published"]
        ),
        closed_listings=listing_counts["closed"],
        total_submitted_applications=(
            total_submitted
        ),
        applied=application_counts["applied"],
        interviewing=(
            application_counts["interviewing"]
        ),
        accepted=application_counts["accepted"],
        rejected=application_counts["rejected"],
        interviewing_share_percent=(
            _percentage(
                application_counts["interviewing"],
                total_submitted,
            )
        ),
        decision_share_percent=(
            _percentage(
                decisions,
                total_submitted,
            )
        ),
        acceptance_share_among_decisions_percent=(
            acceptance_share
        ),
    )
