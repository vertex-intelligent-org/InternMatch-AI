"""
Authoritative cancellation for user-owned durable AI processing jobs.

Cancellation is intentionally distinct from merely stopping mobile polling:
the server marks the durable operation terminal and releases any still-reserved
AI quota before the client is allowed to treat cancellation as successful.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.processing_job import ProcessingJobRepository
from app.services.ai_quota_integration import (
    release_job_ai_quota_if_present,
)


class ProcessingJobCancellationNotFound(Exception):
    pass


class ProcessingJobCancellationUnsupported(Exception):
    pass


class ProcessingJobCancellationTerminal(Exception):
    pass


# CV extraction deliberately remains on its specialized cancellation endpoint
# because CV replacement/identity-confirmation has additional invariants.
#
# Match explanation and interview prep are included now so the same authority
# can be reused when their synchronous flows are moved to durable jobs.
CANCELLABLE_AI_JOB_QUOTA_FEATURES: dict[str, Optional[str]] = {
    "application_generation": "application_support",
    "match_calculation": None,
    "match_explanation": "match_explanation",
    "interview_prep": "interview_prep",
}


def cancel_user_processing_job(
    db: Session,
    *,
    job_id: UUID,
    user_id: UUID,
):
    job = ProcessingJobRepository.get_by_id_and_user_id_for_update(
            db=db,
            job_id=job_id,
            user_id=user_id,
    )

    if job is None:
        raise ProcessingJobCancellationNotFound()

    if job.job_type not in CANCELLABLE_AI_JOB_QUOTA_FEATURES:
        raise ProcessingJobCancellationUnsupported(
            f"Job type {job.job_type!r} is not cancellable here."
        )

    current_result = (
        dict(job.result)
        if isinstance(job.result, dict)
        else {}
    )

    # Idempotent replay of a successful cancellation.
    if current_result.get("cancelled") is True:
        return job

    # Completed benefit is authoritative and cannot be retroactively
    # converted into a free cancellation.
    if job.status == "completed":
        raise ProcessingJobCancellationTerminal(
            "AI operation has already completed."
        )

    # An unrelated failed job is already terminal. Its own failure path
    # is responsible for quota release.
    if job.status == "failed":
        raise ProcessingJobCancellationTerminal(
            "AI operation is already terminal."
        )

    current_result["cancelled"] = True
    current_result["cancel_requested"] = True
    current_result["cancel_reason"] = "user_cancelled"

    job.result = current_result
    job.status = "failed"
    job.error = "AI operation cancelled by user."

    feature_key = CANCELLABLE_AI_JOB_QUOTA_FEATURES[
        job.job_type
    ]

    if feature_key is not None:
        release_job_ai_quota_if_present(
            db=db,
            feature_key=feature_key,
            job_id=job.id,
            reason="user_cancelled",
        )

    # Cancellation state + quota release are committed together.
    db.commit()
    db.refresh(job)

    return job
