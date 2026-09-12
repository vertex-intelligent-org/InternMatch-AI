from uuid import uuid4

import pytest

from app.db.models import ProcessingJob
from app.services import processing_job_cancellation as cancellation
from app.services.processing_job_cancellation import (
    ProcessingJobCancellationNotFound,
    ProcessingJobCancellationTerminal,
    cancel_user_processing_job,
)
from tests.db import TestingSessionLocal


def _create_job(
    *,
    user_id,
    job_type="match_calculation",
    status="queued",
):
    db = TestingSessionLocal()

    try:
        job = ProcessingJob(
            user_id=user_id,
            job_type=job_type,
            status=status,
            progress_percent=0,
            result={},
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id
    finally:
        db.close()


def test_cancel_owned_active_job_is_durable_and_idempotent():
    user_id = uuid4()
    job_id = _create_job(user_id=user_id)

    db = TestingSessionLocal()

    try:
        cancelled = cancel_user_processing_job(
            db,
            job_id=job_id,
            user_id=user_id,
        )

        assert cancelled.status == "failed"
        assert cancelled.result["cancelled"] is True
        assert cancelled.result["cancel_requested"] is True
        assert cancelled.result["cancel_reason"] == "user_cancelled"

        replay = cancel_user_processing_job(
            db,
            job_id=job_id,
            user_id=user_id,
        )

        assert replay.id == job_id
        assert replay.result["cancelled"] is True
    finally:
        db.close()


def test_cancel_is_strictly_user_scoped():
    owner_id = uuid4()
    attacker_id = uuid4()
    job_id = _create_job(user_id=owner_id)

    db = TestingSessionLocal()

    try:
        with pytest.raises(
            ProcessingJobCancellationNotFound
        ):
            cancel_user_processing_job(
                db,
                job_id=job_id,
                user_id=attacker_id,
            )

        stored = db.get(
            ProcessingJob,
            job_id,
        )

        assert stored is not None
        assert stored.status == "queued"
    finally:
        db.close()


def test_completed_job_cannot_be_retroactively_cancelled():
    user_id = uuid4()
    job_id = _create_job(
        user_id=user_id,
        status="completed",
    )

    db = TestingSessionLocal()

    try:
        with pytest.raises(
            ProcessingJobCancellationTerminal
        ):
            cancel_user_processing_job(
                db,
                job_id=job_id,
                user_id=user_id,
            )

        stored = db.get(
            ProcessingJob,
            job_id,
        )

        assert stored is not None
        assert stored.status == "completed"
    finally:
        db.close()


def test_application_generation_cancel_releases_reserved_feature(
    monkeypatch,
):
    user_id = uuid4()
    job_id = _create_job(
        user_id=user_id,
        job_type="application_generation",
    )

    calls = []

    def fake_release(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        cancellation,
        "release_job_ai_quota_if_present",
        fake_release,
    )

    db = TestingSessionLocal()

    try:
        cancel_user_processing_job(
            db,
            job_id=job_id,
            user_id=user_id,
        )

        assert len(calls) == 1
        assert (
            calls[0].get("feature_key")
            or calls[0].get("feature")
        ) == "application_support"

        assert (
            calls[0].get("job_id")
            or calls[0].get("processing_job_id")
        ) == job_id

        assert calls[0]["reason"] == "user_cancelled"
    finally:
        db.close()
