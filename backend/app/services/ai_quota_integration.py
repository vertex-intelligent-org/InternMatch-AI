"""Execution-boundary integration helpers for AI product quotas."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.ai_quota import AIQuotaRepository
from app.repositories.processing_job import ProcessingJobRepository
from app.services.ai_quota import (
    AIQuotaConfigurationError,
    AIQuotaExceededError,
    AIQuotaIdempotencyConflictError,
    release_ai_quota_operation,
    reserve_ai_quota,
    settle_ai_quota_operation,
)

SYNC_AI_RESERVATION_STALE_SECONDS = 15 * 60
HTTP_IDEMPOTENCY_KEY_MAX_LENGTH = 200
RETRYABLE_ASYNC_RELEASE_REASONS = frozenset(
    {
        "enqueue_failure",
        "worker_failure",
    }
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



def format_ai_idempotency_conflict_payload() -> dict[str, Any]:
    """Safe machine-readable response for conflicting HTTP retries."""

    return {
        "error": {
            "code": "AI_IDEMPOTENCY_CONFLICT",
            "message": (
                "This Idempotency-Key was already used "
                "for a different request."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }



def build_ai_request_fingerprint(
    payload: dict[str, Any],
) -> str:
    """Stable SHA-256 fingerprint for an HTTP AI request."""

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def build_cv_request_fingerprint(
    *,
    content: bytes,
    filename: str,
    content_type: str,
) -> str:
    """Fingerprint CV bytes and request metadata without persisting content."""

    content_digest = hashlib.sha256(content).hexdigest()

    return build_ai_request_fingerprint(
        {
            "content_sha256": content_digest,
            "filename": filename,
            "content_type": content_type,
        }
    )


def _http_job_idempotency_key(
    *,
    feature_key: str,
    raw_key: str,
) -> str:
    normalized = raw_key.strip()

    if not normalized:
        raise AIQuotaIdempotencyConflictError(
            "Idempotency-Key must not be blank."
        )

    if len(normalized) > HTTP_IDEMPOTENCY_KEY_MAX_LENGTH:
        raise AIQuotaIdempotencyConflictError(
            "Idempotency-Key is too long."
        )

    digest = hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()

    return f"{feature_key}:http:{digest}"


def acquire_job_ai_quota_lock(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
) -> None:
    """Serialize request-level job idempotency with quota mutation."""

    AIQuotaRepository.acquire_feature_lock(
        db,
        user_id=user_id,
        feature_key=feature_key,
    )


def get_http_idempotent_job_ai_quota(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    raw_idempotency_key: str,
    request_fingerprint: str,
) -> dict[str, Any] | None:
    """Resolve an existing HTTP retry to its original durable job."""

    internal_key = _http_job_idempotency_key(
        feature_key=feature_key,
        raw_key=raw_idempotency_key,
    )

    operation = (
        AIQuotaRepository.get_latest_operation_by_idempotency_key(
            db,
            user_id=user_id,
            feature_key=feature_key,
            idempotency_key=internal_key,
        )
    )

    if operation is None:
        return None

    if operation.request_fingerprint != request_fingerprint:
        raise AIQuotaIdempotencyConflictError(
            "Idempotency-Key was reused for a different request."
        )

    if operation.processing_job_id is None:
        raise AIQuotaConfigurationError(
            "HTTP idempotency operation is missing its ProcessingJob."
        )

    job = ProcessingJobRepository.get_by_id_and_user_id(
        db,
        job_id=operation.processing_job_id,
        user_id=user_id,
    )

    if job is None:
        raise AIQuotaConfigurationError(
            "HTTP idempotency operation references a missing ProcessingJob."
        )

    return {
        "operation": operation,
        "job": job,
        "idempotency_key": internal_key,
    }


def reserve_http_idempotent_job_ai_quota(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    job_id: UUID,
    raw_idempotency_key: str,
    request_fingerprint: str,
) -> dict[str, Any]:
    """Reserve/re-reserve the same quota operation for one HTTP request."""

    internal_key = _http_job_idempotency_key(
        feature_key=feature_key,
        raw_key=raw_idempotency_key,
    )

    return reserve_ai_quota(
        db,
        user_id=user_id,
        feature_key=feature_key,
        idempotency_key=internal_key,
        request_fingerprint=request_fingerprint,
        processing_job_id=job_id,
    )


def is_retryable_released_job_ai_quota(
    operation: Any,
) -> bool:
    """Only transient async failures may restart under the same HTTP key."""

    return (
        operation.status == "released"
        and operation.release_reason
        in RETRYABLE_ASYNC_RELEASE_REASONS
    )


def release_stale_sync_ai_quota_reservations(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    now: datetime | None = None,
) -> int:
    """Release abandoned synchronous reservations conservatively.

    Only operations without ProcessingJob linkage are eligible. Async jobs
    are reconciled through their durable worker lifecycle instead.
    """

    reference_time = now or datetime.now(timezone.utc)
    reserved_before = reference_time - timedelta(
        seconds=SYNC_AI_RESERVATION_STALE_SECONDS
    )

    stale_operations = (
        AIQuotaRepository.list_stale_sync_reservations(
            db,
            user_id=user_id,
            feature_key=feature_key,
            reserved_before=reserved_before,
        )
    )

    released_count = 0

    for operation in stale_operations:
        result = release_ai_quota_operation(
            db,
            operation_id=operation.id,
            reason="stale_sync_reservation",
        )

        if result["outcome"] == "released":
            released_count += 1

    return released_count


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
    """Reserve one unit for a synchronous fresh AI generation.

    Abandoned synchronous reservations are released first. Cleanup is
    committed independently so an over-limit exception cannot roll it back.
    """

    released_count = release_stale_sync_ai_quota_reservations(
        db,
        user_id=user_id,
        feature_key=feature_key,
    )

    if released_count:
        db.commit()

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
