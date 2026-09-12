"""
Integration & Unit Tests for CV Mismatch Confirmation Flow.
Verifies the confirmation contract, ownership validation, idempotency, transactional integrity,
and non-mutation of profile data before user confirmation.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from app.core.security import AuthenticatedUser, get_current_user
from app.db.models import (
    EducationEntry,
    ExperienceEntry,
    ProcessingJob,
    StudentProfile,
    StudentSkill,
)
from app.main import app
from app.repositories.matching_data import MatchingDataRepository
from app.repositories.processing_job import ProcessingJobRepository
from app.services.cv_profile_extraction import (
    ExtractedCandidateProfile,
    ExtractedEducation,
    ExtractedExperience,
    ExtractedSkill,
)
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal

# Make worker task modules importable when this test file runs in isolation.
worker_dir = Path(__file__).parent.parent / "worker"
if str(worker_dir) not in sys.path:
    sys.path.insert(0, str(worker_dir))

from tasks.cv_extraction import run_cv_extraction  # noqa: E402

client = TestClient(app)


def test_worker_mismatch_stores_pending_confirmation_without_mutating_profile(monkeypatch):
    """
    Test 1: When candidate identity mismatch occurs in worker:
    - job.status == 'completed'
    - job.result['requires_confirmation'] == True
    - Existing profile is NOT modified
    - No match calculation job is enqueued
    """
    db = TestingSessionLocal()
    user_id = uuid4()
    job_id = uuid4()

    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="John Doe",
            headline="Backend Dev",
        )
        db.add(profile)
        db.flush()

        db.add(EducationEntry(student_id=profile.id, institution="MIT", degree="B.S. CS"))
        db.add(ExperienceEntry(student_id=profile.id, company="Google", role="SWE Intern"))

        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="cv_extraction",
            status="queued",
        )
        db.add(job)
        db.commit()

        # Mock download, validation, and extraction returning a different candidate (Alice Smith)
        monkeypatch.setattr(
            "tasks.cv_extraction.download_candidate_cv",
            lambda user_id, storage_path: b"%PDF-1.4 mock content",
        )
        monkeypatch.setattr(
            "tasks.cv_extraction.extract_cv_text",
            lambda content, storage_path: "Alice Smith Resume Oxford Economics McKinsey",
        )
        monkeypatch.setattr(
            "tasks.cv_extraction.validate_cv_document",
            lambda text, content_locale: MagicMock(is_cv=True, confidence=0.99),
        )

        extracted_profile = ExtractedCandidateProfile(
            full_name="Alice Smith",
            headline="Management Consultant",
            skills=[ExtractedSkill(name="Financial Modeling")],
            education=[ExtractedEducation(institution="Oxford", degree="B.A. Economics")],
            experience=[ExtractedExperience(company="McKinsey", role="Associate")],
        )
        monkeypatch.setattr(
            "tasks.cv_extraction.extract_structured_candidate_profile",
            lambda text, content_locale: extracted_profile,
        )

        # Mock match queue
        mock_enqueue = MagicMock()
        monkeypatch.setattr(
            "tasks.cv_extraction.enqueue_match_calculation",
            mock_enqueue,
        )
        monkeypatch.setattr(
            "tasks.cv_extraction.SessionLocal",
            lambda: TestingSessionLocal(),
        )

        # Execute worker task directly
        run_cv_extraction(
            job_id=job_id,
            user_id=user_id,
            storage_path=f"{user_id}/resume.pdf",
        )

        # Inspect DB state
        db.expire_all()
        updated_job = db.query(ProcessingJob).filter_by(id=job_id).first()
        assert updated_job.status == "completed"
        assert updated_job.result is not None
        assert updated_job.result.get("requires_confirmation") is True
        assert updated_job.result.get("confirmed") is False
        assert updated_job.result.get("reason") == "possible_identity_mismatch"
        assert updated_job.result.get("extracted_name") == "Alice Smith"
        assert updated_job.result.get("existing_name") == "John Doe"

        # Verify profile was NOT mutated
        current_profile = db.query(StudentProfile).filter_by(user_id=user_id).first()
        assert current_profile.full_name == "John Doe"
        assert current_profile.headline == "Backend Dev"

        # Verify no match calculation job was enqueued
        mock_enqueue.assert_not_called()
    finally:
        db.close()


def test_confirm_endpoint_requires_job_ownership():
    """Test 2: POST /api/v1/profile/cv/confirm rejects jobs owned by another user (404/403)."""
    db = TestingSessionLocal()
    user_a_id = uuid4()
    user_b_id = uuid4()
    job_id = uuid4()

    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_a_id,
            job_type="cv_extraction",
            status="completed",
            result={
                "requires_confirmation": True,
                "confirmed": False,
                "extracted_profile": {"full_name": "Test Candidate", "skills": []},
                "cv_storage_path": f"{user_a_id}/resume.pdf",
            },
        )
        db.add(job)
        db.commit()

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id=user_b_id, email="userb@example.com", role="student"
        )
        response = client.post(
            "/api/v1/profile/cv/confirm",
            json={"job_id": str(job_id)},
        )
        # Job not owned by user_b -> Not Found
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        db.close()


def test_confirm_endpoint_rejects_non_cv_job_type():
    """Test 3: POST /api/v1/profile/cv/confirm rejects jobs that are not cv_extraction (400)."""
    db = TestingSessionLocal()
    user_id = uuid4()
    job_id = uuid4()

    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="match_calculation",
            status="completed",
            result={"requires_confirmation": True},
        )
        db.add(job)
        db.commit()

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id=user_id, email="user@example.com", role="student"
        )
        response = client.post(
            "/api/v1/profile/cv/confirm",
            json={"job_id": str(job_id)},
        )
        assert response.status_code == 400
        assert "not a CV extraction job" in response.json()["detail"]["error"]["message"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        db.close()


def test_confirm_endpoint_rejects_job_not_requiring_confirmation():
    """Test 4: POST /api/v1/profile/cv/confirm rejects jobs that did not flag a mismatch (400)."""
    db = TestingSessionLocal()
    user_id = uuid4()
    job_id = uuid4()

    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="cv_extraction",
            status="completed",
            result={"skills_extracted": 5},
        )
        db.add(job)
        db.commit()

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id=user_id, email="user@example.com", role="student"
        )
        response = client.post(
            "/api/v1/profile/cv/confirm",
            json={"job_id": str(job_id)},
        )
        assert response.status_code == 400
        assert "does not require confirmation" in response.json()["detail"]["error"]["message"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        db.close()


def test_confirm_endpoint_executes_replacement_and_enqueues_matches(monkeypatch):
    """
    Test 5: Valid confirmation call:
    - Mutates candidate profile (true replacement)
    - Enqueues match calculation job
    - Sets confirmed = True in job.result
    - Subsequent call returns idempotently without re-enqueuing
    """
    db = TestingSessionLocal()
    user_id = uuid4()
    job_id = uuid4()

    try:
        initial_profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Old Name",
            headline="Old Headline",
        )
        db.add(initial_profile)
        db.flush()

        db.add(
            EducationEntry(
                student_id=initial_profile.id,
                institution="Old College",
                degree="B.A.",
            )
        )
        db.add(
            ExperienceEntry(
                student_id=initial_profile.id,
                company="Old Company",
                role="Intern",
            )
        )

        extracted_data = {
            "full_name": "Confirmed New Name",
            "headline": "Lead AI Architect",
            "skills": [{"name": "Rust"}, {"name": "PyTorch"}],
            "education": [{"institution": "MIT", "degree": "M.S. CS"}],
            "experience": [{"company": "OpenAI", "role": "Research Scientist"}],
            "projects": [],
            "preferences": {
                "work_types": ["remote"],
                "desired_locations": ["San Francisco"],
                "target_roles": [],
            },
        }

        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="cv_extraction",
            status="completed",
            result={
                "requires_confirmation": True,
                "confirmed": False,
                "extracted_profile": extracted_data,
                "cv_storage_path": f"{user_id}/new_cv.pdf",
            },
        )
        db.add(job)
        db.commit()

        # Embedding is deferred to the match worker; mock the endpoint symbol to prove confirmation does not call it.
        mock_embed = MagicMock()
        monkeypatch.setattr(
            "app.api.v1.endpoints.profile.generate_and_persist_candidate_embedding",
            mock_embed,
        )

        mock_enqueue = MagicMock()
        monkeypatch.setattr(
            "app.api.v1.endpoints.profile.enqueue_match_calculation",
            mock_enqueue,
        )

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id=user_id, email="user@example.com", role="student"
        )

        # First confirmation call
        res1 = client.post(
            "/api/v1/profile/cv/confirm",
            json={"job_id": str(job_id)},
        )
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["status"] == "completed"
        assert "profile_id" in data1
        mock_embed.assert_not_called()
        mock_enqueue.assert_called_once()

        # Inspect updated DB state
        db.expire_all()
        updated_prof = db.query(StudentProfile).filter_by(user_id=user_id).first()
        assert updated_prof.full_name == "Confirmed New Name"
        assert updated_prof.headline == "Lead AI Architect"

        # Verify old education/experience replaced
        edu = MatchingDataRepository.get_education_for_student(db, updated_prof.id)
        assert len(edu) == 1
        assert edu[0].institution == "MIT"

        exp = MatchingDataRepository.get_experience_for_student(db, updated_prof.id)
        assert len(exp) == 1
        assert exp[0].company == "OpenAI"

        skills = db.query(StudentSkill).filter_by(student_id=updated_prof.id).all()
        assert len(skills) == 2

        # Verify job is marked confirmed
        updated_job = db.query(ProcessingJob).filter_by(id=job_id).first()
        assert updated_job.result["confirmed"] is True

        # Second confirmation call (IDEMPOTENT REPLAY)
        mock_embed.reset_mock()
        mock_enqueue.reset_mock()

        res2 = client.post(
            "/api/v1/profile/cv/confirm",
            json={"job_id": str(job_id)},
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["status"] == "completed"
        assert "already confirmed" in data2["message"]
        # Must not have re-embedded or re-enqueued matches
        mock_embed.assert_not_called()
        mock_enqueue.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        db.close()


def test_confirm_endpoint_invalid_pending_payload_returns_safe_error():
    """
    Regression: malformed server-side pending extraction data must return a
    stable user-safe error and must not expose Pydantic/schema internals.
    """
    db = TestingSessionLocal()
    user_id = uuid4()
    job_id = uuid4()

    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="cv_extraction",
            status="completed",
            result={
                "requires_confirmation": True,
                "confirmed": False,
                # Deliberately malformed structured extraction payload.
                "extracted_profile": {
                    "skills": "this-is-not-a-valid-skill-list",
                },
                "cv_storage_path": f"{user_id}/pending_cv.pdf",
            },
        )
        db.add(job)
        db.commit()

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id=user_id,
            email="user@example.com",
            role="student",
        )

        response = client.post(
            "/api/v1/profile/cv/confirm",
            json={"job_id": str(job_id)},
        )

        assert response.status_code == 400

        payload = response.json()
        message = payload["detail"]["error"]["message"]

        assert message == (
            "Pending CV replacement data is invalid. Please upload the CV again."
        )

        response_text = response.text.lower()

        # Internal validation/schema details must never reach the client.
        assert "validation error" not in response_text
        assert "pydantic" not in response_text
        assert "input should be" not in response_text
        assert "extractedcandidateprofile" not in response_text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        db.close()


def test_confirm_endpoint_marks_match_job_failed_when_enqueue_fails(monkeypatch):
    """
    Regression: profile confirmation remains successful when automatic matching
    enqueue fails, but the already-persisted match job must be marked failed
    rather than remaining queued forever.
    """
    db = TestingSessionLocal()
    user_id = uuid4()
    job_id = uuid4()

    try:
        initial_profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Old Candidate",
            headline="Old Headline",
        )
        db.add(initial_profile)
        db.flush()

        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="cv_extraction",
            status="completed",
            result={
                "requires_confirmation": True,
                "confirmed": False,
                "extracted_profile": {
                    "full_name": "Confirmed Candidate",
                    "headline": "Backend Engineer",
                    "skills": [{"name": "Python"}],
                    "education": [],
                    "experience": [],
                    "projects": [],
                    "preferences": {},
                },
                "cv_storage_path": f"{user_id}/confirmed_cv.pdf",
            },
        )
        db.add(job)
        db.commit()

        mock_embed = MagicMock()
        monkeypatch.setattr(
            "app.api.v1.endpoints.profile.generate_and_persist_candidate_embedding",
            mock_embed,
        )

        mock_enqueue = MagicMock(side_effect=RuntimeError("queue unavailable"))
        monkeypatch.setattr(
            "app.api.v1.endpoints.profile.enqueue_match_calculation",
            mock_enqueue,
        )

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id=user_id,
            email="user@example.com",
            role="student",
        )

        response = client.post(
            "/api/v1/profile/cv/confirm",
            json={"job_id": str(job_id)},
        )

        # CV replacement itself succeeded; matching is best-effort.
        assert response.status_code == 200
        mock_embed.assert_not_called()
        mock_enqueue.assert_called_once()

        db.expire_all()

        updated_profile = (
            db.query(StudentProfile)
            .filter_by(user_id=user_id)
            .first()
        )
        assert updated_profile is not None
        assert updated_profile.full_name == "Confirmed Candidate"

        updated_cv_job = (
            db.query(ProcessingJob)
            .filter_by(id=job_id)
            .first()
        )
        assert updated_cv_job.result["confirmed"] is True
        assert updated_cv_job.result["requires_confirmation"] is False

        match_jobs = (
            db.query(ProcessingJob)
            .filter_by(
                user_id=user_id,
                job_type="match_calculation",
            )
            .all()
        )

        assert len(match_jobs) == 1

        failed_match_job = match_jobs[0]
        assert failed_match_job.status == "failed"
        assert failed_match_job.progress_percent == 100
        assert failed_match_job.result is None
        assert (
            failed_match_job.error
            == "Failed to enqueue automatic match calculation."
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        db.close()


def test_processing_job_confirm_lookup_uses_postgres_for_update():
    """
    Regression: the actual repository method used by CV confirmation must issue
    a user-scoped SELECT ... FOR UPDATE query under PostgreSQL.
    """
    from sqlalchemy.dialects import postgresql

    user_id = uuid4()
    job_id = uuid4()

    class CapturingSession:
        def __init__(self):
            self.statement = None

        def scalar(self, statement):
            self.statement = statement
            return None

    db = CapturingSession()

    result = ProcessingJobRepository.get_by_id_and_user_id_for_update(
        db=db,
        job_id=job_id,
        user_id=user_id,
    )

    assert result is None
    assert db.statement is not None

    sql = str(
        db.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    normalized_sql = " ".join(sql.upper().split())

    assert "FOR NO KEY UPDATE" in normalized_sql
    assert "FOR UPDATE" not in normalized_sql
    assert "PROCESSING_JOBS.ID" in normalized_sql
    assert "PROCESSING_JOBS.USER_ID" in normalized_sql
    assert str(job_id).upper() in normalized_sql
    assert str(user_id).upper() in normalized_sql


def test_cancel_cv_analysis_rejects_other_users_job():
    """A user must never be able to cancel another user's CV job."""
    db = TestingSessionLocal()
    owner_user_id = uuid4()
    requester_user_id = uuid4()
    job_id = uuid4()

    try:
        job = ProcessingJob(
            id=job_id,
            user_id=owner_user_id,
            job_type="cv_extraction",
            status="queued",
            progress_percent=0,
            result=None,
        )
        db.add(job)
        db.commit()

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id=requester_user_id,
            email="requester@example.com",
            role="student",
        )

        response = client.post(f"/api/v1/profile/cv/{job_id}/cancel")

        assert response.status_code == 404

        db.expire_all()
        persisted = db.query(ProcessingJob).filter_by(id=job_id).first()

        assert persisted is not None
        assert persisted.status == "queued"
        assert persisted.result is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        db.close()


