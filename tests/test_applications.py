"""
Unit & Integration Tests for Personalized Application Assistant (Gate 2.28).
Tests POST /api/v1/applications/generate endpoint, authentication,
tenant isolation, request validation, enqueue service, grounded LLM generation,
application persistence/regeneration semantics, and worker task lifecycle.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

# Add worker directory to path for test execution
worker_dir = Path(__file__).parent.parent / "worker"
if str(worker_dir) not in sys.path:
    sys.path.insert(0, str(worker_dir))

from app.core.config import settings  # noqa: E402
from app.db.models import (  # noqa: E402
    Application,
    EducationEntry,
    ExperienceEntry,
    InternshipListing,
    Match,
    ProcessingJob,
    ProjectEntry,
    Skill,
    StudentProfile,
    StudentSkill,
)
from app.repositories.application import ApplicationRepository  # noqa: E402
from app.repositories.processing_job import (  # noqa: E402
    ProcessingJobRepository,
)
from app.services.application_enqueue import (  # noqa: E402
    enqueue_application_generation,
)
from app.services.application_generation import (  # noqa: E402
    LLMCoverLetter,
    generate_grounded_cover_letter,
)
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tasks.application_generation import (  # noqa: E402
    run_application_generation,
)

from tests.db import TestingSessionLocal  # noqa: E402

pytestmark = pytest.mark.usefixtures("mock_supabase_auth")


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure all related tables are cleared before and after each test."""
    db = TestingSessionLocal()
    try:
        db.query(Application).delete()
        db.query(Match).delete()
        db.query(ProcessingJob).delete()
        db.query(StudentSkill).delete()
        db.query(EducationEntry).delete()
        db.query(ExperienceEntry).delete()
        db.query(ProjectEntry).delete()
        db.query(StudentProfile).delete()
        db.query(Skill).delete()
        db.query(InternshipListing).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = TestingSessionLocal()
    try:
        db.query(Application).delete()
        db.query(Match).delete()
        db.query(ProcessingJob).delete()
        db.query(StudentSkill).delete()
        db.query(EducationEntry).delete()
        db.query(ExperienceEntry).delete()
        db.query(ProjectEntry).delete()
        db.query(StudentProfile).delete()
        db.query(Skill).delete()
        db.query(InternshipListing).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def override_worker_sessionlocal(monkeypatch):
    """Ensure worker SessionLocal uses TestingSessionLocal."""
    monkeypatch.setattr("tasks.application_generation.SessionLocal", TestingSessionLocal)


def _mock_gemini_cover_letter_generate(monkeypatch, cover_letter_obj: LLMCoverLetter):
    """Helper to mock Gemini client structured generate_content method."""
    mock_response = MagicMock()
    mock_response.text = cover_letter_obj.model_dump_json()

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    monkeypatch.setattr(
        "app.services.application_generation.settings.GEMINI_API_KEY",
        "gemini-test-application-generation",
    )
    monkeypatch.setattr(
        "app.services.application_generation.genai.Client",
        lambda api_key: mock_client,
    )
    return mock_client


# ---------------------------------------------------------------------------
# 1. HTTP / API ENDPOINT TESTS (1 - 10)
# ---------------------------------------------------------------------------


