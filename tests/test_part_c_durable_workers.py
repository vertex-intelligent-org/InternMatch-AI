from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.services import ai_generation_quota
from tasks import durable_ai_generation


class FakeDB:
    def __init__(self):
        self.refresh_count = 0

    def refresh(self, job):
        self.refresh_count += 1


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def model_dump(self, *, mode):
        assert mode == "json"
        return dict(self.payload)


def test_completion_barrier_rejects_cancellation_first(monkeypatch):
    job_id = uuid4()
    user_id = uuid4()

    cancelled_job = SimpleNamespace(
        id=job_id,
        user_id=user_id,
        job_type="match_explanation",
        status="failed",
        progress_percent=100,
        result={
            "cancelled": True,
            "cancel_requested": True,
        },
        error="AI processing cancelled by user.",
    )

    monkeypatch.setattr(
        durable_ai_generation.ProcessingJobRepository,
        "get_by_id_and_user_id_for_update",
        lambda **kwargs: cancelled_job,
    )

    db = FakeDB()

    with pytest.raises(
        durable_ai_generation.DurableAIGenerationCancelled
    ):
        durable_ai_generation.prepare_job_completion(
            db,
            job_id=job_id,
            user_id=user_id,
            expected_job_type="match_explanation",
            response=FakeResponse({"benefit": "must-not-publish"}),
        )

    assert cancelled_job.status == "failed"
    assert cancelled_job.result["cancelled"] is True
    assert "benefit" not in cancelled_job.result
    assert db.refresh_count == 1


def test_completion_barrier_stages_result_before_commit(monkeypatch):
    job_id = uuid4()
    user_id = uuid4()

    active_job = SimpleNamespace(
        id=job_id,
        user_id=user_id,
        job_type="interview_prep",
        status="processing",
        progress_percent=10,
        result=None,
        error=None,
    )

    monkeypatch.setattr(
        durable_ai_generation.ProcessingJobRepository,
        "get_by_id_and_user_id_for_update",
        lambda **kwargs: active_job,
    )

    db = FakeDB()

    payload = durable_ai_generation.prepare_job_completion(
        db,
        job_id=job_id,
        user_id=user_id,
        expected_job_type="interview_prep",
        response=FakeResponse(
            {
                "application_id": str(uuid4()),
                "preparation_summary": "Grounded prep",
            }
        ),
    )

    assert active_job.status == "completed"
    assert active_job.progress_percent == 100
    assert active_job.result == payload
    assert active_job.error is None
    assert db.refresh_count == 1


def test_async_quota_reservation_reuses_existing_job_operation(
    monkeypatch,
):
    job_id = uuid4()
    user_id = uuid4()
    operation = SimpleNamespace(id=uuid4())

    ensure_calls = []
    reserve_calls = []

    def fake_ensure(db, **kwargs):
        ensure_calls.append(kwargs)
        return {
            "outcome": "existing_reserved",
            "operation": operation,
        }

    def fake_reserve(db, **kwargs):
        reserve_calls.append(kwargs)
        raise AssertionError("duplicate durable reservation attempted")

    monkeypatch.setattr(
        ai_generation_quota,
        "ensure_job_ai_quota_reserved_if_present",
        fake_ensure,
    )
    monkeypatch.setattr(
        ai_generation_quota,
        "reserve_job_ai_quota",
        fake_reserve,
    )

    result = ai_generation_quota.reserve_generation_ai_quota(
        object(),
        user_id=user_id,
        feature_key="match_explanation",
        idempotency_key="sync-key-is-unused-for-job",
        request_fingerprint="sync-fingerprint-is-unused-for-job",
        processing_job_id=job_id,
    )

    assert result["operation"] is operation
    assert len(ensure_calls) == 1
    assert reserve_calls == []


def test_async_quota_reservation_creates_only_when_missing(
    monkeypatch,
):
    job_id = uuid4()
    user_id = uuid4()
    reserve_calls = []

    monkeypatch.setattr(
        ai_generation_quota,
        "ensure_job_ai_quota_reserved_if_present",
        lambda db, **kwargs: None,
    )

    def fake_reserve(db, **kwargs):
        reserve_calls.append(kwargs)
        return {
            "outcome": "reserved",
            "operation": SimpleNamespace(id=uuid4()),
        }

    monkeypatch.setattr(
        ai_generation_quota,
        "reserve_job_ai_quota",
        fake_reserve,
    )

    ai_generation_quota.reserve_generation_ai_quota(
        object(),
        user_id=user_id,
        feature_key="interview_prep",
        idempotency_key="unused",
        request_fingerprint="unused",
        processing_job_id=job_id,
    )

    assert len(reserve_calls) == 1
    assert reserve_calls[0]["job_id"] == job_id
    assert reserve_calls[0]["user_id"] == user_id
    assert reserve_calls[0]["feature_key"] == "interview_prep"


