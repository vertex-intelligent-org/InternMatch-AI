"""
Shared cancellation/completion authority for durable AI generation workers.
"""

from uuid import UUID

from app.repositories.processing_job import ProcessingJobRepository


class DurableAIGenerationCancelled(Exception):
    """Raised when authoritative user cancellation wins the job race."""


def job_cancel_requested(job: object | None) -> bool:
    if job is None:
        return False

    result = getattr(job, "result", None)
    result_dict = result if isinstance(result, dict) else {}

    return (
        getattr(job, "status", None) == "failed"
        and result_dict.get("cancelled") is True
    )


def lock_active_job_or_cancel(
    db,
    *,
    job_id: UUID,
    user_id: UUID,
    expected_job_type: str,
):
    """
    Serialize worker continuation/finalization against HTTP cancellation.

    First row-lock winner is authoritative.
    """
    job = ProcessingJobRepository.get_by_id_and_user_id_for_update(
        db=db,
        job_id=job_id,
        user_id=user_id,
    )

    if job is None:
        raise ValueError(
            f"ProcessingJob {job_id} not found for user {user_id}."
        )

    db.refresh(job)

    if job.job_type != expected_job_type:
        raise ValueError(
            "ProcessingJob type mismatch: "
            f"expected {expected_job_type!r}, got {job.job_type!r}."
        )

    if job_cancel_requested(job):
        raise DurableAIGenerationCancelled()

    return job


def serialize_response(response: object) -> dict:
    model_dump = getattr(response, "model_dump", None)

    if not callable(model_dump):
        raise TypeError("Durable AI response is not serializable.")

    payload = model_dump(mode="json")

    if not isinstance(payload, dict):
        raise TypeError("Durable AI response did not serialize to an object.")

    return payload


def prepare_job_completion(
    db,
    *,
    job_id: UUID,
    user_id: UUID,
    expected_job_type: str,
    response: object,
) -> dict:
    """
    Lock and stage completed job state without committing.

    Fresh-generation services invoke this immediately before quota settlement.
    Their subsequent commit therefore atomically publishes the user benefit,
    quota settlement, and completed ProcessingJob state.
    """
    job = lock_active_job_or_cancel(
        db,
        job_id=job_id,
        user_id=user_id,
        expected_job_type=expected_job_type,
    )

    payload = serialize_response(response)

    if job.status == "completed":
        existing = job.result if isinstance(job.result, dict) else None

        if existing is not None:
            return existing

    job.status = "completed"
    job.progress_percent = 100
    job.result = payload
    job.error = None

    return payload
