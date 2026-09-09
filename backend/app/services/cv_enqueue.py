"""
Backend CV Extraction Enqueue Service
Provides small Redis/RQ enqueue boundary for dispatching CV extraction jobs.
"""

from typing import Any
from uuid import UUID

from app.services.rq_enqueue import enqueue_with_backpressure


def enqueue_cv_extraction(
    job_id: UUID,
    user_id: UUID,
    storage_path: str,
    content_locale: str = "en",
) -> Any:
    """
    Enqueue CV extraction task to default RQ queue.
    Validates inputs and passes positional arguments as durable primitive strings.
    Specifies RQ job_id keyword parameter for job tracking.
    """
    if not isinstance(job_id, UUID):
        raise ValueError("job_id must be a valid UUID")

    if not isinstance(user_id, UUID):
        raise ValueError("user_id must be a valid UUID")

    clean_path = storage_path.strip() if isinstance(storage_path, str) else ""
    if not clean_path:
        raise ValueError("storage_path cannot be empty")

    clean_locale = content_locale.strip() if isinstance(content_locale, str) else "en"
    if not clean_locale:
        clean_locale = "en"

    task_path = "tasks.cv_extraction.run_cv_extraction"
    rq_job = enqueue_with_backpressure(
        task_path,
        str(job_id),
        str(user_id),
        clean_path,
        clean_locale,
        job_id=str(job_id),
        job_timeout=180,
    )
    return rq_job
