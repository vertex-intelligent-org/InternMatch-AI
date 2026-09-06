"""
Worker Task Foundation Tests
Verifies task module imports, ping_task execution, job_state persistence helper,
and run_match_calculation RQ task lifecycle.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

# Add worker directory to path for test execution
worker_dir = Path(__file__).parent.parent / "worker"
if str(worker_dir) not in sys.path:
    sys.path.insert(0, str(worker_dir))

from app.db.models import (  # noqa: E402
    EducationEntry,
    InternshipListing,
    Match,
    ProcessingJob,  # noqa: E402
    StudentProfile,
    StudentSkill,
)
from app.db.session import Base  # noqa: E402
from app.repositories.processing_job import ProcessingJobRepository  # noqa: E402
from app.services.cv_profile_extraction import (  # noqa: E402
    ExtractedCandidateProfile,
    ExtractedEducation,
    ExtractedExperience,
    ExtractedPreferences,
    ExtractedProject,
    ExtractedSkill,
)
from app.services.cv_validation import (  # noqa: E402
    CVValidationResult,
    CVValidationServiceError,
    InvalidCVDocumentError,
)
from app.services.match_calculation import (  # noqa: E402
    MatchCalculationPreconditionError,
)
from tasks.cv_extraction import (  # noqa: E402
    _publish_progress,
    run_cv_extraction,
)
from tasks.example_task import ping_task  # noqa: E402
from tasks.job_state import update_job_state  # noqa: E402
from tasks.match_calculation import run_match_calculation  # noqa: E402

from tests.db import TestingSessionLocal, test_engine  # noqa: E402


@pytest.fixture(autouse=True)
def override_worker_sessionlocal(monkeypatch):
    """Monkeypatch worker SessionLocal to use TestingSessionLocal SQLite memory DB."""
    monkeypatch.setattr("tasks.job_state.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("tasks.match_calculation.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("tasks.cv_extraction.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(
        "tasks.application_generation.SessionLocal", TestingSessionLocal
    )
    monkeypatch.setattr(
        "tasks.cv_extraction.validate_cv_document",
        lambda **kwargs: CVValidationResult(
            is_cv=True, confidence=0.95, reason_code="valid_cv"
        ),
    )



def _clear_worker_test_database() -> None:
    """Delete worker-test rows in foreign-key-safe dependency order."""
    with test_engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture(autouse=True)
def clean_worker_database(setup_test_database):
    """Isolate worker tests that intentionally commit through independent sessions."""
    _clear_worker_test_database()

    try:
        yield
    finally:
        _clear_worker_test_database()


def test_worker_ping_task():
    """Verify ping_task returns expected response."""
    result = ping_task()
    assert result == "pong"


def test_update_job_state_worker_helper_success():
    """Verify worker update_job_state helper updates job state and commits successfully."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    # Call worker helper with string or UUID job_id
    updated = update_job_state(
        job_id=str(job_id),
        status="processing",
        progress_percent=50,
        result={"step": "parsing_pdf"},
    )
    assert updated.id == job_id
    assert updated.status == "processing"
    assert updated.progress_percent == 50
    assert updated.result == {"step": "parsing_pdf"}

    # Verify persisted state in fresh session
    db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(db=db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "processing"
        assert persisted.progress_percent == 50
    finally:
        db.close()


def test_update_job_state_worker_helper_unknown_job_raises():
    """Verify worker update_job_state helper raises ValueError for unknown job_id."""
    unknown_id = uuid4()
    with pytest.raises(ValueError, match="not found"):
        update_job_state(
            job_id=unknown_id,
            status="completed",
            progress_percent=100,
        )


def test_update_job_state_worker_helper_invalid_string_uuid_raises():
    """Verify worker update_job_state helper raises ValueError for invalid UUID string."""
    with pytest.raises(ValueError, match="Invalid UUID string format"):
        update_job_state(
            job_id="not-a-valid-uuid-string",
            status="completed",
            progress_percent=100,
        )


def test_update_job_state_worker_helper_invalid_progress_raises():
    """Verify worker update_job_state helper raises ValueError for invalid progress_percent."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    with pytest.raises(ValueError, match="Invalid progress_percent"):
        update_job_state(
            job_id=job_id,
            status="processing",
            progress_percent=-10,
        )


# RUN_MATCH_CALCULATION TASK TESTS (1 - 15)


def test_run_match_calculation_success(monkeypatch):
    """Test 1: Successful task execution updates job to completed and returns summary dict."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="match_calculation")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    # Fake calculation returns 2 match items
    fake_matches = ["match1", "match2"]
    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        lambda db, user_id, candidate_limit, progress_callback=None: fake_matches,
    )

    res = run_match_calculation(job_id=job_id, user_id=user_id, candidate_limit=25)
    assert res == {
        "job_id": str(job_id),
        "status": "completed",
        "match_count": 2,
    }

    # Verify persisted state in fresh session
    db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(db=db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "completed"
        assert persisted.progress_percent == 100
        assert persisted.result == {"match_count": 2}
        assert persisted.error is None
    finally:
        db.close()


def test_run_match_calculation_boundary_call_args(monkeypatch):
    """Test 2: Calculation boundary receives db session, correct user_id, and candidate_limit."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="match_calculation")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    calls = []

    def mock_calc(db, user_id, candidate_limit, progress_callback=None):
        calls.append((user_id, candidate_limit))
        return ["m1"]

    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        mock_calc,
    )

    run_match_calculation(job_id=job_id, user_id=user_id, candidate_limit=15)
    assert len(calls) == 1
    assert calls[0] == (user_id, 15)


def test_run_match_calculation_default_candidate_limit_is_50(monkeypatch):
    """Test 3: Default candidate_limit passed to calculation service is 50."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="match_calculation")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    limits = []

    def mock_calc(db, user_id, candidate_limit, progress_callback=None):
        limits.append(candidate_limit)
        return []

    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        mock_calc,
    )

    run_match_calculation(job_id=job_id, user_id=user_id)
    assert limits == [50]


