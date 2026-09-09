from uuid import uuid4

import worker as worker_module
from rq.exceptions import AbandonedJobError


class _FakeRQJob:
    def __init__(self, job_id):
        self.id = str(job_id)
        self.kwargs = {}


class _FakeProcessingJob:
    def __init__(
        self,
        *,
        job_id,
        job_type="cv_extraction",
        status="queued",
    ):
        self.id = job_id
        self.job_type = job_type
        self.status = status
        self.progress_percent = 0
        self.result = {"stale": True}
        self.error = None


class _FakeSession:
    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_abandoned_cv_job_marks_failed_and_releases_quota(
    monkeypatch,
):
    job_id = uuid4()
    processing_job = _FakeProcessingJob(job_id=job_id)
    session = _FakeSession()
    releases = []

    monkeypatch.setattr(
        worker_module,
        "SessionLocal",
        lambda: session,
    )
    monkeypatch.setattr(
        worker_module.ProcessingJobRepository,
        "get_by_id",
        lambda db, requested_job_id: (
            processing_job
            if requested_job_id == job_id
            else None
        ),
    )

    def fake_release(
        db,
        *,
        feature_key,
        job_id,
        reason,
    ):
        releases.append(
            {
                "db": db,
                "feature_key": feature_key,
                "job_id": job_id,
                "reason": reason,
            }
        )
        return {"outcome": "released"}

    monkeypatch.setattr(
        worker_module,
        "release_job_ai_quota_if_present",
        fake_release,
    )

    result = worker_module._recover_abandoned_processing_job(
        _FakeRQJob(job_id),
        AbandonedJobError,
        AbandonedJobError(),
        [],
    )

    assert result is True
    assert processing_job.status == "failed"
    assert processing_job.progress_percent == 100
    assert processing_job.result is None
    assert processing_job.error == (
        "Background processing was interrupted before completion."
    )

    assert releases == [
        {
            "db": session,
            "feature_key": worker_module.FEATURE_CV_ANALYSIS,
            "job_id": job_id,
            "reason": "rq_abandoned_job",
        }
    ]

    assert session.committed is True
    assert session.rolled_back is False
    assert session.closed is True


def test_abandoned_application_job_releases_application_quota(
    monkeypatch,
):
    job_id = uuid4()
    processing_job = _FakeProcessingJob(
        job_id=job_id,
        job_type="application_generation",
        status="processing",
    )
    session = _FakeSession()
    released_features = []

    monkeypatch.setattr(
        worker_module,
        "SessionLocal",
        lambda: session,
    )
    monkeypatch.setattr(
        worker_module.ProcessingJobRepository,
        "get_by_id",
        lambda db, requested_job_id: processing_job,
    )
    monkeypatch.setattr(
        worker_module,
        "release_job_ai_quota_if_present",
        lambda db, *, feature_key, job_id, reason: (
            released_features.append(feature_key)
            or {"outcome": "released"}
        ),
    )

    worker_module._recover_abandoned_processing_job(
        _FakeRQJob(job_id),
        AbandonedJobError,
        AbandonedJobError(),
        [],
    )

    assert processing_job.status == "failed"
    assert released_features == [
        worker_module.FEATURE_APPLICATION_SUPPORT
    ]
    assert session.committed is True
    assert session.closed is True


def test_non_abandoned_exception_does_not_touch_database(
    monkeypatch,
):
    called = {"session": False}

    def forbidden_session():
        called["session"] = True
        raise AssertionError("Session must not be opened")

    monkeypatch.setattr(
        worker_module,
        "SessionLocal",
        forbidden_session,
    )

    result = worker_module._recover_abandoned_processing_job(
        _FakeRQJob(uuid4()),
        RuntimeError,
        RuntimeError("ordinary failure"),
        [],
    )

    assert result is True
    assert called["session"] is False


def test_completed_abandoned_job_is_not_reopened_or_released(
    monkeypatch,
):
    job_id = uuid4()
    processing_job = _FakeProcessingJob(
        job_id=job_id,
        status="completed",
    )
    session = _FakeSession()

    monkeypatch.setattr(
        worker_module,
        "SessionLocal",
        lambda: session,
    )
    monkeypatch.setattr(
        worker_module.ProcessingJobRepository,
        "get_by_id",
        lambda db, requested_job_id: processing_job,
    )

    def forbidden_release(*args, **kwargs):
        raise AssertionError(
            "Completed job quota must not be released"
        )

    monkeypatch.setattr(
        worker_module,
        "release_job_ai_quota_if_present",
        forbidden_release,
    )

    result = worker_module._recover_abandoned_processing_job(
        _FakeRQJob(job_id),
        AbandonedJobError,
        AbandonedJobError(),
        [],
    )

    assert result is True
    assert processing_job.status == "completed"
    assert session.committed is False
    assert session.closed is True


def test_abandoned_recovery_uses_rq_job_id_without_kwargs(
    monkeypatch,
):
    job_id = uuid4()
    processing_job = _FakeProcessingJob(job_id=job_id)
    session = _FakeSession()
    released = []

    monkeypatch.setattr(
        worker_module,
        "SessionLocal",
        lambda: session,
    )

    monkeypatch.setattr(
        worker_module.ProcessingJobRepository,
        "get_by_id",
        lambda db, requested_job_id: (
            processing_job
            if requested_job_id == job_id
            else None
        ),
    )

    monkeypatch.setattr(
        worker_module,
        "release_job_ai_quota_if_present",
        lambda db, *, feature_key, job_id, reason: (
            released.append(
                (feature_key, job_id, reason)
            )
            or {"outcome": "released"}
        ),
    )

    rq_job = _FakeRQJob(job_id)

    assert rq_job.kwargs == {}

    result = (
        worker_module._recover_abandoned_processing_job(
            rq_job,
            AbandonedJobError,
            AbandonedJobError(),
            [],
        )
    )

    assert result is True
    assert processing_job.status == "failed"
    assert released == [
        (
            worker_module.FEATURE_CV_ANALYSIS,
            job_id,
            "rq_abandoned_job",
        )
    ]
    assert session.committed is True


def test_windows_worker_implementation_is_available():
    assert worker_module.SimpleWorker is not None
