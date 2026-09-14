"""Durable quota lifecycle for Employer AI operations.

This module reuses the existing ai_quota_periods / ai_quota_operations
ledger without coupling Employer entitlement resolution to Student plans.

Quota limits are intentionally environment-configured and fail closed.
Product limits must be chosen from real cost/usage evidence before launch.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AIQuotaOperation,
    AIQuotaPeriod,
)
from app.repositories.ai_quota import AIQuotaRepository
from app.repositories.subscription import SubscriptionRepository
from app.services.ai_quota import (
    AIQuotaExceededError,
    AIQuotaIdempotencyConflictError,
)
from app.services.subscription import (
    PRO_EMPLOYER_ENTITLEMENT_ID,
    get_employer_subscription_snapshot,
)

EMPLOYER_CANDIDATE_INSIGHT = (
    "employer_candidate_insight"
)
EMPLOYER_INTERVIEW_KIT = (
    "employer_interview_kit"
)
EMPLOYER_SHORTLIST_COMPARISON = (
    "employer_shortlist_comparison"
)
EMPLOYER_INTERNSHIP_DESCRIPTION = (
    "employer_internship_description"
)

EMPLOYER_AI_FEATURES = (
    EMPLOYER_CANDIDATE_INSIGHT,
    EMPLOYER_INTERVIEW_KIT,
    EMPLOYER_SHORTLIST_COMPARISON,
    EMPLOYER_INTERNSHIP_DESCRIPTION,
)

SYNC_RESERVATION_STALE_SECONDS = 15 * 60
MAX_IDEMPOTENCY_KEY_LENGTH = 200
MAX_FINGERPRINT_LENGTH = 512


class EmployerAIQuotaConfigurationError(RuntimeError):
    """Employer quota policy is missing or malformed."""


class EmployerAIQuotaAccessError(RuntimeError):
    """Current Employer plan cannot use this quota feature."""


_FREE_LIMIT_ENV = {
    EMPLOYER_CANDIDATE_INSIGHT: (
        "INTERNMATCH_EMPLOYER_FREE_"
        "CANDIDATE_INSIGHT_LIMIT"
    ),
}

_PRO_LIMIT_ENV = {
    EMPLOYER_CANDIDATE_INSIGHT: (
        "INTERNMATCH_EMPLOYER_PRO_"
        "CANDIDATE_INSIGHT_LIMIT"
    ),
    EMPLOYER_INTERVIEW_KIT: (
        "INTERNMATCH_EMPLOYER_PRO_"
        "INTERVIEW_KIT_LIMIT"
    ),
    EMPLOYER_SHORTLIST_COMPARISON: (
        "INTERNMATCH_EMPLOYER_PRO_"
        "SHORTLIST_COMPARISON_LIMIT"
    ),
    EMPLOYER_INTERNSHIP_DESCRIPTION: (
        "INTERNMATCH_EMPLOYER_PRO_"
        "INTERNSHIP_DESCRIPTION_LIMIT"
    ),
}

_FREE_WINDOW_ENV = (
    "INTERNMATCH_EMPLOYER_FREE_AI_WINDOW_DAYS"
)

_T = TypeVar("_T")


def _as_utc(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _read_positive_int_env(
    name: str,
) -> int:
    raw = os.getenv(name)

    if raw is None or not raw.strip():
        raise EmployerAIQuotaConfigurationError(
            f"Employer AI quota setting "
            f"{name} is not configured."
        )

    try:
        value = int(raw)
    except ValueError as exc:
        raise EmployerAIQuotaConfigurationError(
            f"Employer AI quota setting "
            f"{name} must be an integer."
        ) from exc

    if value <= 0:
        raise EmployerAIQuotaConfigurationError(
            f"Employer AI quota setting "
            f"{name} must be positive."
        )

    return value


def _normalize_idempotency_key(
    value: str,
) -> str:
    normalized = (value or "").strip()

    if not normalized:
        raise AIQuotaIdempotencyConflictError(
            "Idempotency-Key must not be blank."
        )

    if len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise AIQuotaIdempotencyConflictError(
            "Idempotency-Key is too long."
        )

    return normalized


def _normalize_fingerprint(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    if not normalized:
        return None

    if len(normalized) > MAX_FINGERPRINT_LENGTH:
        raise AIQuotaIdempotencyConflictError(
            "Request fingerprint is too long."
        )

    return normalized


def _current_period_matches(
    period: AIQuotaPeriod,
    *,
    plan_key: str,
    period_start: datetime,
    period_end: datetime,
) -> bool:
    return (
        period.plan_key == plan_key
        and _as_utc(period.period_start)
        == _as_utc(period_start)
        and _as_utc(period.period_end)
        == _as_utc(period_end)
    )


def _operation_period_matches(
    operation: AIQuotaOperation,
    period: AIQuotaPeriod,
) -> bool:
    return (
        operation.plan_key == period.plan_key
        and _as_utc(operation.period_start)
        == _as_utc(period.period_start)
        and _as_utc(operation.period_end)
        == _as_utc(period.period_end)
    )


def _resolve_policy(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    now: datetime,
    current_period: AIQuotaPeriod | None,
) -> tuple[
    str,
    int,
    datetime,
    datetime,
]:
    if feature_key not in EMPLOYER_AI_FEATURES:
        raise ValueError(
            f"Unsupported Employer AI quota feature: "
            f"{feature_key}"
        )

    subscription = (
        get_employer_subscription_snapshot(
            db,
            user_id=user_id,
        )
    )

    if (
        subscription["plan"] == "employer_pro"
        and bool(subscription["is_active"])
    ):
        limit = _read_positive_int_env(
            _PRO_LIMIT_ENV[feature_key]
        )

        entitlement = (
            SubscriptionRepository.get_entitlement(
                db,
                user_id=user_id,
                entitlement_id=(
                    PRO_EMPLOYER_ENTITLEMENT_ID
                ),
            )
        )

        if entitlement is None:
            raise EmployerAIQuotaConfigurationError(
                "Active Employer Pro state is "
                "missing its entitlement record."
            )

        period_start = _as_utc(
            getattr(
                entitlement,
                "current_period_started_at",
                None,
            )
        )
        period_end = _as_utc(
            getattr(
                entitlement,
                "expires_at",
                None,
            )
        )

        if (
            period_start is None
            or period_end is None
            or period_start >= period_end
            or period_end <= now
        ):
            raise EmployerAIQuotaConfigurationError(
                "Employer Pro billing period "
                "is missing or invalid."
            )

        return (
            "employer_pro",
            limit,
            period_start,
            period_end,
        )

    if feature_key != EMPLOYER_CANDIDATE_INSIGHT:
        raise EmployerAIQuotaAccessError(
            "Employer Pro is required "
            "for this AI feature."
        )

    limit = _read_positive_int_env(
        _FREE_LIMIT_ENV[feature_key]
    )
    window_days = _read_positive_int_env(
        _FREE_WINDOW_ENV
    )

    if (
        current_period is not None
        and current_period.plan_key == "free"
    ):
        existing_start = _as_utc(
            current_period.period_start
        )
        existing_end = _as_utc(
            current_period.period_end
        )

        if (
            existing_start is not None
            and existing_end is not None
            and existing_start <= now
            and existing_end > now
        ):
            return (
                "free",
                limit,
                existing_start,
                existing_end,
            )

    return (
        "free",
        limit,
        now,
        now + timedelta(
            days=window_days
        ),
    )


def _release_stale_sync_operations(
    db: Session,
    *,
    period: AIQuotaPeriod,
    now: datetime,
) -> None:
    stale_before = now - timedelta(
        seconds=SYNC_RESERVATION_STALE_SECONDS
    )

    stmt = (
        select(AIQuotaOperation)
        .where(
            AIQuotaOperation.user_id
            == period.user_id,
            AIQuotaOperation.feature_key
            == period.feature_key,
            AIQuotaOperation.plan_key
            == period.plan_key,
            AIQuotaOperation.period_start
            == period.period_start,
            AIQuotaOperation.status
            == "reserved",
            AIQuotaOperation.processing_job_id
            .is_(None),
            AIQuotaOperation.reserved_at
            <= stale_before,
        )
        .with_for_update()
    )

    stale_operations = list(
        db.scalars(stmt).all()
    )

    for operation in stale_operations:
        if period.reserved_count > 0:
            period.reserved_count -= 1

        operation.status = "released"
        operation.released_at = now
        operation.settled_at = None
        operation.release_reason = (
            "stale_sync_reservation"
        )
        operation.updated_at = now


def reserve_employer_ai_quota(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    idempotency_key: str,
    request_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Reserve one Employer AI product unit atomically.

    Caller owns commit/rollback.
    """

    key = _normalize_idempotency_key(
        idempotency_key
    )
    fingerprint = _normalize_fingerprint(
        request_fingerprint
    )
    now = datetime.now(timezone.utc)

    AIQuotaRepository.acquire_feature_lock(
        db,
        user_id=user_id,
        feature_key=feature_key,
    )

    current_period = db.scalar(
        select(AIQuotaPeriod)
        .where(
            AIQuotaPeriod.user_id == user_id,
            AIQuotaPeriod.feature_key
            == feature_key,
        )
        .with_for_update()
    )

    (
        plan_key,
        limit,
        period_start,
        period_end,
    ) = _resolve_policy(
        db,
        user_id=user_id,
        feature_key=feature_key,
        now=now,
        current_period=current_period,
    )

    if current_period is None:
        current_period = AIQuotaPeriod(
            user_id=user_id,
            feature_key=feature_key,
            plan_key=plan_key,
            period_start=period_start,
            period_end=period_end,
            used_count=0,
            reserved_count=0,
        )
        db.add(current_period)
        db.flush()
    elif not _current_period_matches(
        current_period,
        plan_key=plan_key,
        period_start=period_start,
        period_end=period_end,
    ):
        current_period.plan_key = plan_key
        current_period.period_start = (
            period_start
        )
        current_period.period_end = period_end
        current_period.used_count = 0
        current_period.reserved_count = 0
        db.flush()

    _release_stale_sync_operations(
        db,
        period=current_period,
        now=now,
    )

    existing = db.scalar(
        select(AIQuotaOperation)
        .where(
            AIQuotaOperation.user_id
            == user_id,
            AIQuotaOperation.feature_key
            == feature_key,
            AIQuotaOperation.period_start
            == period_start,
            AIQuotaOperation.idempotency_key
            == key,
        )
        .with_for_update()
    )

    if existing is not None:
        if (
            existing.request_fingerprint
            != fingerprint
        ):
            raise AIQuotaIdempotencyConflictError(
                "Idempotency-Key was reused "
                "for different request content."
            )

        if existing.status in {
            "reserved",
            "settled",
        }:
            return {
                "outcome": (
                    f"duplicate_{existing.status}"
                ),
                "operation": existing,
                "period": current_period,
                "limit": limit,
            }

        if existing.status == "released":
            if (
                current_period.used_count
                + current_period.reserved_count
                >= limit
            ):
                raise AIQuotaExceededError(
                    feature_key=feature_key,
                    plan=plan_key,
                    limit=limit,
                    used=(
                        current_period.used_count
                    ),
                    reserved=(
                        current_period.reserved_count
                    ),
                    reset_at=period_end,
                )

            existing.status = "reserved"
            existing.reserved_at = now
            existing.settled_at = None
            existing.released_at = None
            existing.release_reason = None
            existing.updated_at = now

            current_period.reserved_count += 1
            db.flush()

            return {
                "outcome": "reserved_again",
                "operation": existing,
                "period": current_period,
                "limit": limit,
            }

    if (
        current_period.used_count
        + current_period.reserved_count
        >= limit
    ):
        raise AIQuotaExceededError(
            feature_key=feature_key,
            plan=plan_key,
            limit=limit,
            used=current_period.used_count,
            reserved=current_period.reserved_count,
            reset_at=period_end,
        )

    operation = AIQuotaOperation(
        user_id=user_id,
        feature_key=feature_key,
        plan_key=plan_key,
        period_start=period_start,
        period_end=period_end,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        status="reserved",
        processing_job_id=None,
        reserved_at=now,
    )

    db.add(operation)
    current_period.reserved_count += 1
    db.flush()

    return {
        "outcome": "reserved",
        "operation": operation,
        "period": current_period,
        "limit": limit,
    }


