from pathlib import Path
from uuid import uuid4

from app.db.models import ProcessingJob
from app.services import interview_prep_enqueue
from app.services import match_explanation_enqueue


def _processing_job_type_constraint_text() -> str:
    for constraint in ProcessingJob.__table__.constraints:
        if constraint.name == "ck_processing_jobs_job_type":
            return str(constraint.sqltext)

    raise AssertionError(
        "ck_processing_jobs_job_type constraint was not found."
    )


def test_processing_job_constraint_allows_part_c_types():
    sql = _processing_job_type_constraint_text()

    assert "match_explanation" in sql
    assert "interview_prep" in sql

    # Existing durable job types must not be lost.
    assert "cv_extraction" in sql
    assert "match_calculation" in sql
    assert "application_generation" in sql


def test_match_explanation_enqueue_uses_durable_job_id(monkeypatch):
    calls = []

    def fake_enqueue(task_path, *args, **kwargs):
        calls.append((task_path, args, kwargs))
        return object()

    monkeypatch.setattr(
        match_explanation_enqueue,
        "enqueue_with_backpressure",
        fake_enqueue,
    )

    job_id = uuid4()
    user_id = uuid4()
    match_id = uuid4()

    match_explanation_enqueue.enqueue_match_explanation_generation(
        job_id=job_id,
        user_id=user_id,
        match_id=match_id,
        content_locale="tr",
    )

    assert len(calls) == 1

    task_path, args, kwargs = calls[0]

    assert task_path == (
        "tasks.match_explanation_generation."
        "run_match_explanation_generation"
    )
    assert args == (
        str(job_id),
        str(user_id),
        str(match_id),
        "tr",
    )
    assert kwargs["job_id"] == str(job_id)
    assert kwargs["job_timeout"] == 180


def test_interview_prep_enqueue_uses_durable_job_id(monkeypatch):
    calls = []

    def fake_enqueue(task_path, *args, **kwargs):
        calls.append((task_path, args, kwargs))
        return object()

    monkeypatch.setattr(
        interview_prep_enqueue,
        "enqueue_with_backpressure",
        fake_enqueue,
    )

    job_id = uuid4()
    user_id = uuid4()
    application_id = uuid4()

    interview_prep_enqueue.enqueue_interview_prep_generation(
        job_id=job_id,
        user_id=user_id,
        application_id=application_id,
        content_locale="ar",
    )

    assert len(calls) == 1

    task_path, args, kwargs = calls[0]

    assert task_path == (
        "tasks.interview_prep_generation."
        "run_interview_prep_generation"
    )
    assert args == (
        str(job_id),
        str(user_id),
        str(application_id),
        "ar",
    )
    assert kwargs["job_id"] == str(job_id)
    assert kwargs["job_timeout"] == 180


def test_part_c_enqueue_rejects_invalid_locale(monkeypatch):
    called = []

    def fake_enqueue(*args, **kwargs):
        called.append(True)
        return object()

    monkeypatch.setattr(
        match_explanation_enqueue,
        "enqueue_with_backpressure",
        fake_enqueue,
    )
    monkeypatch.setattr(
        interview_prep_enqueue,
        "enqueue_with_backpressure",
        fake_enqueue,
    )

    job_id = uuid4()
    user_id = uuid4()

    try:
        match_explanation_enqueue.enqueue_match_explanation_generation(
            job_id=job_id,
            user_id=user_id,
            match_id=uuid4(),
            content_locale="xx",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid match locale was accepted.")

    try:
        interview_prep_enqueue.enqueue_interview_prep_generation(
            job_id=job_id,
            user_id=user_id,
            application_id=uuid4(),
            content_locale="xx",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid interview-prep locale was accepted.")

    assert called == []

def test_processing_job_migration_drops_legacy_and_canonical_constraints():
    migration = Path(
        "database/migrations/"
        "018_expand_processing_job_ai_types.sql"
    ).read_text(encoding="utf-8")

    assert (
        "DROP CONSTRAINT IF EXISTS "
        "processing_jobs_job_type_check"
        in migration
    )
    assert (
        "DROP CONSTRAINT IF EXISTS "
        "ck_processing_jobs_job_type"
        in migration
    )
    assert (
        "ADD CONSTRAINT "
        "ck_processing_jobs_job_type"
        in migration
    )

    assert "match_explanation" in migration
    assert "interview_prep" in migration