def test_async_settle_and_release_are_job_scoped(monkeypatch):
    job_id = uuid4()
    operation_id = uuid4()

    settled = []
    released = []

    monkeypatch.setattr(
        ai_generation_quota,
        "settle_job_ai_quota_if_present",
        lambda db, **kwargs: settled.append(kwargs) or {},
    )

    monkeypatch.setattr(
        ai_generation_quota,
        "release_job_ai_quota_if_present",
        lambda db, **kwargs: released.append(kwargs) or {},
    )

    ai_generation_quota.settle_generation_ai_quota(
        object(),
        feature_key="match_explanation",
        operation_id=operation_id,
        processing_job_id=job_id,
    )

    ai_generation_quota.release_generation_ai_quota(
        object(),
        feature_key="match_explanation",
        operation_id=operation_id,
        processing_job_id=job_id,
        reason="user_cancelled",
    )

    assert settled == [
        {
            "feature_key": "match_explanation",
            "job_id": job_id,
        }
    ]

    assert released == [
        {
            "feature_key": "match_explanation",
            "job_id": job_id,
            "reason": "user_cancelled",
        }
    ]


def test_sync_quota_adapter_preserves_existing_path(monkeypatch):
    operation_id = uuid4()
    user_id = uuid4()

    reserved = []
    settled = []
    released = []

    monkeypatch.setattr(
        ai_generation_quota,
        "reserve_sync_ai_quota",
        lambda db, **kwargs: reserved.append(kwargs)
        or {"operation": SimpleNamespace(id=operation_id)},
    )

    monkeypatch.setattr(
        ai_generation_quota,
        "settle_sync_ai_quota",
        lambda db, **kwargs: settled.append(kwargs) or {},
    )

    monkeypatch.setattr(
        ai_generation_quota,
        "release_sync_ai_quota",
        lambda db, **kwargs: released.append(kwargs) or {},
    )

    ai_generation_quota.reserve_generation_ai_quota(
        object(),
        user_id=user_id,
        feature_key="interview_prep",
        idempotency_key="sync-key",
        request_fingerprint="sync-fingerprint",
        processing_job_id=None,
    )

    ai_generation_quota.settle_generation_ai_quota(
        object(),
        feature_key="interview_prep",
        operation_id=operation_id,
        processing_job_id=None,
    )

    ai_generation_quota.release_generation_ai_quota(
        object(),
        feature_key="interview_prep",
        operation_id=operation_id,
        processing_job_id=None,
        reason="provider_failure",
    )

    assert reserved == [
        {
            "user_id": user_id,
            "feature_key": "interview_prep",
            "idempotency_key": "sync-key",
            "request_fingerprint": "sync-fingerprint",
        }
    ]
    assert settled == [{"operation_id": operation_id}]
    assert released == [
        {
            "operation_id": operation_id,
            "reason": "provider_failure",
        }
    ]


def test_service_source_places_completion_barrier_before_settlement():
    root = Path(__file__).resolve().parents[1]

    match_source = (
        root / "backend/app/services/match_explanation.py"
    ).read_text(encoding="utf-8")

    interview_source = (
        root / "backend/app/services/interview_prep.py"
    ).read_text(encoding="utf-8")

    # Count actual indented call sites only. A raw substring search would
    # incorrectly include the helper function definition itself.
    match_lines = match_source.splitlines()

    match_callbacks = [
        line_number
        for line_number, line in enumerate(match_lines)
        if line.strip() == "before_async_finalize(response_payload)"
    ]

    match_settles = [
        line_number
        for line_number, line in enumerate(match_lines)
        if line.strip() == "_settle_match_quota("
    ]

    assert len(match_callbacks) == 2
    assert len(match_settles) == 2
    assert match_callbacks[0] < match_settles[0]
    assert match_callbacks[1] < match_settles[1]

    interview_lines = interview_source.splitlines()

    interview_callbacks = [
        line_number
        for line_number, line in enumerate(interview_lines)
        if line.strip() == "before_async_finalize(response_payload)"
    ]

    interview_settles = [
        line_number
        for line_number, line in enumerate(interview_lines)
        if line.strip() == "_settle_interview_quota("
    ]

    assert len(interview_callbacks) == 1
    assert len(interview_settles) == 1
    assert interview_callbacks[0] < interview_settles[0]


def test_worker_source_uses_durable_job_identity_and_finalizer():
    root = Path(__file__).resolve().parents[1]

    match_worker = (
        root / "worker/tasks/match_explanation_generation.py"
    ).read_text(encoding="utf-8")

    interview_worker = (
        root / "worker/tasks/interview_prep_generation.py"
    ).read_text(encoding="utf-8")

    for source in (match_worker, interview_worker):
        assert "processing_job_id=norm_job_id" in source
        assert "before_async_finalize=finalize_response" in source
        assert "prepare_job_completion(" in source
        assert "lock_active_job_or_cancel(" in source
        assert 'reason="user_cancelled"' in source