def test_cancel_cv_analysis_marks_active_job_cancelled():
    """
    Cancelling an active owned CV job must persist a durable cancellation marker
    before returning success.
    """
    db = TestingSessionLocal()
    user_id = uuid4()
    job_id = uuid4()

    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="cv_extraction",
            status="processing",
            progress_percent=55,
            result=None,
        )
        db.add(job)
        db.commit()

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id=user_id,
            email="user@example.com",
            role="student",
        )

        response = client.post(f"/api/v1/profile/cv/{job_id}/cancel")

        assert response.status_code == 200

        payload = response.json()
        assert payload["job_id"] == str(job_id)
        assert payload["status"] == "cancelled"

        db.expire_all()
        persisted = db.query(ProcessingJob).filter_by(id=job_id).first()

        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.progress_percent == 100
        assert persisted.result["cancel_requested"] is True
        assert persisted.result["cancelled"] is True
        assert persisted.error == "CV analysis cancelled by user."
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        db.close()


def test_cancel_cv_analysis_is_idempotent():
    """Repeating an already-successful cancellation must remain a safe success."""
    db = TestingSessionLocal()
    user_id = uuid4()
    job_id = uuid4()

    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="cv_extraction",
            status="queued",
            progress_percent=0,
            result=None,
        )
        db.add(job)
        db.commit()

        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            user_id=user_id,
            email="user@example.com",
            role="student",
        )

        first_response = client.post(f"/api/v1/profile/cv/{job_id}/cancel")
        second_response = client.post(f"/api/v1/profile/cv/{job_id}/cancel")

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert second_response.json()["status"] == "cancelled"

        db.expire_all()
        persisted = db.query(ProcessingJob).filter_by(id=job_id).first()

        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.progress_percent == 100
        assert persisted.result["cancel_requested"] is True
        assert persisted.result["cancelled"] is True
        assert persisted.error == "CV analysis cancelled by user."
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        db.close()