def settle_employer_ai_quota_operation(
    db: Session,
    *,
    operation_id: UUID,
) -> dict[str, Any]:
    """Settle one successful Employer AI reservation exactly once."""

    peek = db.get(
        AIQuotaOperation,
        operation_id,
    )

    if peek is None:
        raise ValueError(
            "Employer AI quota operation "
            "was not found."
        )

    AIQuotaRepository.acquire_feature_lock(
        db,
        user_id=peek.user_id,
        feature_key=peek.feature_key,
    )

    operation = db.scalar(
        select(AIQuotaOperation)
        .where(
            AIQuotaOperation.id
            == operation_id
        )
        .with_for_update()
    )

    if operation is None:
        raise ValueError(
            "Employer AI quota operation "
            "was not found."
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

    period = db.scalar(
        select(AIQuotaPeriod)
        .where(
            AIQuotaPeriod.user_id
            == operation.user_id,
            AIQuotaPeriod.feature_key
            == operation.feature_key,
        )
        .with_for_update()
    )

    if (
        period is not None
        and _operation_period_matches(
            operation,
            period,
        )
    ):
        if period.reserved_count > 0:
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


def release_employer_ai_quota_operation(
    db: Session,
    *,
    operation_id: UUID,
    reason: str | None = None,
) -> dict[str, Any]:
    """Release a failed Employer AI reservation without consuming it."""

    peek = db.get(
        AIQuotaOperation,
        operation_id,
    )

    if peek is None:
        raise ValueError(
            "Employer AI quota operation "
            "was not found."
        )

    AIQuotaRepository.acquire_feature_lock(
        db,
        user_id=peek.user_id,
        feature_key=peek.feature_key,
    )

    operation = db.scalar(
        select(AIQuotaOperation)
        .where(
            AIQuotaOperation.id
            == operation_id
        )
        .with_for_update()
    )

    if operation is None:
        raise ValueError(
            "Employer AI quota operation "
            "was not found."
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

    period = db.scalar(
        select(AIQuotaPeriod)
        .where(
            AIQuotaPeriod.user_id
            == operation.user_id,
            AIQuotaPeriod.feature_key
            == operation.feature_key,
        )
        .with_for_update()
    )

    if (
        period is not None
        and _operation_period_matches(
            operation,
            period,
        )
        and period.reserved_count > 0
    ):
        period.reserved_count -= 1

    now = datetime.now(timezone.utc)

    operation.status = "released"
    operation.released_at = now
    operation.settled_at = None
    operation.release_reason = (
        (reason or "provider_failure")[:200]
    )
    operation.updated_at = now

    db.flush()

    return {
        "outcome": "released",
        "operation": operation,
    }


def execute_employer_ai_with_quota(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    idempotency_key: str,
    request_fingerprint: str | None,
    callback: Callable[[], _T],
) -> _T:
    """Reserve -> execute -> settle/release with durable boundaries."""

    reservation = reserve_employer_ai_quota(
        db,
        user_id=user_id,
        feature_key=feature_key,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
    )

    operation_id = reservation[
        "operation"
    ].id

    # Reservation must survive provider/process work.
    db.commit()

    try:
        result = callback()
    except Exception:
        db.rollback()

        try:
            release_employer_ai_quota_operation(
                db,
                operation_id=operation_id,
                reason="provider_or_service_failure",
            )
            db.commit()
        except Exception:
            db.rollback()

        raise

    try:
        settle_employer_ai_quota_operation(
            db,
            operation_id=operation_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return result
