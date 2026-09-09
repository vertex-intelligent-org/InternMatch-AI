"""
Backend Application Generation Enqueue Service
Provides Redis/RQ enqueue boundary for dispatching application generation jobs.
"""

from typing import Any
from uuid import UUID

from app.services.rq_enqueue import enqueue_with_backpressure


def enqueue_application_generation(
    job_id: UUID,
    user_id: UUID,
    match_id: UUID,
    tone: str,
    content_locale: str = "en",
) -> Any:
    """
    Enqueue application generation task to default RQ queue.
    Passes worker task positional arguments as durable strings and specifies
    RQ job_id keyword.
    """
    task_path = "tasks.application_generation.run_application_generation"
    rq_job = enqueue_with_backpressure(
        task_path,
        str(job_id),
        str(user_id),
        str(match_id),
        str(tone),
        str(content_locale),
        job_id=str(job_id),
        job_timeout=180,
    )
    return rq_job
