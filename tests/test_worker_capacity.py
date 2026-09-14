"""Worker queue capacity and horizontal-scaling regression guards."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from app.services import rq_enqueue


class FakeLock:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRedis:
    def lock(
        self,
        key,
        *,
        timeout,
        blocking_timeout,
    ):
        assert key == rq_enqueue.QUEUE_CAPACITY_LOCK_KEY
        assert timeout == 5
        assert blocking_timeout == 2
        return FakeLock()


class FakeQueue:
    def __init__(self, pending: int):
        self.count = pending
        self.enqueue_calls = []

    def enqueue(
        self,
        task_path,
        *args,
        job_id,
        job_timeout,
    ):
        self.enqueue_calls.append(
            {
                "task_path": task_path,
                "args": args,
                "job_id": job_id,
                "job_timeout": job_timeout,
            }
        )
        return SimpleNamespace(id=job_id)


def test_queue_accepts_burst_below_default_capacity(monkeypatch):
    fake_redis = FakeRedis()
    fake_queue = FakeQueue(
        rq_enqueue.DEFAULT_MAX_PENDING_JOBS - 1
    )

    monkeypatch.delenv(
        "RQ_MAX_PENDING_JOBS",
        raising=False,
    )
    monkeypatch.setattr(
        rq_enqueue.Redis,
        "from_url",
        lambda *args, **kwargs: fake_redis,
    )
    monkeypatch.setattr(
        rq_enqueue,
        "Queue",
        lambda connection: fake_queue,
    )

    result = rq_enqueue.enqueue_with_backpressure(
        "tasks.cv_extraction.run_cv_extraction",
        "job-1",
        "user-1",
        "path.pdf",
        "en",
        job_id="job-1",
        job_timeout=180,
    )

    assert result.id == "job-1"
    assert len(fake_queue.enqueue_calls) == 1


def test_queue_rejects_at_capacity_without_enqueue(monkeypatch):
    fake_redis = FakeRedis()
    fake_queue = FakeQueue(
        rq_enqueue.DEFAULT_MAX_PENDING_JOBS
    )

    monkeypatch.delenv(
        "RQ_MAX_PENDING_JOBS",
        raising=False,
    )
    monkeypatch.setattr(
        rq_enqueue.Redis,
        "from_url",
        lambda *args, **kwargs: fake_redis,
    )
    monkeypatch.setattr(
        rq_enqueue,
        "Queue",
        lambda connection: fake_queue,
    )

    with pytest.raises(
        rq_enqueue.QueueBackpressureError
    ):
        rq_enqueue.enqueue_with_backpressure(
            "tasks.cv_extraction.run_cv_extraction",
            "job-2",
            "user-2",
            "path.pdf",
            "en",
            job_id="job-2",
            job_timeout=180,
        )

    assert fake_queue.enqueue_calls == []


def test_queue_limit_is_configurable_but_bounded(monkeypatch):
    monkeypatch.setenv(
        "RQ_MAX_PENDING_JOBS",
        "60",
    )
    assert rq_enqueue._max_pending_jobs() == 60

    monkeypatch.setenv(
        "RQ_MAX_PENDING_JOBS",
        "0",
    )
    with pytest.raises(RuntimeError):
        rq_enqueue._max_pending_jobs()

    monkeypatch.setenv(
        "RQ_MAX_PENDING_JOBS",
        "not-a-number",
    )
    with pytest.raises(RuntimeError):
        rq_enqueue._max_pending_jobs()


def test_enqueue_services_do_not_configure_automatic_rq_retry():
    root = Path(__file__).resolve().parents[1]

    files = (
        root / "backend" / "app" / "services" / "cv_enqueue.py",
        root / "backend" / "app" / "services" / "application_enqueue.py",
        root / "backend" / "app" / "services" / "match_enqueue.py",
        root / "backend" / "app" / "services" / "rq_enqueue.py",
    )

    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in files
    )

    assert "Retry(" not in source
    assert "retry=" not in source


def test_compose_worker_can_be_scaled_horizontally():
    root = Path(__file__).resolve().parents[1]
    compose = (
        root / "docker-compose.yml"
    ).read_text(encoding="utf-8")

    worker_block = compose.split(
        "  worker:",
        1,
    )[1].split(
        "  redis:",
        1,
    )[0]

    assert "container_name:" not in worker_block
