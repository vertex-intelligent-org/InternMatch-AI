"""
Backend Interview Preparation Enqueue Service.

Provides the Redis/RQ boundary for durable, cancellable interview-preparation
generation jobs.
"""

from typing import Any
from uuid import UUID

from app.services.rq_enqueue import enqueue_with_backpressure


def enqueue_interview_prep_generation(
    job_id: UUID,
    user_id: UUID,
    application_id: UUID,
    content_locale: str = "en",
) -> Any:
    """
    Dispatch one durable interview-preparation generation job.

    UUID values are serialized so the RQ payload remains durable and portable.
    The ProcessingJob id is also used as the RQ job id.
    """
    locale = (content_locale or "en").strip().lower()

    if locale not in {"en", "tr", "ar"}:
        raise ValueError(
            f"Unsupported interview preparation locale: {content_locale!r}"
        )

    task_path = (
        "tasks.interview_prep_generation."
        "run_interview_prep_generation"
    )

    return enqueue_with_backpressure(
        task_path,
        str(job_id),
        str(user_id),
        str(application_id),
        locale,
        job_id=str(job_id),
        job_timeout=180,
    )
