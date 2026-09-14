"""Shared RQ enqueue boundary with bounded queue backpressure."""

from __future__ import annotations

import os
from typing import Any

from redis import Redis
from rq import Queue

from app.core.config import settings

DEFAULT_MAX_PENDING_JOBS = 120
MIN_MAX_PENDING_JOBS = 1
MAX_MAX_PENDING_JOBS = 10_000
QUEUE_CAPACITY_LOCK_KEY = "internmatch:rq:enqueue-capacity"


class QueueBackpressureError(RuntimeError):
    """Raised when the shared RQ queue has reached its configured pending limit."""


def _max_pending_jobs() -> int:
    raw = os.getenv(
        "RQ_MAX_PENDING_JOBS",
        str(DEFAULT_MAX_PENDING_JOBS),
    ).strip()

    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            "RQ_MAX_PENDING_JOBS must be an integer."
        ) from exc

    if not MIN_MAX_PENDING_JOBS <= value <= MAX_MAX_PENDING_JOBS:
        raise RuntimeError(
            "RQ_MAX_PENDING_JOBS must be between "
            f"{MIN_MAX_PENDING_JOBS} and {MAX_MAX_PENDING_JOBS}."
        )

    return value


def enqueue_with_backpressure(
    task_path: str,
    *args: object,
    job_id: str,
    job_timeout: int = 180,
) -> Any:
    """
    Enqueue one durable RQ job while bounding pending queue growth.

    The short Redis lock makes the pending-count check and enqueue decision
    deterministic across simultaneous API requests. It does not cover worker
    execution and therefore does not serialize background processing.

    Automatic RQ retry is intentionally not configured. Provider failover and
    durable request/job idempotency own retry semantics.
    """
    if not isinstance(task_path, str) or not task_path.strip():
        raise ValueError("task_path cannot be empty")

    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("job_id cannot be empty")

    if job_timeout <= 0:
        raise ValueError("job_timeout must be greater than zero")

    redis_conn = Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=2,
        socket_timeout=2,
    )

    queue = Queue(connection=redis_conn)
    max_pending = _max_pending_jobs()

    lock = redis_conn.lock(
        QUEUE_CAPACITY_LOCK_KEY,
        timeout=5,
        blocking_timeout=2,
    )

    with lock:
        pending = queue.count

        if pending >= max_pending:
            raise QueueBackpressureError(
                "Background processing queue is temporarily at capacity."
            )

        return queue.enqueue(
            task_path,
            *args,
            job_id=job_id,
            job_timeout=job_timeout,
        )
