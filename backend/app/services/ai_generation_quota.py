"""
Quota adapter for AI generation services that can execute either synchronously
or inside a durable ProcessingJob.

Synchronous callers retain the existing reservation semantics. Durable workers
link quota operations to the ProcessingJob so authoritative cancellation can
release capacity safely.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.services.ai_quota_integration import (
    ensure_job_ai_quota_reserved_if_present,
    release_job_ai_quota_if_present,
    release_sync_ai_quota,
    reserve_job_ai_quota,
    reserve_sync_ai_quota,
    settle_job_ai_quota_if_present,
    settle_sync_ai_quota,
)


def reserve_generation_ai_quota(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    idempotency_key: str,
    request_fingerprint: str,
    processing_job_id: UUID | None,
):
    """
    Reserve only when a fresh AI generation is actually required.

    For a durable job, reuse/re-reserve its existing operation on retry instead
    of creating a second quota operation.
    """
    if processing_job_id is None:
        return reserve_sync_ai_quota(
            db,
            user_id=user_id,
            feature_key=feature_key,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )

    existing = ensure_job_ai_quota_reserved_if_present(
        db,
        user_id=user_id,
        feature_key=feature_key,
        job_id=processing_job_id,
    )

    if existing is not None:
        return existing

    return reserve_job_ai_quota(
        db,
        user_id=user_id,
        feature_key=feature_key,
        job_id=processing_job_id,
    )


def settle_generation_ai_quota(
    db: Session,
    *,
    feature_key: str,
    operation_id: UUID,
    processing_job_id: UUID | None,
):
    """Settle exactly once using the appropriate sync/durable operation."""
    if processing_job_id is None:
        return settle_sync_ai_quota(
            db,
            operation_id=operation_id,
        )

    return settle_job_ai_quota_if_present(
        db,
        feature_key=feature_key,
        job_id=processing_job_id,
    )


def release_generation_ai_quota(
    db: Session,
    *,
    feature_key: str,
    operation_id: UUID,
    processing_job_id: UUID | None,
    reason: str,
):
    """Release unsuccessful/cancelled generation without consuming quota."""
    if processing_job_id is None:
        return release_sync_ai_quota(
            db,
            operation_id=operation_id,
            reason=reason,
        )

    return release_job_ai_quota_if_present(
        db,
        feature_key=feature_key,
        job_id=processing_job_id,
        reason=reason,
    )