def test_run_match_calculation_accepts_uuid_strings(monkeypatch):
    """Test 4: Accepts valid UUID strings for job_id and user_id."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="match_calculation")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        lambda db, user_id, candidate_limit, progress_callback=None: [],
    )

    res = run_match_calculation(job_id=str(job_id), user_id=str(user_id))
    assert res["status"] == "completed"


def test_run_match_calculation_invalid_job_id_uuid_string_raises_value_error():
    """Test 5: Invalid job_id string raises ValueError."""
    with pytest.raises(ValueError, match="Invalid UUID string format for job_id"):
        run_match_calculation(job_id="bad-uuid", user_id=uuid4())


def test_run_match_calculation_invalid_user_id_uuid_string_raises_value_error():
    """Test 6: Invalid user_id string raises ValueError."""
    with pytest.raises(ValueError, match="Invalid UUID string format for user_id"):
        run_match_calculation(job_id=uuid4(), user_id="bad-uuid")


def test_run_match_calculation_candidate_limit_zero_or_negative_raises_value_error(monkeypatch):
    """Test 7: candidate_limit <= 0 raises ValueError without invoking calculation."""
    called = []
    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        lambda db, user_id, candidate_limit: called.append(1),
    )

    with pytest.raises(ValueError, match="Limit must be > 0"):
        run_match_calculation(job_id=uuid4(), user_id=uuid4(), candidate_limit=0)

    with pytest.raises(ValueError, match="Limit must be > 0"):
        run_match_calculation(job_id=uuid4(), user_id=uuid4(), candidate_limit=-5)

    assert called == []


def test_run_match_calculation_missing_job_raises_value_error(monkeypatch):
    """Test 8: Missing ProcessingJob raises ValueError without invoking calculation."""
    called = []
    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        lambda db, user_id, candidate_limit: called.append(1),
    )

    with pytest.raises(ValueError, match="not found"):
        run_match_calculation(job_id=uuid4(), user_id=uuid4())

    assert called == []


def test_run_match_calculation_ownership_mismatch_raises_value_error(monkeypatch):
    """Test 9: Job ownership mismatch raises ValueError and leaves job state unchanged."""
    owner_id = uuid4()
    other_user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=owner_id, job_type="match_calculation")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    called = []
    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        lambda db, user_id, candidate_limit: called.append(1),
    )

    with pytest.raises(ValueError, match="Job ownership mismatch"):
        run_match_calculation(job_id=job_id, user_id=other_user_id)

    assert called == []

    # Verify job remained queued and untouched
    db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(db=db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "queued"
        assert persisted.progress_percent == 0
    finally:
        db.close()


def test_run_match_calculation_wrong_job_type_raises_value_error(monkeypatch):
    """Test 10: Wrong job_type (e.g. cv_extraction) raises ValueError and leaves job unchanged."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    called = []
    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        lambda db, user_id, candidate_limit: called.append(1),
    )

    with pytest.raises(ValueError, match="ProcessingJob type mismatch"):
        run_match_calculation(job_id=job_id, user_id=user_id)

    assert called == []

    # Verify job remained queued
    db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(db=db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "queued"
    finally:
        db.close()


def test_run_match_calculation_calculation_exception_rolls_back_and_marks_failed(monkeypatch):
    """
    Test 11 & 15: Calculation exception rolls back uncommitted Match writes,
    persists job as failed in fresh session, and re-raises original exception.
    """
    user_id = uuid4()
    student_id = uuid4()
    internship_id = uuid4()
    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            id=student_id,
            user_id=user_id,
            full_name="Rollback Worker",
            summary_embedding=[0.1] * 768,
        )
        listing = InternshipListing(
            id=internship_id,
            title="Rollback Internship",
            company="Rollback Co",
            location="Remote",
            work_type="remote",
            description="Rollback lifecycle test.",
        )
        db.add_all([profile, listing])
        db.flush()
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="match_calculation")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    def mock_failing_calc(db, user_id, candidate_limit, progress_callback=None):
        # Perform an uncommitted Match write using supplied session
        uncommitted_match = Match(
            student_id=student_id,
            internship_id=internship_id,
            overall_score=75,
            skill_score=75,
            vector_score=75,
            attribute_score=75,
        )
        db.add(uncommitted_match)
        db.flush()
        raise RuntimeError("Calculation internal crash")

    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        mock_failing_calc,
    )

    with pytest.raises(RuntimeError, match="Calculation internal crash"):
        run_match_calculation(job_id=job_id, user_id=user_id)

    # Verify in fresh DB session:
    # 1. Partial Match write was rolled back completely
    # 2. ProcessingJob was updated to failed with error message
    db = TestingSessionLocal()
    try:
        match_check = db.query(Match).filter_by(student_id=student_id).first()
        assert match_check is None

        persisted_job = ProcessingJobRepository.get_by_id(db=db, job_id=job_id)
        assert persisted_job is not None
        assert persisted_job.status == "failed"
        assert persisted_job.progress_percent == 100
        assert persisted_job.result is None
        assert persisted_job.error == "Match calculation failed."
    finally:
        db.close()