def test_worker_cancelled_job_stops_before_profile_mutation(monkeypatch):
    """
    A worker that observes a durable cancellation marker must exit before
    downloading/mutating the candidate profile or generating an embedding.
    """
    db = TestingSessionLocal()
    user_id = uuid4()
    job_id = uuid4()
    storage_path = f"{user_id}/cancelled_cv.pdf"

    try:
        job = ProcessingJob(
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
        db.add(job)
        db.commit()

        monkeypatch.setattr(
            "tasks.cv_extraction.SessionLocal",
            TestingSessionLocal,
        )

        mock_download = MagicMock()
        mock_replace = MagicMock()
        mock_embed = MagicMock()

        monkeypatch.setattr(
            "tasks.cv_extraction.download_candidate_cv",
            mock_download,
        )
        monkeypatch.setattr(
            "tasks.cv_extraction.replace_candidate_profile_from_extraction",
            mock_replace,
        )
        monkeypatch.setattr(
            "tasks.cv_extraction.generate_and_persist_candidate_embedding",
            mock_embed,
        )

        result = run_cv_extraction(
            job_id=job_id,
            user_id=user_id,
            storage_path=storage_path,
        )

        assert result == {
            "job_id": str(job_id),
            "status": "cancelled",
        }

        mock_download.assert_not_called()
        mock_replace.assert_not_called()
        mock_embed.assert_not_called()

        db.expire_all()
        persisted = db.query(ProcessingJob).filter_by(id=job_id).first()

        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.result["cancel_requested"] is True
        assert persisted.result["cancelled"] is True
        assert persisted.error == "CV analysis cancelled by user."
    finally:
        db.close()
