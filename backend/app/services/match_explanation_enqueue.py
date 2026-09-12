"""
Backend Match Explanation Enqueue Service.

Provides the Redis/RQ boundary for durable, cancellable Why You Match
generation jobs.
"""

from typing import Any
from uuid import UUID

from app.services.rq_enqueue import enqueue_with_backpressure


def enqueue_match_explanation_generation(
    job_id: UUID,
    user_id: UUID,
    match_id: UUID,
    content_locale: str = "en",
) -> Any:
    """
    Dispatch one durable match-explanation generation job.

    UUID values are serialized so the RQ payload remains durable and portable.
    The ProcessingJob id is also used as the RQ job id.
    """
    locale = (content_locale or "en").strip().lower()

    if locale not in {"en", "tr", "ar"}:
        raise ValueError(
            f"Unsupported match explanation locale: {content_locale!r}"
        )

    task_path = (
        "tasks.match_explanation_generation."
        "run_match_explanation_generation"
    )

    return enqueue_with_backpressure(
        task_path,
        str(job_id),
        str(user_id),
        str(match_id),
        locale,
        job_id=str(job_id),
        job_timeout=180,
    )