def test_unauthenticated_generate_request_rejected(client: TestClient):
    """Test 1: Unauthenticated POST /applications/generate returns 401."""
    response = client.post(
        "/api/v1/applications/generate",
        json={"match_id": str(uuid4()), "tone": "professional"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_owner_can_enqueue_application_generation(client: TestClient, monkeypatch):
    """Test 2: Authenticated owner enqueues generation with 202 Accepted response."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Jane Student")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Backend Intern",
            company="TechCorp",
            location="Remote",
            work_type="remote",
            description="Build scalable APIs.",
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=90,
            skill_score=90,
            vector_score=90,
            attribute_score=90,
            skill_gap_analysis={"matching_skills": ["Python"]},
        )
        db.add(match)
        db.commit()
        match_id = match.id
    finally:
        db.close()

    mock_enqueue = MagicMock()
    monkeypatch.setattr(
        "app.api.v1.endpoints.applications.enqueue_application_generation",
        mock_enqueue,
    )

    response = client.post(
        "/api/v1/applications/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "match_id": str(match_id),
            "tone": "enthusiastic",
            "content_locale": "en",
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert data["message"] == "Personalized application generation enqueued."

    # Verify processing job created in database
    db = TestingSessionLocal()
    try:
        job = ProcessingJobRepository.get_by_id(db, UUID(data["job_id"]))
        assert job is not None
        assert job.user_id == user_id
        assert job.job_type == "application_generation"
        assert job.status == "queued"
    finally:
        db.close()

    # Verify enqueue called with durable arguments
    mock_enqueue.assert_called_once()
    kwargs = mock_enqueue.call_args.kwargs
    assert kwargs["user_id"] == user_id
    assert kwargs["match_id"] == match_id
    assert kwargs["tone"] == "enthusiastic"
    assert kwargs["content_locale"] == "en"


def test_nonexistent_match_returns_404(client: TestClient):
    """Test 3: Requesting generation for nonexistent match returns 404."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    response = client.post(
        "/api/v1/applications/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"match_id": str(uuid4()), "tone": "professional"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Match not found."


def test_another_user_match_returns_404_tenant_isolation(client: TestClient):
    """Test 4: Requesting generation for another candidate's match returns 404."""
    user_a = uuid4()
    user_b = uuid4()
    token_b = f"valid-user-{user_b}"

    db = TestingSessionLocal()
    try:
        prof_a = StudentProfile(id=uuid4(), user_id=user_a, full_name="Candidate A")
        db.add(prof_a)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Backend Intern",
            company="AlphaCorp",
            location="Remote",
            work_type="remote",
            description="Build backend microservices.",
        )
        db.add(listing)
        db.flush()

        match_a = Match(
            id=uuid4(),
            student_id=prof_a.id,
            internship_id=listing.id,
            overall_score=85,
            skill_score=90,
            vector_score=80,
            attribute_score=85,
        )
        db.add(match_a)
        db.commit()
        match_id = match_a.id
    finally:
        db.close()

    response = client.post(
        "/api/v1/applications/generate",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"match_id": str(match_id), "tone": "professional"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Match not found."


def test_invalid_content_locale_rejected_with_422(client: TestClient):
    """Test 5: Invalid content_locale returns 422 validation error."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    response = client.post(
        "/api/v1/applications/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "match_id": str(uuid4()),
            "tone": "professional",
            "content_locale": "fr",  # Not in ('en', 'tr', 'ar')
        },
    )
    assert response.status_code == 422


def test_empty_or_whitespace_tone_rejected_with_422(client: TestClient):
    """Test 6: Empty or whitespace-only tone returns 422."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    response = client.post(
        "/api/v1/applications/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"match_id": str(uuid4()), "tone": "   "},
    )
    assert response.status_code == 422


def test_enqueue_failure_updates_job_to_failed_and_returns_503(client: TestClient, monkeypatch):
    """Test 7: Enqueue failure updates DB job to failed and returns 503."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Dev",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=80,
            skill_score=80,
            vector_score=80,
            attribute_score=80,
        )
        db.add(match)
        db.commit()
        match_id = match.id
    finally:
        db.close()

    def failing_enqueue(*args, **kwargs):
        raise ConnectionError("Redis cluster unreachable")

    monkeypatch.setattr(
        "app.api.v1.endpoints.applications.enqueue_application_generation",
        failing_enqueue,
    )

    response = client.post(
        "/api/v1/applications/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"match_id": str(match_id), "tone": "professional"},
    )
    assert response.status_code == 503
    assert "Redis" not in response.text

    # Verify job marked failed in database with safe generic message
    db = TestingSessionLocal()
    try:
        job = (
            db.query(ProcessingJob)
            .filter_by(user_id=user_id, job_type="application_generation")
            .first()
        )
        assert job is not None
        assert job.status == "failed"
        assert job.progress_percent == 100
        assert job.error == "Failed to enqueue application generation job."
    finally:
        db.close()


def test_enqueue_application_generation_service(monkeypatch):
    """Test 8: application generation delegates exact job data to shared RQ."""
    calls = []

    def mock_enqueue(task_path, *args, **kwargs):
        calls.append((task_path, args, kwargs))
        return MagicMock()

    monkeypatch.setattr(
        "app.services.application_enqueue.enqueue_with_backpressure",
        mock_enqueue,
    )

    job_id = uuid4()
    user_id = uuid4()
    match_id = uuid4()

    enqueue_application_generation(
        job_id=job_id,
        user_id=user_id,
        match_id=match_id,
        tone="confident",
        content_locale="tr",
    )

    assert len(calls) == 1

    task_path, args, kwargs = calls[0]

    assert task_path == (
        "tasks.application_generation.run_application_generation"
    )

    assert args == (
        str(job_id),
        str(user_id),
        str(match_id),
        "confident",
        "tr",
    )

    assert kwargs == {
        "job_id": str(job_id),
        "job_timeout": 180,
    }


def test_generate_grounded_cover_letter_service_success(monkeypatch):
    """Test 9: generate_grounded_cover_letter calls Gemini with prompt context."""
    profile = StudentProfile(
        id=uuid4(),
        user_id=uuid4(),
        full_name="Alex Researcher",
        headline="AI Undergrad",
    )
    listing = InternshipListing(
        id=uuid4(),
        title="AI Engineer",
        company="Nexa",
        location="Remote",
        work_type="remote",
        description="Build LLMs.",
        required_skills=["Python", "PyTorch"],
    )
    match = Match(
        id=uuid4(),
        student_id=profile.id,
        internship_id=listing.id,
        overall_score=95,
        skill_score=95,
        vector_score=95,
        attribute_score=95,
        skill_gap_analysis={"matching_skills": ["Python", "PyTorch"]},
    )

    mock_llm_output = LLMCoverLetter(
        generated_cover_letter=(
            "Dear Hiring Team at Nexa, I am writing to express my enthusiasm "
            "for the AI Engineer role. With my background in Python and PyTorch..."
        )
    )
    mock_client = _mock_gemini_cover_letter_generate(monkeypatch, mock_llm_output)

    result = generate_grounded_cover_letter(
        profile=profile,
        internship=listing,
        match=match,
        tone="enthusiastic",
        candidate_skills=["Python", "PyTorch"],
        education_entries=["B.S. Computer Science"],
        content_locale="en",
    )

    assert result == mock_llm_output.generated_cover_letter
    mock_client.models.generate_content.assert_called_once()
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == settings.LLM_MODEL_NAME
    sys_msg = call_kwargs["config"].system_instruction
    user_msg = call_kwargs["contents"]

    # Security check: tone must NOT be in system instructions
    assert "Requested Tone: enthusiastic" not in sys_msg
    assert "UNTRUSTED DATA" in sys_msg
    assert "Target content locale: en" in sys_msg

    # User message contains tone under parameters and factual candidate data
    assert "Requested Tone: enthusiastic" in user_msg
    assert "Alex Researcher" in user_msg
    assert "Nexa" in user_msg
    assert "Python, PyTorch" in user_msg


def test_generate_grounded_cover_letter_missing_api_key_fails(monkeypatch):
    """Test 10: Missing/placeholder API key raises ValueError."""
    monkeypatch.setattr(
        "app.services.application_generation.settings.GEMINI_API_KEY",
        "placeholder-key",
    )

    profile = StudentProfile(id=uuid4(), user_id=uuid4(), full_name="Candidate")
    listing = InternshipListing(
        id=uuid4(),
        title="Dev",
        company="Co",
        location="Remote",
        work_type="remote",
        description="Dev.",
    )
    match = Match(
        id=uuid4(),
        student_id=profile.id,
        internship_id=listing.id,
        overall_score=80,
        skill_score=80,
        vector_score=80,
        attribute_score=80,
    )

    with pytest.raises(ValueError, match="GEMINI_API_KEY configuration"):
        generate_grounded_cover_letter(
            profile=profile,
            internship=listing,
            match=match,
            tone="professional",
        )


def test_generate_grounded_cover_letter_unescapes_html_entities(monkeypatch):
    """Test regression: generate_grounded_cover_letter unescapes HTML entities in generated text."""
    profile = StudentProfile(
        id=uuid4(),
        user_id=uuid4(),
        full_name="Caner Yılmaz",
        headline="Yazılım Mühendisi",
    )
    listing = InternshipListing(
        id=uuid4(),
        title="Gömülü Sistemler Stajyeri",
        company="Teknoloji & Araştırma A.Ş.",
        location="İstanbul",
        work_type="hybrid",
        description="Gömülü sensör sistemleri geliştirme.",
        required_skills=["C++", "Sensör"],
    )
    match = Match(
        id=uuid4(),
        student_id=profile.id,
        internship_id=listing.id,
        overall_score=90,
        skill_score=90,
        vector_score=90,
        attribute_score=90,
        skill_gap_analysis={"matching_skills": ["C++", "Sensör"]},
    )

    escaped_cover_letter = (
        "Sayın Yetkili, &#220;niversitesi m&#252;hendisliği öğrencisi olarak "
        "g&#246;mülü sens&#246;r sistemleri &amp; yazılım alanındaki staj pozisyonuna başvuruyorum."
    )
    mock_llm_output = LLMCoverLetter(
        generated_cover_letter=escaped_cover_letter
    )
    _mock_gemini_cover_letter_generate(monkeypatch, mock_llm_output)

    result = generate_grounded_cover_letter(
        profile=profile,
        internship=listing,
        match=match,
        tone="professional",
        candidate_skills=["C++", "Sensör"],
        education_entries=["Boğaziçi Üniversitesi"],
        content_locale="tr",
    )

    expected_cover_letter = (
        "Sayın Yetkili, Üniversitesi mühendisliği öğrencisi olarak "
        "gömülü sensör sistemleri & yazılım alanındaki staj pozisyonuna başvuruyorum."
    )
    assert result == expected_cover_letter
    assert "&#220;niversitesi" not in result
    assert "Üniversitesi" in result
    assert "mühendisliği" in result
    assert "gömülü" in result
    assert "sensör" in result
    assert "&amp;" not in result
    assert "&" in result


# ---------------------------------------------------------------------------
# 3. APPLICATION PERSISTENCE & REGENERATION SEMANTICS (14 - 17)
# ---------------------------------------------------------------------------


def test_first_generation_creates_application_with_status_saved():
    """Test 11: First cover letter generation creates Application with status='saved'."""
    db = TestingSessionLocal()
    try:
        student_id = uuid4()
        internship_id = uuid4()
        profile = StudentProfile(id=student_id, user_id=uuid4(), full_name="Candidate")
        db.add(profile)
        listing = InternshipListing(
            id=internship_id,
            title="Dev",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
        )
        db.add(listing)
        db.flush()

        app = ApplicationRepository.upsert_generated_cover_letter(
            db=db,
            student_id=student_id,
            internship_id=internship_id,
            generated_cover_letter="My tailored cover letter v1",
        )
        db.commit()

        assert app.id is not None
        assert app.status == "saved"
        assert app.generated_cover_letter == "My tailored cover letter v1"
        assert app.notes is None
    finally:
        db.close()


def test_regeneration_updates_cover_letter_and_preserves_status_and_notes():
    """
    Test 12: Regeneration updates cover letter in place and preserves
    status ('interviewing'), notes, and original id.
    """
    db = TestingSessionLocal()
    try:
        student_id = uuid4()
        internship_id = uuid4()
        profile = StudentProfile(id=student_id, user_id=uuid4(), full_name="Candidate")
        db.add(profile)
        listing = InternshipListing(
            id=internship_id,
            title="Dev",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
        )
        db.add(listing)
        db.flush()

        # Existing tracked application in 'interviewing' stage with notes
        existing_app = Application(
            id=uuid4(),
            student_id=student_id,
            internship_id=internship_id,
            status="interviewing",
            generated_cover_letter="Old cover letter v1",
            notes="First round interview on Friday",
        )
        db.add(existing_app)
        db.commit()
        orig_id = existing_app.id

        # Regenerate cover letter
        updated_app = ApplicationRepository.upsert_generated_cover_letter(
            db=db,
            student_id=student_id,
            internship_id=internship_id,
            generated_cover_letter="New regenerated cover letter v2",
        )
        db.commit()

        assert updated_app.id == orig_id
        assert updated_app.status == "interviewing"  # PRESERVED
        assert updated_app.notes == "First round interview on Friday"  # PRESERVED
        assert updated_app.generated_cover_letter == "New regenerated cover letter v2"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4. WORKER TASK LIFECYCLE TESTS (18 - 25)
# ---------------------------------------------------------------------------


def test_worker_run_application_generation_success(monkeypatch):
    """Test 13: Worker executes full pipeline and marks job completed."""
    user_id = uuid4()
    job_id = uuid4()

    db = TestingSessionLocal()
    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="application_generation",
            status="queued",
        )
        db.add(job)

        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Jane Candidate")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Backend Intern",
            company="AlphaCorp",
            location="Remote",
            work_type="remote",
            description="Python API dev.",
            required_skills=["Python"],
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=88,
            skill_score=90,
            vector_score=85,
            attribute_score=90,
            skill_gap_analysis={"matching_skills": ["Python"]},
        )
        db.add(match)
        db.commit()
        match_id = match.id
    finally:
        db.close()

    mock_llm_output = LLMCoverLetter(
        generated_cover_letter="Dear AlphaCorp, here is my grounded application."
    )
    _mock_gemini_cover_letter_generate(monkeypatch, mock_llm_output)

    result = run_application_generation(
        job_id=str(job_id),
        user_id=str(user_id),
        match_id=str(match_id),
        tone="professional",
        content_locale="en",
    )

    assert result["status"] == "completed"
    assert result["job_id"] == str(job_id)
    assert "application_id" in result

    # Verify DB state
    db = TestingSessionLocal()
    try:
        persisted_job = db.query(ProcessingJob).filter_by(id=job_id).first()
        assert persisted_job is not None
        assert persisted_job.status == "completed"
        assert persisted_job.progress_percent == 100
        assert persisted_job.result == {"application_id": result["application_id"]}

        persisted_app = db.query(Application).filter_by(id=UUID(result["application_id"])).first()
        assert persisted_app is not None
        assert persisted_app.generated_cover_letter == mock_llm_output.generated_cover_letter
        assert persisted_app.status == "saved"
    finally:
        db.close()


def test_worker_ownership_mismatch_rejected():
    """Test 14: Worker rejects job when job.user_id != user_id."""
    job_id = uuid4()
    user_a = uuid4()
    user_b = uuid4()

    db = TestingSessionLocal()
    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_a,
            job_type="application_generation",
            status="queued",
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    with pytest.raises(ValueError, match="Job ownership mismatch"):
        run_application_generation(
            job_id=job_id,
            user_id=user_b,
            match_id=uuid4(),
            tone="professional",
        )


def test_worker_job_type_mismatch_rejected():
    """Test 15: Worker rejects job with incorrect job_type."""
    job_id = uuid4()
    user_id = uuid4()

    db = TestingSessionLocal()
    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="cv_extraction",  # Wrong type
            status="queued",
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    with pytest.raises(ValueError, match="ProcessingJob type mismatch"):
        run_application_generation(
            job_id=job_id,
            user_id=user_id,
            match_id=uuid4(),
            tone="professional",
        )


def test_worker_unowned_match_fails_and_marks_job_failed():
    """Test 16: Worker with unowned match marks job failed in DB and raises."""
    job_id = uuid4()
    user_id = uuid4()
    other_user = uuid4()

    db = TestingSessionLocal()
    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="application_generation",
            status="queued",
        )
        db.add(job)

        other_profile = StudentProfile(id=uuid4(), user_id=other_user, full_name="Other")
        db.add(other_profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Dev",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=other_profile.id,
            internship_id=listing.id,
            overall_score=80,
            skill_score=80,
            vector_score=80,
            attribute_score=80,
        )
        db.add(match)
        db.commit()
        match_id = match.id
    finally:
        db.close()

    with pytest.raises(ValueError, match="Match '.*' not found or not owned"):
        run_application_generation(
            job_id=job_id,
            user_id=user_id,
            match_id=match_id,
            tone="professional",
        )

    # Verify job marked failed in database
    db = TestingSessionLocal()
    try:
        persisted_job = db.query(ProcessingJob).filter_by(id=job_id).first()
        assert persisted_job is not None
        assert persisted_job.status == "failed"
        assert persisted_job.progress_percent == 100
        assert persisted_job.error == "Application generation failed."
    finally:
        db.close()


def test_worker_provider_failure_rolls_back_application_mutation(monkeypatch):
    """
    Test 17: LLM provider failure rolls back Application mutation
    and marks job failed with safe generic error.
    """
    job_id = uuid4()
    user_id = uuid4()

    db = TestingSessionLocal()
    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="application_generation",
            status="queued",
        )
        db.add(job)

        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Dev",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=80,
            skill_score=80,
            vector_score=80,
            attribute_score=80,
        )
        db.add(match)
        db.commit()
        match_id = match.id
    finally:
        db.close()

    sensitive_error = "OpenAI rate limit exceeded with sk-SECRET_KEY_12345"

    def failing_generation(*args, **kwargs):
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(
        "tasks.application_generation.generate_grounded_cover_letter",
        failing_generation,
    )

    with pytest.raises(RuntimeError, match="OpenAI rate limit exceeded"):
        run_application_generation(
            job_id=job_id,
            user_id=user_id,
            match_id=match_id,
            tone="professional",
        )

    # Verify no application was created
    db = TestingSessionLocal()
    try:
        apps = db.query(Application).all()
        assert len(apps) == 0

        # Verify job marked failed in database with safe generic message
        persisted_job = db.query(ProcessingJob).filter_by(id=job_id).first()
        assert persisted_job is not None
        assert persisted_job.status == "failed"
        assert persisted_job.error == "Application generation failed."
        assert "SECRET_KEY" not in (persisted_job.error or "")
    finally:
        db.close()


def test_post_applications_generate_rate_limited_returns_429(client: TestClient, monkeypatch):
    """
    Test 23: Rate limit on POST /applications/generate returns HTTP 429
    before job creation.
    """
    user_id = uuid4()
    match_id = uuid4()
    token = f"valid-user-{user_id}"

    def failing_rate_limit(*, user_id, scope):
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many requests. Please retry later.",
                    "details": {"retry_after_seconds": 600},
                    "timestamp": "2026-08-14T00:00:00Z",
                }
            },
            headers={"Retry-After": "600"},
        )

    monkeypatch.setattr("app.api.v1.endpoints.applications.enforce_rate_limit", failing_rate_limit)

    enqueue_called = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.applications.enqueue_application_generation",
        lambda *args, **kwargs: enqueue_called.append(1),
    )

    response = client.post(
        "/api/v1/applications/generate",
        json={"match_id": str(match_id), "tone": "professional"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 429
    assert response.headers.get("retry-after") == "600"
    data = response.json()
    assert data["detail"]["error"]["code"] == "RATE_LIMITED"
    assert enqueue_called == []

    # Verify no processing job was created
    db = TestingSessionLocal()
    try:
        jobs = db.query(ProcessingJob).filter_by(user_id=user_id).all()
        assert len(jobs) == 0
    finally:
        db.close()

# ---------------------------------------------------------------------------
# QA-4C ? DISCARD SAVED APPLICATION DRAFT
# ---------------------------------------------------------------------------


def _create_application_for_discard_test(*, user_id, status_value="saved"):
    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Discard Test Candidate",
        )
        db.add(profile)

        listing = InternshipListing(
            id=uuid4(),
            title="Backend Intern",
            company="Discard Test Co",
            location="Remote",
            work_type="remote",
            description="Test internship for draft discard behavior.",
        )
        db.add(listing)
        db.flush()

        application = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            status=status_value,
            generated_cover_letter="Generated draft that may be discarded.",
        )
        db.add(application)
        db.commit()

        return application.id
    finally:
        db.close()


def test_owner_can_discard_saved_application_draft(client: TestClient):
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    application_id = _create_application_for_discard_test(
        user_id=user_id,
        status_value="saved",
    )

    response = client.delete(
        f"/api/v1/applications/{application_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204
    assert response.content == b""

    db = TestingSessionLocal()
    try:
        persisted = db.query(Application).filter_by(id=application_id).first()
        assert persisted is None
    finally:
        db.close()


def test_discard_draft_enforces_tenant_isolation(client: TestClient):
    owner_user_id = uuid4()
    other_user_id = uuid4()
    other_token = f"valid-user-{other_user_id}"

    application_id = _create_application_for_discard_test(
        user_id=owner_user_id,
        status_value="saved",
    )

    response = client.delete(
        f"/api/v1/applications/{application_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found."

    db = TestingSessionLocal()
    try:
        persisted = db.query(Application).filter_by(id=application_id).first()
        assert persisted is not None
        assert persisted.status == "saved"
    finally:
        db.close()


def test_submitted_application_cannot_be_discarded(client: TestClient):
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    application_id = _create_application_for_discard_test(
        user_id=user_id,
        status_value="applied",
    )

    response = client.delete(
        f"/api/v1/applications/{application_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert "Only saved application drafts can be discarded" in response.json()["detail"]

    db = TestingSessionLocal()
    try:
        persisted = db.query(Application).filter_by(id=application_id).first()
        assert persisted is not None
        assert persisted.status == "applied"
    finally:
        db.close()
