"""Backend-authoritative Student AI feature quota policy.

SUB-2 defines plans, limits, periods, and read snapshots.
Actual atomic reservation and settlement is implemented in SUB-3.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import AIQuotaPeriod
from app.repositories.ai_quota import AIQuotaRepository
from app.repositories.subscription import SubscriptionRepository
from app.services.subscription import (
    PRO_STUDENT_ENTITLEMENT_ID,
    get_student_subscription_snapshot,
)

FEATURE_CV_ANALYSIS = "cv_analysis"
FEATURE_MATCH_EXPLANATION = "match_explanation"
FEATURE_APPLICATION_SUPPORT = "application_support"
FEATURE_INTERVIEW_PREP = "interview_prep"

AI_FEATURE_ORDER = (
    FEATURE_CV_ANALYSIS,
    FEATURE_MATCH_EXPLANATION,
    FEATURE_APPLICATION_SUPPORT,
    FEATURE_INTERVIEW_PREP,
)


@dataclass(frozen=True)
class AIQuotaPolicy:
    """One backend-controlled feature policy for one subscription plan."""

    feature_key: str
    display_name: str
    limit: int
    window_days: int | None


FREE_POLICIES: dict[str, AIQuotaPolicy] = {
    FEATURE_CV_ANALYSIS: AIQuotaPolicy(
        feature_key=FEATURE_CV_ANALYSIS,
        display_name="CV analyses",
        limit=1,
        window_days=30,
    ),
    FEATURE_MATCH_EXPLANATION: AIQuotaPolicy(
        feature_key=FEATURE_MATCH_EXPLANATION,
        display_name="Match explanations",
        limit=5,
        window_days=7,
    ),
    FEATURE_APPLICATION_SUPPORT: AIQuotaPolicy(
        feature_key=FEATURE_APPLICATION_SUPPORT,
        display_name="Application AI assists",
        limit=3,
        window_days=7,
    ),
    FEATURE_INTERVIEW_PREP: AIQuotaPolicy(
        feature_key=FEATURE_INTERVIEW_PREP,
        display_name="Interview prep sessions",
        limit=2,
        window_days=7,
    ),
}

PRO_STUDENT_POLICIES: dict[str, AIQuotaPolicy] = {
    FEATURE_CV_ANALYSIS: AIQuotaPolicy(
        feature_key=FEATURE_CV_ANALYSIS,
        display_name="CV analyses",
        limit=10,
        window_days=None,
    ),
    FEATURE_MATCH_EXPLANATION: AIQuotaPolicy(
        feature_key=FEATURE_MATCH_EXPLANATION,
        display_name="Match explanations",
        limit=100,
        window_days=None,
    ),
    FEATURE_APPLICATION_SUPPORT: AIQuotaPolicy(
        feature_key=FEATURE_APPLICATION_SUPPORT,
        display_name="Application AI assists",
        limit=50,
        window_days=None,
    ),
    FEATURE_INTERVIEW_PREP: AIQuotaPolicy(
        feature_key=FEATURE_INTERVIEW_PREP,
        display_name="Interview prep sessions",
        limit=20,
        window_days=None,
    ),
}


class AIQuotaConfigurationError(RuntimeError):
    """Local subscription/quota state cannot define a safe quota period."""


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _policy_set(plan: str) -> dict[str, AIQuotaPolicy]:
    if plan == "pro_student":
        return PRO_STUDENT_POLICIES

    return FREE_POLICIES


def _same_instant(
    first: datetime,
    second: datetime,
) -> bool:
    first_utc = _as_utc(first)
    second_utc = _as_utc(second)

    return first_utc == second_utc


def _find_free_period(
    rows: list[AIQuotaPeriod],
    *,
    feature_key: str,
) -> AIQuotaPeriod | None:
    for row in rows:
        if row.feature_key == feature_key:
            return row

    return None


def _find_pro_period(
    rows: list[AIQuotaPeriod],
    *,
    feature_key: str,
    period_start: datetime,
    period_end: datetime,
) -> AIQuotaPeriod | None:
    for row in rows:
        if row.feature_key != feature_key:
            continue

        if not _same_instant(row.period_start, period_start):
            continue

        if not _same_instant(row.period_end, period_end):
            continue

        return row

    return None


def _resolve_pro_billing_period(
    db: Session,
    *,
    user_id: UUID,
    now: datetime,
) -> tuple[datetime, datetime]:
    entitlement = SubscriptionRepository.get_entitlement(
        db,
        user_id=user_id,
        entitlement_id=PRO_STUDENT_ENTITLEMENT_ID,
    )

    if entitlement is None:
        raise AIQuotaConfigurationError(
            "Active Student Pro state is missing its entitlement record."
        )

    period_start = _as_utc(
        entitlement.current_period_started_at
    )
    period_end = _as_utc(entitlement.expires_at)

    if period_start is None or period_end is None:
        raise AIQuotaConfigurationError(
            "Active Student Pro state is missing billing-period timestamps."
        )

    if period_start >= period_end:
        raise AIQuotaConfigurationError(
            "Student Pro billing period is invalid."
        )

    if period_end <= now:
        raise AIQuotaConfigurationError(
            "Student Pro billing period has already ended."
        )

    return period_start, period_end


def get_ai_usage_snapshot(
    db: Session,
    *,
    user_id: UUID,
) -> dict[str, Any]:
    """Return plan-aware AI limits and current remaining usage.

    This function does not create or mutate quota periods.
    """

    now = datetime.now(timezone.utc)

    subscription = get_student_subscription_snapshot(
        db,
        user_id=user_id,
    )
    plan = subscription["plan"]

    policies = _policy_set(plan)

    active_rows = AIQuotaRepository.list_active_periods(
        db,
        user_id=user_id,
        plan_key=plan,
        now=now,
    )

    pro_period: tuple[datetime, datetime] | None = None

    if plan == "pro_student":
        pro_period = _resolve_pro_billing_period(
            db,
            user_id=user_id,
            now=now,
        )

    features: list[dict[str, Any]] = []

    for feature_key in AI_FEATURE_ORDER:
        policy = policies[feature_key]

        if plan == "pro_student":
            assert pro_period is not None

            period_start, period_end = pro_period

            row = _find_pro_period(
                active_rows,
                feature_key=feature_key,
                period_start=period_start,
                period_end=period_end,
            )

            reset_policy = "billing_period"
        else:
            if policy.window_days is None:
                raise AIQuotaConfigurationError(
                    f"Free policy for {feature_key} has no reset window."
                )

            row = _find_free_period(
                active_rows,
                feature_key=feature_key,
            )

            if row is None:
                # A Free period is anchored when SUB-3 performs the first
                # reservation. Until then, preview the reset time from now.
                period_start = now
                period_end = now + timedelta(
                    days=policy.window_days
                )
            else:
                period_start = _as_utc(row.period_start)
                period_end = _as_utc(row.period_end)

                if period_start is None or period_end is None:
                    raise AIQuotaConfigurationError(
                        "Stored Free quota period is invalid."
                    )

            reset_policy = f"{policy.window_days}_days"

        used = int(row.used_count) if row is not None else 0
        reserved = (
            int(row.reserved_count)
            if row is not None
            else 0
        )

        remaining = max(
            policy.limit - used - reserved,
            0,
        )

        features.append(
            {
                "feature_key": policy.feature_key,
                "display_name": policy.display_name,
                "limit": policy.limit,
                "used": used,
                "remaining": remaining,
                "reset_policy": reset_policy,
                "period_started_at": period_start,
                "reset_at": period_end,
            }
        )

    return {
        "plan": plan,
        "features": features,
    }
