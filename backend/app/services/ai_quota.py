"""Backend-authoritative Student AI feature quota policy.

SUB-2 defines plans, limits, periods, and read snapshots.
Actual atomic reservation and settlement is implemented in SUB-3.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import AIQuotaOperation, AIQuotaPeriod
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


class AIQuotaExceededError(RuntimeError):
    """The authenticated user has no capacity left for this AI feature."""

    def __init__(
        self,
        *,
        feature_key: str,
        plan: str,
        limit: int,
        used: int,
        reserved: int,
        reset_at: datetime,
    ) -> None:
        super().__init__(
            f"AI quota exceeded for feature {feature_key}."
        )
        self.feature_key = feature_key
        self.plan = plan
        self.limit = limit
        self.used = used
        self.reserved = reserved
        self.remaining = max(
            limit - used - reserved,
            0,
        )
        self.reset_at = reset_at


class AIQuotaIdempotencyConflictError(RuntimeError):
    """One idempotency key was reused for different request content."""


class AIQuotaOperationNotFoundError(RuntimeError):
    """Requested quota operation ledger entry does not exist."""


def _normalize_idempotency_key(value: str) -> str:
    normalized = (value or "").strip()

    if not normalized:
        raise ValueError(
            "AI quota idempotency key is required."
        )

    if len(normalized) > 200:
        raise ValueError(
            "AI quota idempotency key exceeds 200 characters."
        )

    return normalized


def _normalize_request_fingerprint(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    if not normalized:
        return None

    if len(normalized) > 512:
        raise ValueError(
            "AI quota request fingerprint exceeds 512 characters."
        )

    return normalized


def _period_matches(
    row: AIQuotaPeriod,
    *,
    plan_key: str,
    period_start: datetime,
    period_end: datetime,
) -> bool:
    return (
        row.plan_key == plan_key
        and _same_instant(
            row.period_start,
            period_start,
        )
        and _same_instant(
            row.period_end,
            period_end,
        )
    )


def _operation_matches_current_period(
    operation: "AIQuotaOperation",
    period: AIQuotaPeriod,
) -> bool:
    return (
        operation.plan_key == period.plan_key
        and _same_instant(
            operation.period_start,
            period.period_start,
        )
        and _same_instant(
            operation.period_end,
            period.period_end,
        )
    )


def _resolve_reservation_period(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    current_period: AIQuotaPeriod | None,
    now: datetime,
) -> tuple[
    str,
    AIQuotaPolicy,
    datetime,
    datetime,
]:
    subscription = get_student_subscription_snapshot(
        db,
        user_id=user_id,
    )

    plan = subscription["plan"]
    policies = _policy_set(plan)

    if feature_key not in policies:
        raise ValueError(
            f"Unsupported AI quota feature: {feature_key}"
        )

    policy = policies[feature_key]

    if plan == "pro_student":
        period_start, period_end = (
            _resolve_pro_billing_period(
                db,
                user_id=user_id,
                now=now,
            )
        )

        return (
            plan,
            policy,
            period_start,
            period_end,
        )

    if policy.window_days is None:
        raise AIQuotaConfigurationError(
            f"Free policy for {feature_key} has no reset window."
        )

    if (
        current_period is not None
        and current_period.plan_key == "free"
        and _as_utc(current_period.period_start) is not None
        and _as_utc(current_period.period_end) is not None
        and _as_utc(current_period.period_start) <= now
        and _as_utc(current_period.period_end) > now
    ):
        period_start = _as_utc(
            current_period.period_start
        )
        period_end = _as_utc(
            current_period.period_end
        )

        assert period_start is not None
        assert period_end is not None

        return (
            plan,
            policy,
            period_start,
            period_end,
        )

    return (
        plan,
        policy,
        now,
        now + timedelta(days=policy.window_days),
    )


def reserve_ai_quota(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    idempotency_key: str,
    request_fingerprint: str | None = None,
    processing_job_id: UUID | None = None,
) -> dict[str, Any]:
    """Atomically reserve one unit of AI feature capacity.

    Caller owns commit/rollback.

    Duplicate reserved/settled operations do not increment counters.
    A previously released operation may be reserved again with the same
    idempotency key, allowing safe retries after provider/infrastructure
    failures.
    """

    if feature_key not in AI_FEATURE_ORDER:
        raise ValueError(
            f"Unsupported AI quota feature: {feature_key}"
        )

    key = _normalize_idempotency_key(
        idempotency_key
    )
    fingerprint = _normalize_request_fingerprint(
        request_fingerprint
    )

    now = datetime.now(timezone.utc)

    AIQuotaRepository.acquire_feature_lock(
        db,
        user_id=user_id,
        feature_key=feature_key,
    )

    period = AIQuotaRepository.get_feature_period(
        db,
        user_id=user_id,
        feature_key=feature_key,
        for_update=True,
    )

    (
        plan,
        policy,
        target_start,
        target_end,
    ) = _resolve_reservation_period(
        db,
        user_id=user_id,
        feature_key=feature_key,
        current_period=period,
        now=now,
    )

    if period is None:
        period = AIQuotaPeriod(
            user_id=user_id,
            feature_key=feature_key,
            plan_key=plan,
            period_start=target_start,
            period_end=target_end,
            used_count=0,
            reserved_count=0,
        )
        db.add(period)
        db.flush()

    elif not _period_matches(
        period,
        plan_key=plan,
        period_start=target_start,
        period_end=target_end,
    ):
        # One current aggregate row exists per user+feature.
        # When plan/period changes, old in-flight operations remain in the
        # durable operation ledger, but the aggregate counter starts fresh.
        period.plan_key = plan
        period.period_start = target_start
        period.period_end = target_end
        period.used_count = 0
        period.reserved_count = 0

        db.flush()

    operation = AIQuotaRepository.get_operation_by_key(
        db,
        user_id=user_id,
        feature_key=feature_key,
        period_start=target_start,
        idempotency_key=key,
        for_update=True,
    )

    if operation is not None:
        if (
            operation.request_fingerprint is not None
            and fingerprint is not None
            and operation.request_fingerprint != fingerprint
        ):
            raise AIQuotaIdempotencyConflictError(
                "Idempotency key was reused for different AI request content."
            )

        if (
            operation.request_fingerprint is None
            and fingerprint is not None
        ):
            operation.request_fingerprint = fingerprint

        if processing_job_id is not None:
            if (
                operation.processing_job_id is not None
                and operation.processing_job_id
                != processing_job_id
            ):
                raise AIQuotaIdempotencyConflictError(
                    "Idempotency key is already linked to another processing job."
                )

            operation.processing_job_id = (
                processing_job_id
            )

        if operation.status in {
            "reserved",
            "settled",
        }:
            return {
                "outcome": (
                    "duplicate_"
                    + operation.status
                ),
                "operation": operation,
                "period": period,
                "limit": policy.limit,
            }

        # released -> explicit safe retry
        if (
            period.used_count
            + period.reserved_count
            >= policy.limit
        ):
            raise AIQuotaExceededError(
                feature_key=feature_key,
                plan=plan,
                limit=policy.limit,
                used=period.used_count,
                reserved=period.reserved_count,
                reset_at=target_end,
            )

        period.reserved_count += 1
        operation.status = "reserved"
        operation.reserved_at = now
        operation.settled_at = None
        operation.released_at = None
        operation.release_reason = None
        operation.updated_at = now

        db.flush()

        return {
            "outcome": "re_reserved",
            "operation": operation,
            "period": period,
            "limit": policy.limit,
        }

    if (
        period.used_count
        + period.reserved_count
        >= policy.limit
    ):
        raise AIQuotaExceededError(
            feature_key=feature_key,
            plan=plan,
            limit=policy.limit,
            used=period.used_count,
            reserved=period.reserved_count,
            reset_at=target_end,
        )

    operation = AIQuotaOperation(
        user_id=user_id,
        feature_key=feature_key,
        plan_key=plan,
        period_start=target_start,
        period_end=target_end,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        status="reserved",
        processing_job_id=processing_job_id,
        reserved_at=now,
    )

    db.add(operation)
    period.reserved_count += 1
    db.flush()

    return {
        "outcome": "reserved",
        "operation": operation,
        "period": period,
        "limit": policy.limit,
    }


def settle_ai_quota_operation(
    db: Session,
    *,
    operation_id: UUID,
) -> dict[str, Any]:
    """Settle a successful reservation exactly once."""

    peek = AIQuotaRepository.get_operation_by_id(
        db,
        operation_id=operation_id,
    )

    if peek is None:
        raise AIQuotaOperationNotFoundError(
            "AI quota operation was not found."
        )

    AIQuotaRepository.acquire_feature_lock(
        db,
        user_id=peek.user_id,
        feature_key=peek.feature_key,
    )

    operation = AIQuotaRepository.get_operation_by_id(
        db,
        operation_id=operation_id,
        for_update=True,
    )

    if operation is None:
        raise AIQuotaOperationNotFoundError(
            "AI quota operation was not found."
        )

    if operation.status == "settled":
        return {
            "outcome": "already_settled",
            "operation": operation,
        }

    if operation.status == "released":
        return {
            "outcome": "already_released",
            "operation": operation,
        }

    period = AIQuotaRepository.get_feature_period(
        db,
        user_id=operation.user_id,
        feature_key=operation.feature_key,
        for_update=True,
    )

    if (
        period is not None
        and _operation_matches_current_period(
            operation,
            period,
        )
    ):
        if period.reserved_count <= 0:
            raise AIQuotaConfigurationError(
                "Quota reservation counter is inconsistent."
            )

        period.reserved_count -= 1
        period.used_count += 1

    now = datetime.now(timezone.utc)

    operation.status = "settled"
    operation.settled_at = now
    operation.released_at = None
    operation.release_reason = None
    operation.updated_at = now

    db.flush()

    return {
        "outcome": "settled",
        "operation": operation,
    }


def release_ai_quota_operation(
    db: Session,
    *,
    operation_id: UUID,
    reason: str | None = None,
) -> dict[str, Any]:
    """Release an unsuccessful reservation without consuming quota."""

    peek = AIQuotaRepository.get_operation_by_id(
        db,
        operation_id=operation_id,
    )

    if peek is None:
        raise AIQuotaOperationNotFoundError(
            "AI quota operation was not found."
        )

    AIQuotaRepository.acquire_feature_lock(
        db,
        user_id=peek.user_id,
        feature_key=peek.feature_key,
    )

    operation = AIQuotaRepository.get_operation_by_id(
        db,
        operation_id=operation_id,
        for_update=True,
    )

    if operation is None:
        raise AIQuotaOperationNotFoundError(
            "AI quota operation was not found."
        )

    if operation.status == "released":
        return {
            "outcome": "already_released",
            "operation": operation,
        }

    if operation.status == "settled":
        return {
            "outcome": "already_settled",
            "operation": operation,
        }

    period = AIQuotaRepository.get_feature_period(
        db,
        user_id=operation.user_id,
        feature_key=operation.feature_key,
        for_update=True,
    )

    if (
        period is not None
        and _operation_matches_current_period(
            operation,
            period,
        )
    ):
        if period.reserved_count <= 0:
            raise AIQuotaConfigurationError(
                "Quota reservation counter is inconsistent."
            )

        period.reserved_count -= 1

    now = datetime.now(timezone.utc)

    operation.status = "released"
    operation.released_at = now
    operation.settled_at = None
    operation.release_reason = (
        reason.strip()[:500]
        if reason and reason.strip()
        else None
    )
    operation.updated_at = now

    db.flush()

    return {
        "outcome": "released",
        "operation": operation,
    }