def test_run_match_calculation_precondition_error_follows_failed_lifecycle(monkeypatch):
    """Test 12: MatchCalculationPreconditionError triggers failed job state and re-raises error."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="match_calculation")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    def mock_precondition_calc(db, user_id, candidate_limit, progress_callback=None):
        raise MatchCalculationPreconditionError("Profile summary_embedding missing")

    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        mock_precondition_calc,
    )

    with pytest.raises(MatchCalculationPreconditionError, match="summary_embedding missing"):
        run_match_calculation(job_id=job_id, user_id=user_id)

    # Verify persisted job state is failed
    db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(db=db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.progress_percent == 100
        assert persisted.error == "Match calculation failed."
    finally:
        db.close()


def test_run_match_calculation_clears_stale_job_result_and_error(monkeypatch):
    """Test 13: Stale job.result and job.error are cleared on successful rerun."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="match_calculation")
        job.result = {"old": "result"}
        job.error = "old error"
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        lambda db, user_id, candidate_limit, progress_callback=None: ["m1"],
    )

    run_match_calculation(job_id=job_id, user_id=user_id)

    db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(db=db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "completed"
        assert persisted.error is None
        assert persisted.result == {"match_count": 1}
    finally:
        db.close()


def test_run_match_calculation_failure_persists_safe_error_and_hides_raw_exception(
    monkeypatch,
):
    """
    Test 14: Match worker failure persists safe generic error message
    and hides long internal exception text.
    """
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(
            db=db, user_id=user_id, job_type="match_calculation"
        )
        db.commit()
        job_id = job.id
    finally:
        db.close()

    long_msg = "X" * 1500

    def mock_long_error_calc(db, user_id, candidate_limit, progress_callback=None):
        raise RuntimeError(long_msg)

    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        mock_long_error_calc,
    )

    with pytest.raises(RuntimeError):
        run_match_calculation(job_id=job_id, user_id=user_id)

    db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(db=db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.progress_percent == 100
        assert persisted.error == "Match calculation failed."
        assert long_msg not in (persisted.error or "")
        assert "X" * 1000 not in (persisted.error or "")
    finally:
        db.close()


def test_cv_publish_progress_updates_active_job():
    """Progress publication updates an active CV job without changing its contract."""
    user_id = uuid4()
    job_id = uuid4()

    db = TestingSessionLocal()
    try:
        db.add(
            ProcessingJob(
                id=job_id,
                user_id=user_id,
                job_type="cv_extraction",
                status="queued",
                progress_percent=0,
            )
        )
        db.commit()
    finally:
        db.close()

    _publish_progress(job_id, 35)

    fresh_db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(
            fresh_db,
            job_id=job_id,
        )
        assert persisted is not None
        assert persisted.status == "processing"
        assert persisted.progress_percent == 35
    finally:
        fresh_db.close()


def test_cv_publish_progress_does_not_resurrect_cancelled_job():
    """A progress checkpoint must never reopen a durably cancelled CV job."""
    user_id = uuid4()
    job_id = uuid4()

    db = TestingSessionLocal()
    try:
        db.add(
            ProcessingJob(
                id=job_id,
                user_id=user_id,
                job_type="cv_extraction",
                status="failed",
                progress_percent=100,
                result={
                    "cancel_requested": True,
                    "cancelled": True,
                },
                error="CV analysis cancelled by user.",
            )
        )
        db.commit()
    finally:
        db.close()

    _publish_progress(job_id, 70)

    fresh_db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(
            fresh_db,
            job_id=job_id,
        )
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.progress_percent == 100
        assert persisted.result["cancel_requested"] is True
        assert persisted.result["cancelled"] is True
        assert persisted.error == "CV analysis cancelled by user."
    finally:
        fresh_db.close()


# RUN_CV_EXTRACTION WORKER PIPELINE TESTS (16 - 28)


def _make_dummy_extracted_profile(name="Test Candidate"):
    return ExtractedCandidateProfile(
        full_name=name,
        headline="AI Software Intern",
        skills=[
            ExtractedSkill(name="Python", proficiency_level="advanced"),
            ExtractedSkill(name="FastAPI", proficiency_level="intermediate"),
        ],
        education=[
            ExtractedEducation(
                institution="State University",
                degree="B.S. Computer Science",
                start_year=2022,
                end_year=2026,
            )
        ],
        experience=[
            ExtractedExperience(
                company="Tech Corp",
                role="Software Intern",
                description="Built APIs.",
            )
        ],
        projects=[
            ExtractedProject(
                title="Job Portal",
                tech_stack=["Python", "FastAPI"],
                description="Intern matching app.",
            )
        ],
        preferences=ExtractedPreferences(
            work_types=["remote"],
            desired_locations=["Remote"],
            target_roles=["Backend Intern"],
        ),
    )


def test_run_cv_extraction_success_lifecycle(monkeypatch):
    """Test 16: Successful run_cv_extraction completes pipeline, commits, and returns summary."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    storage_path = f"{user_id}/resume.pdf"
    fake_profile = _make_dummy_extracted_profile("Alice Smith")

    monkeypatch.setattr(
        "tasks.cv_extraction.download_candidate_cv",
        lambda *, user_id, storage_path: b"%PDF fake content",
    )
    monkeypatch.setattr(
        "tasks.cv_extraction.extract_cv_text",
        lambda *, storage_path, content: "Alice Smith - AI Software Intern\nPython, FastAPI",
    )
    monkeypatch.setattr(
        "tasks.cv_extraction.extract_structured_candidate_profile",
        lambda *, text, content_locale: fake_profile,
    )
    monkeypatch.setattr(
        "tasks.cv_extraction.generate_and_persist_candidate_embedding",
        lambda db, user_id: [0.1] * 1536,
    )

    res = run_cv_extraction(
        job_id=job_id,
        user_id=user_id,
        storage_path=storage_path,
        content_locale="en",
    )

    assert res["status"] == "completed"
    assert res["job_id"] == str(job_id)
    assert "profile_id" in res

    # Verify persisted state in fresh session
    fresh_db = TestingSessionLocal()
    try:
        persisted_job = ProcessingJobRepository.get_by_id(fresh_db, job_id=job_id)
        assert persisted_job is not None
        assert persisted_job.status == "completed"
        assert persisted_job.progress_percent == 100
        assert persisted_job.result == {"profile_id": res["profile_id"]}
        assert persisted_job.error is None

        # Verify profile and related records exist
        profile = fresh_db.query(StudentProfile).filter_by(user_id=user_id).first()
        assert profile is not None
        assert profile.full_name == "Alice Smith"
        assert profile.headline == "AI Software Intern"

        skills = fresh_db.query(StudentSkill).filter_by(student_id=profile.id).all()
        assert len(skills) == 2

        edu = fresh_db.query(EducationEntry).filter_by(student_id=profile.id).all()
        assert len(edu) == 1
    finally:
        fresh_db.close()


def test_run_cv_extraction_accepts_uuid_strings(monkeypatch):
    """Test 17: run_cv_extraction accepts valid UUID strings for job_id and user_id."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr("tasks.cv_extraction.download_candidate_cv", lambda **kwargs: b"bytes")
    monkeypatch.setattr("tasks.cv_extraction.extract_cv_text", lambda **kwargs: "text")
    monkeypatch.setattr(
        "tasks.cv_extraction.extract_structured_candidate_profile",
        lambda **kwargs: _make_dummy_extracted_profile("Bob"),
    )
    monkeypatch.setattr(
        "tasks.cv_extraction.generate_and_persist_candidate_embedding",
        lambda db, user_id: [0.2] * 1536,
    )

    res = run_cv_extraction(
        job_id=str(job_id),
        user_id=str(user_id),
        storage_path=f"{user_id}/resume.pdf",
    )
    assert res["status"] == "completed"


def test_run_cv_extraction_empty_storage_path_raises_value_error():
    """Test 18: Empty storage_path raises ValueError before DB operations."""
    with pytest.raises(ValueError, match="storage_path cannot be empty"):
        run_cv_extraction(job_id=uuid4(), user_id=uuid4(), storage_path="")


def test_run_cv_extraction_missing_job_raises_without_mutation():
    """Test 19: Non-existent ProcessingJob raises ValueError without mutating state."""
    unknown_id = uuid4()
    with pytest.raises(ValueError, match="not found"):
        run_cv_extraction(
            job_id=unknown_id,
            user_id=uuid4(),
            storage_path=f"{unknown_id}/resume.pdf",
        )


def test_run_cv_extraction_ownership_mismatch_leaves_job_untouched():
    """Test 20: Job ownership mismatch raises ValueError and leaves job in queued state."""
    owner_id = uuid4()
    attacker_id = uuid4()

    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=owner_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    with pytest.raises(ValueError, match="Job ownership mismatch"):
        run_cv_extraction(
            job_id=job_id,
            user_id=attacker_id,
            storage_path=f"{attacker_id}/resume.pdf",
        )

    # Verify job remained queued and untouched
    fresh_db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(fresh_db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "queued"
        assert persisted.progress_percent == 0
    finally:
        fresh_db.close()


def test_run_cv_extraction_wrong_job_type_leaves_job_untouched():
    """Test 21: Wrong job_type raises ValueError and leaves job in queued state."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="match_calculation")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    with pytest.raises(ValueError, match="ProcessingJob type mismatch"):
        run_cv_extraction(
            job_id=job_id,
            user_id=user_id,
            storage_path=f"{user_id}/resume.pdf",
        )

    fresh_db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(fresh_db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "queued"
    finally:
        fresh_db.close()


def test_run_cv_extraction_storage_failure_rolls_back_and_marks_failed(monkeypatch):
    """Test 22: Storage download failure rolls back transaction and marks job failed."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr(
        "tasks.cv_extraction.download_candidate_cv",
        MagicMock(side_effect=RuntimeError("Storage service unavailable 503")),
    )

    with pytest.raises(RuntimeError, match="Storage service unavailable"):
        run_cv_extraction(
            job_id=job_id,
            user_id=user_id,
            storage_path=f"{user_id}/resume.pdf",
        )

    fresh_db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(fresh_db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.progress_percent == 100
        assert persisted.error == "CV processing failed."
        assert "Storage service unavailable" not in (persisted.error or "")
    finally:
        fresh_db.close()


def test_run_cv_extraction_parser_failure_rolls_back_and_marks_failed(monkeypatch):
    """Test 23: Document parsing failure rolls back transaction and marks job failed."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr("tasks.cv_extraction.download_candidate_cv", lambda **kwargs: b"corrupted")
    monkeypatch.setattr(
        "tasks.cv_extraction.extract_cv_text",
        MagicMock(side_effect=ValueError("Corrupt PDF EOF marker missing")),
    )

    with pytest.raises(ValueError, match="Corrupt PDF"):
        run_cv_extraction(
            job_id=job_id,
            user_id=user_id,
            storage_path=f"{user_id}/resume.pdf",
        )

    fresh_db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(fresh_db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.error == "CV processing failed."
        assert "Corrupt PDF" not in (persisted.error or "")
    finally:
        fresh_db.close()


def test_run_cv_extraction_llm_failure_rolls_back_and_marks_failed(monkeypatch):
    """Test 24: LLM extraction failure rolls back transaction and marks job failed."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr("tasks.cv_extraction.download_candidate_cv", lambda **kwargs: b"pdf")
    monkeypatch.setattr("tasks.cv_extraction.extract_cv_text", lambda **kwargs: "text")
    monkeypatch.setattr(
        "tasks.cv_extraction.extract_structured_candidate_profile",
        MagicMock(side_effect=RuntimeError("OpenAI API rate limit exceeded")),
    )

    with pytest.raises(RuntimeError, match="OpenAI API rate limit"):
        run_cv_extraction(
            job_id=job_id,
            user_id=user_id,
            storage_path=f"{user_id}/resume.pdf",
        )

    fresh_db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(fresh_db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.error == "CV processing failed."
    finally:
        fresh_db.close()


def test_run_cv_extraction_embedding_failure_rolls_back_and_marks_failed(monkeypatch):
    """Test 25: Embedding generation failure rolls back all candidate profile writes."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr("tasks.cv_extraction.download_candidate_cv", lambda **kwargs: b"pdf")
    monkeypatch.setattr("tasks.cv_extraction.extract_cv_text", lambda **kwargs: "text")
    monkeypatch.setattr(
        "tasks.cv_extraction.extract_structured_candidate_profile",
        lambda **kwargs: _make_dummy_extracted_profile("Rollback Target"),
    )
    monkeypatch.setattr(
        "tasks.cv_extraction.generate_and_persist_candidate_embedding",
        MagicMock(side_effect=RuntimeError("Embedding model service crash")),
    )

    with pytest.raises(RuntimeError, match="Embedding model service crash"):
        run_cv_extraction(
            job_id=job_id,
            user_id=user_id,
            storage_path=f"{user_id}/resume.pdf",
        )

    fresh_db = TestingSessionLocal()
    try:
        # Verify student profile with "Rollback Target" was NOT committed
        profile = fresh_db.query(StudentProfile).filter_by(user_id=user_id).first()
        assert profile is None

        # Verify job is failed
        persisted = ProcessingJobRepository.get_by_id(fresh_db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.error == "CV processing failed."
    finally:
        fresh_db.close()


def test_run_cv_extraction_result_contains_profile_id_only(monkeypatch):
    """Test 26: Worker result contains profile_id only; excludes raw text and vector."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr("tasks.cv_extraction.download_candidate_cv", lambda **kwargs: b"pdf")
    monkeypatch.setattr("tasks.cv_extraction.extract_cv_text", lambda **kwargs: "text")
    monkeypatch.setattr(
        "tasks.cv_extraction.extract_structured_candidate_profile",
        lambda **kwargs: _make_dummy_extracted_profile("Charlie"),
    )
    monkeypatch.setattr(
        "tasks.cv_extraction.generate_and_persist_candidate_embedding",
        lambda db, user_id: [0.3] * 1536,
    )

    run_cv_extraction(job_id=job_id, user_id=user_id, storage_path=f"{user_id}/resume.pdf")

    fresh_db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(fresh_db, job_id=job_id)
        assert persisted is not None
        assert "profile_id" in persisted.result
        assert "raw_cv_text" not in persisted.result
        assert "embedding" not in persisted.result
        assert "vector" not in persisted.result
    finally:
        fresh_db.close()


def test_run_cv_extraction_failure_persists_safe_error_and_hides_raw_exception(monkeypatch):
    """
    Test 27: Worker failures persist generic safe error message and never leak raw exception.
    """
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    sensitive_error = "Internal database connection failure: postgresql://admin:SECRET@db/prod"
    monkeypatch.setattr(
        "tasks.cv_extraction.download_candidate_cv",
        MagicMock(side_effect=RuntimeError(sensitive_error)),
    )

    with pytest.raises(RuntimeError):
        run_cv_extraction(job_id=job_id, user_id=user_id, storage_path=f"{user_id}/resume.pdf")

    fresh_db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(fresh_db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.error == "CV processing failed."
        assert "SECRET" not in (persisted.error or "")
    finally:
        fresh_db.close()


def test_run_cv_extraction_semantic_validation_rejects_non_cv_without_profile_write(monkeypatch):
    """Test 29: Invalid CV fails job with client-safe error and leaves profile untouched."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr(
        "tasks.cv_extraction.download_candidate_cv",
        lambda *, user_id, storage_path: b"%PDF non-cv document content",
    )
    monkeypatch.setattr(
        "tasks.cv_extraction.extract_cv_text",
        lambda *, storage_path, content: (
            "Invoice #12345\nTotal: $500.00\nPayment due upon receipt."
        ),
    )
    monkeypatch.setattr(
        "tasks.cv_extraction.validate_cv_document",
        MagicMock(
            side_effect=InvalidCVDocumentError(
                "The uploaded document does not appear to be a valid CV or resume. "
                "Please upload a valid resume.",
                reason_code="invoice_or_financial",
            )
        ),
    )
    mock_extract = MagicMock()
    monkeypatch.setattr("tasks.cv_extraction.extract_structured_candidate_profile", mock_extract)

    with pytest.raises(InvalidCVDocumentError):
        run_cv_extraction(job_id=job_id, user_id=user_id, storage_path=f"{user_id}/invoice.pdf")

    # Profile extraction and write should NEVER have been called
    assert mock_extract.call_count == 0

    fresh_db = TestingSessionLocal()
    try:
        persisted_job = ProcessingJobRepository.get_by_id(fresh_db, job_id=job_id)
        assert persisted_job is not None
        assert persisted_job.status == "failed"
        assert persisted_job.progress_percent == 100
        assert persisted_job.result is None
        assert "does not appear to be a valid CV or resume" in (persisted_job.error or "")

        # Candidate profile must not exist
        profile = fresh_db.query(StudentProfile).filter_by(user_id=user_id).first()
        assert profile is None
    finally:
        fresh_db.close()


def test_run_cv_extraction_validation_service_error_marks_generic_failure(monkeypatch):
    """Test 30: Validation service failure is treated as generic processing error, not non-CV."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.create(db=db, user_id=user_id, job_type="cv_extraction")
        db.commit()
        job_id = job.id
    finally:
        db.close()

    monkeypatch.setattr(
        "tasks.cv_extraction.download_candidate_cv",
        lambda *, user_id, storage_path: b"%PDF valid content",
    )
    monkeypatch.setattr(
        "tasks.cv_extraction.extract_cv_text",
        lambda *, storage_path, content: "Jane Doe Software Engineer Resume",
    )
    monkeypatch.setattr(
        "tasks.cv_extraction.validate_cv_document",
        MagicMock(side_effect=CVValidationServiceError("Gemini API connection timeout")),
    )

    with pytest.raises(CVValidationServiceError):
        run_cv_extraction(job_id=job_id, user_id=user_id, storage_path=f"{user_id}/resume.pdf")

    fresh_db = TestingSessionLocal()
    try:
        persisted_job = ProcessingJobRepository.get_by_id(fresh_db, job_id=job_id)
        assert persisted_job is not None
        assert persisted_job.status == "failed"
        assert persisted_job.progress_percent == 100
        # Generic error message, NOT invalid CV
        assert persisted_job.error == "CV processing failed."
    finally:
        fresh_db.close()
