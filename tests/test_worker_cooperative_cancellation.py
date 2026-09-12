from uuid import uuid4

from app.db.models import ProcessingJob
from tests.db import TestingSessionLocal
import tasks.application_generation as application_task
import tasks.match_calculation as match_task


def _create_cancelled_job(*, user_id, job_type):
    db = TestingSessionLocal()

    try:
        job = ProcessingJob(
            user_id=user_id,
            job_type=job_type,
            status="failed",
            progress_percent=100,
            result={
                "cancelled": True,
                "cancel_requested": True,
                "cancel_reason": "user_cancelled",
            },
            error="AI operation cancelled by user.",
        )

        db.add(job)
        db.commit()
        db.refresh(job)

        return job.id
    finally:
        db.close()


def test_application_worker_never_restarts_cancelled_job(monkeypatch):
    user_id = uuid4()

    job_id = _create_cancelled_job(
        user_id=user_id,
        job_type="application_generation",
    )

    monkeypatch.setattr(
        application_task,
        "SessionLocal",
        TestingSessionLocal,
    )

    result = application_task.run_application_generation(
        str(job_id),
        str(user_id),
        str(uuid4()),
        "professional",
        "en",
    )

    assert result == {
        "job_id": str(job_id),
        "status": "cancelled",
    }

    db = TestingSessionLocal()

    try:
        stored = db.get(
            ProcessingJob,
            job_id,
        )

        assert stored is not None
        assert stored.status == "failed"
        assert stored.result["cancelled"] is True
    finally:
        db.close()


def test_match_worker_never_restarts_cancelled_job(monkeypatch):
    user_id = uuid4()

    job_id = _create_cancelled_job(
        user_id=user_id,
        job_type="match_calculation",
    )

    monkeypatch.setattr(
        match_task,
        "SessionLocal",
        TestingSessionLocal,
    )

    result = match_task.run_match_calculation(
        str(job_id),
        str(user_id),
        50,
    )

    assert result == {
        "job_id": str(job_id),
        "status": "cancelled",
    }

    db = TestingSessionLocal()

    try:
        stored = db.get(
            ProcessingJob,
            job_id,
        )

        assert stored is not None
        assert stored.status == "failed"
        assert stored.result["cancelled"] is True
    finally:
        db.close()


def test_worker_sources_serialize_cancel_vs_completion():
    application = open(
        "worker/tasks/application_generation.py",
        encoding="utf-8",
    ).read()

    matching = open(
        "worker/tasks/match_calculation.py",
        encoding="utf-8",
    ).read()

    for source in (application, matching):
        assert "_job_cancel_requested" in source
        assert "_lock_active_job_or_cancel" in source

        final_lock = source.rfind(
            "job = _lock_active_job_or_cancel("
        )

        completed = source.rfind(
            'job.status = "completed"'
        )

        assert final_lock != -1
        assert completed != -1
        assert final_lock < completed

        assert (
            "if fail_job and not "
            "_job_cancel_requested(fail_job):"
            in source
        )

    assert (
        "ApplicationGenerationCancelled"
        in application
    )

    assert (
        "MatchCalculationCancelled"
        in matching
    )
