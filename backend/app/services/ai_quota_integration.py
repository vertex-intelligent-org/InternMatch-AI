"""Execution-boundary integration helpers for AI product quotas."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.ai_quota import AIQuotaRepository
from app.services.ai_quota import (
    AIQuotaExceededError,
    release_ai_quota_operation,
    reserve_ai_quota,
    settle_ai_quota_operation,
)


def format_ai_quota_exceeded_payload(
    exc: AIQuotaExceededError,
) -> dict[str, Any]:
    """Machine-readable contract consumed later by the mobile paywall."""

    return {
        "error": {
            "code": "AI_QUOTA_EXCEEDED",
            "message": (
                "You have reached the current AI usage limit "
                "for this feature."
            ),
            "details": {
                "feature_key": exc.feature_key,
                "plan": exc.plan,
                "limit": exc.limit,
                "used": exc.used,
                "remaining": exc.remaining,
                "reset_at": exc.reset_at.isoformat(),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }


def _job_idempotency_key(
    *,
    feature_key: str,
    job_id: UUID,
) -> str:
    return f"{feature_key}:job:{job_id}"


def reserve_job_ai_quota(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    job_id: UUID,
) -> dict[str, Any]:
    """Reserve exactly one unit for one durable asynchronous job."""

    return reserve_ai_quota(
        db,
        user_id=user_id,
        feature_key=feature_key,
        idempotency_key=_job_idempotency_key(
            feature_key=feature_key,
            job_id=job_id,
        ),
        request_fingerprint=f"processing-job:{job_id}",
        processing_job_id=job_id,
    )


def _get_job_operation(
    db: Session,
    *,
    feature_key: str,
    job_id: UUID,
    for_update: bool = False,
):
    return AIQuotaRepository.get_operation_by_processing_job(
        db,
        processing_job_id=job_id,
        feature_key=feature_key,
        for_update=for_update,
    )


def ensure_job_ai_quota_reserved_if_present(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    job_id: UUID,
) -> dict[str, Any] | None:
    """Recover a released reservation when an existing RQ job is retried.

    Legacy jobs created before quota wiring have no operation row and remain
    runnable during deployment; all newly-created quota-controlled jobs are
    linked by the HTTP boundary before enqueue.
    """

    operation = _get_job_operation(
        db,
        feature_key=feature_key,
        job_id=job_id,
    )

    if operation is None:
        return None

    if operation.status != "released":
        return {
            "outcome": f"existing_{operation.status}",
            "operation": operation,
        }

    return reserve_job_ai_quota(
        db,
        user_id=user_id,
        feature_key=feature_key,
        job_id=job_id,
    )


def settle_job_ai_quota_if_present(
    db: Session,
    *,
    feature_key: str,
    job_id: UUID,
) -> dict[str, Any] | None:
    """Settle a successful job without breaking legacy pre-quota jobs."""

    operation = _get_job_operation(
        db,
        feature_key=feature_key,
        job_id=job_id,
    )

    if operation is None:
        return None

    return settle_ai_quota_operation(
        db,
        operation_id=operation.id,
    )


def release_job_ai_quota_if_present(
    db: Session,
    *,
    feature_key: str,
    job_id: UUID,
    reason: str,
) -> dict[str, Any] | None:
    """Release a failed/cancelled job without consuming quota."""

    operation = _get_job_operation(
        db,
        feature_key=feature_key,
        job_id=job_id,
    )

    if operation is None:
        return None

    return release_ai_quota_operation(
        db,
        operation_id=operation.id,
        reason=reason,
    )



def reserve_sync_ai_quota(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    idempotency_key: str,
    request_fingerprint: str,
) -> dict[str, Any]:
    """Reserve one unit for a synchronous fresh AI generation."""

    return reserve_ai_quota(
        db,
        user_id=user_id,
        feature_key=feature_key,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        processing_job_id=None,
    )


def settle_sync_ai_quota(
    db: Session,
    *,
    operation_id: UUID,
) -> dict[str, Any]:
    """Settle a successful synchronous AI generation exactly once."""

    return settle_ai_quota_operation(
        db,
        operation_id=operation_id,
    )


def release_sync_ai_quota(
    db: Session,
    *,
    operation_id: UUID,
    reason: str,
) -> dict[str, Any]:
    """Release an unsuccessful synchronous AI generation."""

    return release_ai_quota_operation(
        db,
        operation_id=operation_id,
        reason=reason,
    )
