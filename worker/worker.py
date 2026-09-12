"""
InternMatch AI — Background RQ Worker Entrypoint
Authors: Mohammad & Selen (AISS Club — Üsküdar University)
"""

import importlib
import logging
import sys
from uuid import UUID

from app.core.config import settings, validate_production_config
from app.db.session import SessionLocal
from app.repositories.processing_job import ProcessingJobRepository
from app.services.ai_quota import (
    FEATURE_APPLICATION_SUPPORT,
    FEATURE_CV_ANALYSIS,
)
from app.services.ai_quota_integration import (
    release_job_ai_quota_if_present,
)
from config import worker_settings
from redis import Redis
from rq import Queue, SimpleWorker, Worker
from rq.exceptions import AbandonedJobError

logging.basicConfig(
    level=getattr(logging, worker_settings.LOG_LEVEL.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] [internmatch_worker]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("internmatch_worker")

REDIS_URL = worker_settings.REDIS_URL
QUEUES = worker_settings.queue_list

_PRELOAD_JOB_MODULES = (
    "tasks.application_generation",
    "tasks.cv_extraction",
    "tasks.match_explanation_generation",
    "tasks.interview_prep_generation",
)


def _preload_job_modules() -> None:
    """Load measured heavy job modules before RQ forks work horses."""

    for module_name in _PRELOAD_JOB_MODULES:
        importlib.import_module(module_name)


def _recover_abandoned_processing_job(
    job,
    exc_type,
    exc_value,
    traceback,
):
    """Recover durable job/quota state when RQ abandons a work horse."""

    if exc_type is not AbandonedJobError:
        return True

    raw_job_id = getattr(job, "id", None)

    if raw_job_id is None:
        kwargs = getattr(job, "kwargs", None) or {}
        raw_job_id = kwargs.get("job_id")

    if raw_job_id is None:
        return True

    try:
        processing_job_id = UUID(str(raw_job_id))
    except (TypeError, ValueError):
        logger.warning(
            "Skipping abandoned-job recovery for invalid processing job id."
        )
        return True

    db = SessionLocal()

    try:
        processing_job = ProcessingJobRepository.get_by_id(
            db,
            processing_job_id,
        )

        if processing_job is None:
            return True

        if processing_job.status == "completed":
            return True

        if processing_job.status in {"queued", "processing"}:
            processing_job.status = "failed"
            processing_job.progress_percent = 100
            processing_job.result = None
            processing_job.error = (
                "Background processing was interrupted before completion."
            )

        feature_by_job_type = {
            "cv_extraction": FEATURE_CV_ANALYSIS,
            "application_generation": FEATURE_APPLICATION_SUPPORT,
        }

        feature_key = feature_by_job_type.get(
            processing_job.job_type
        )

        if feature_key is not None:
            release_job_ai_quota_if_present(
                db,
                feature_key=feature_key,
                job_id=processing_job_id,
                reason="rq_abandoned_job",
            )

        db.commit()

        logger.warning(
            "Recovered abandoned processing job %s (%s).",
            processing_job_id,
            processing_job.job_type,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "Failed to reconcile abandoned processing job %s.",
            processing_job_id,
        )
    finally:
        db.close()

    # Allow any additional configured RQ exception handlers to run.
    return True


def run_worker():
    """Initialize Redis connection and start RQ worker loop."""
    logger.info("Initializing Python RQ worker foundation...")
    # Validate production configuration before attempting network operations
    validate_production_config(settings)

    _preload_job_modules()
    logger.info(
        "Preloaded RQ job modules before fork: %s",
        ", ".join(_PRELOAD_JOB_MODULES),
    )

    try:
        redis_conn = Redis.from_url(REDIS_URL)
        redis_conn.ping()
        logger.info("Successfully connected to Redis instance.")
    except Exception:
        logger.error("Failed to connect to Redis.")
        sys.exit(1)

    queues = [Queue(name, connection=redis_conn) for name in QUEUES]
    worker_class = (
        SimpleWorker
        if sys.platform == "win32"
        else Worker
    )

    logger.info(
        "Using RQ worker class: %s",
        worker_class.__name__,
    )

    worker = worker_class(
        queues,
        connection=redis_conn,
        exception_handlers=[_recover_abandoned_processing_job],
    )
    logger.info(f"Worker active listening on queues: {QUEUES}")
    worker.work()


if __name__ == "__main__":
    run_worker()
