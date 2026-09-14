"""Backend-authoritative Employer Free/Pro product policy.

This module determines feature and listing access from the existing Employer
subscription entitlement. Employer AI usage quotas remain a separate durable
policy enforced by the Employer AI quota service.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.repositories.internship import InternshipRepository
from app.services.subscription import (
    get_employer_subscription_snapshot,
)

FEATURE_CANDIDATE_INSIGHT = "candidate_insight"
FEATURE_INTERVIEW_KIT = "interview_kit"
FEATURE_SHORTLIST_COMPARISON = "shortlist_comparison"
FEATURE_INTERNSHIP_DESCRIPTION = "internship_description"
FEATURE_PIPELINE_ANALYTICS = "pipeline_analytics"


EMPLOYER_FEATURE_ORDER = (
    FEATURE_CANDIDATE_INSIGHT,
    FEATURE_INTERVIEW_KIT,
    FEATURE_SHORTLIST_COMPARISON,
    FEATURE_INTERNSHIP_DESCRIPTION,
    FEATURE_PIPELINE_ANALYTICS,
)


class EmployerListingLimitError(RuntimeError):
    """Employer plan has no capacity for another published listing."""

    def __init__(
        self,
        *,
        plan: str,
        limit: int,
        published_count: int,
    ) -> None:
        super().__init__(
            "Employer plan active-listing limit reached."
        )
        self.plan = plan
        self.limit = limit
        self.published_count = published_count


class EmployerFeatureAccessError(RuntimeError):
    """Requested Employer feature is unavailable on the current plan."""

    def __init__(
        self,
        *,
        feature_key: str,
        plan: str,
    ) -> None:
        super().__init__(
            f"Employer feature '{feature_key}' "
            f"is unavailable on plan '{plan}'."
        )
        self.feature_key = feature_key
        self.plan = plan


class EmployerProductPolicyResponse(BaseModel):
    """Employer product capabilities derived from backend subscription state."""

    model_config = ConfigDict(extra="forbid")

    plan: Literal["free", "employer_pro"]
    is_pro: bool
    active_listing_limit: int | None
    candidate_insight_available: bool
    interview_kit_available: bool
    shortlist_comparison_available: bool
    internship_description_available: bool
    pipeline_analytics_available: bool


def get_employer_product_policy(
    db: Session,
    *,
    user_id: UUID,
) -> EmployerProductPolicyResponse:
    """Return deterministic Employer Free/Pro product capabilities."""

    subscription = get_employer_subscription_snapshot(
        db,
        user_id=user_id,
    )

    is_pro = (
        subscription["plan"] == "employer_pro"
        and bool(subscription["is_active"])
    )

    return EmployerProductPolicyResponse(
        plan=(
            "employer_pro"
            if is_pro
            else "free"
        ),
        is_pro=is_pro,
        # Free product contract: one published internship.
        # Pro product contract: multiple published internships.
        active_listing_limit=(
            None
            if is_pro
            else 1
        ),
        # Free includes limited AI candidate insights.
        # Durable usage quota enforcement is implemented separately.
        candidate_insight_available=True,
        interview_kit_available=is_pro,
        shortlist_comparison_available=is_pro,
        internship_description_available=is_pro,
        pipeline_analytics_available=is_pro,
    )


def require_employer_listing_capacity(
    db: Session,
    *,
    user_id: UUID,
    exclude_internship_id: UUID | None = None,
) -> EmployerProductPolicyResponse:
    """Fail closed when the Employer plan cannot publish another listing.

    Callers performing a publication mutation must first hold the employer
    organization's row lock so concurrent create/reopen requests serialize.
    """

    policy = get_employer_product_policy(
        db,
        user_id=user_id,
    )

    limit = policy.active_listing_limit

    if limit is None:
        return policy

    published_count = (
        InternshipRepository
        .count_published_by_employer(
            db,
            employer_user_id=user_id,
            exclude_internship_id=(
                exclude_internship_id
            ),
        )
    )

    if published_count >= limit:
        raise EmployerListingLimitError(
            plan=policy.plan,
            limit=limit,
            published_count=published_count,
        )

    return policy


def require_employer_feature(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
) -> EmployerProductPolicyResponse:
    """Fail closed when one Employer feature is unavailable."""

    if feature_key not in EMPLOYER_FEATURE_ORDER:
        raise ValueError(
            f"Unsupported Employer feature: {feature_key}"
        )

    policy = get_employer_product_policy(
        db,
        user_id=user_id,
    )

    availability = {
        FEATURE_CANDIDATE_INSIGHT: (
            policy.candidate_insight_available
        ),
        FEATURE_INTERVIEW_KIT: (
            policy.interview_kit_available
        ),
        FEATURE_SHORTLIST_COMPARISON: (
            policy.shortlist_comparison_available
        ),
        FEATURE_INTERNSHIP_DESCRIPTION: (
            policy.internship_description_available
        ),
        FEATURE_PIPELINE_ANALYTICS: (
            policy.pipeline_analytics_available
        ),
    }

    if not availability[feature_key]:
        raise EmployerFeatureAccessError(
            feature_key=feature_key,
            plan=policy.plan,
        )

    return policy
