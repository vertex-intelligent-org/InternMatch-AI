"""
Unit & Integration Tests for Candidate Matches API.
Validates GET /api/v1/matches read access and POST /api/v1/matches/calculate
async enqueue endpoint, commit-before-enqueue boundary, enqueue failure recovery,
and enqueue helper service.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.db.models import InternshipListing, Match, ProcessingJob, StudentProfile
from app.repositories.match import MatchRepository
from app.services.match_enqueue import enqueue_match_calculation
from fastapi import HTTPException
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal

pytestmark = pytest.mark.usefixtures("mock_supabase_auth")


@pytest.fixture(autouse=True)
def clean_matches_table():
    """Ensure matches, processing_jobs, student_profiles, and listings are cleared."""
    db = TestingSessionLocal()
    try:
        db.query(Match).delete()
        db.query(ProcessingJob).delete()
        db.query(StudentProfile).delete()
        db.query(InternshipListing).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = TestingSessionLocal()
    try:
        db.query(Match).delete()
        db.query(ProcessingJob).delete()
        db.query(StudentProfile).delete()
        db.query(InternshipListing).delete()
        db.commit()
    finally:
        db.close()


def test_unauthenticated_matches_request_returns_401(client: TestClient):
    """Test 1: Unauthenticated request to GET /api/v1/matches returns 401 UNAUTHORIZED."""
    response = client.get("/api/v1/matches")
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_authenticated_user_with_no_matches_returns_empty_list(client: TestClient):
    """Test 2: Authenticated user with no persisted matches returns {"matches": []}."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    response = client.get("/api/v1/matches", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["matches"] == []


def test_authenticated_user_receives_own_matches_sorted(client: TestClient):
    """Test 3: Authenticated user receives own matches sorted by overall_score DESC with mapping."""
    user_id = uuid4()
    other_user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        # Create student profiles
        student = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate One")
        other_student = StudentProfile(id=uuid4(), user_id=other_user_id, full_name="Candidate Two")
        db.add_all([student, other_student])
        db.flush()

        # Create internship listings
        internship1 = InternshipListing(
            id=uuid4(),
            title="Backend Engineer Intern",
            company="CloudCorp",
            location="Remote",
            work_type="remote",
            description="Backend dev",
        )
        internship2 = InternshipListing(
            id=uuid4(),
            title="AI Research Intern",
            company="NexaAI",
            location="San Francisco, CA",
            work_type="hybrid",
            description="AI research",
        )
        db.add_all([internship1, internship2])
        db.flush()

        # Create matches
        match_lower = Match(
            id=uuid4(),
            student_id=student.id,
            internship_id=internship1.id,
            overall_score=80,
            skill_score=85,
            vector_score=75,
            attribute_score=80,
            why_you_match="Good fit for backend skills.",
            skill_gap_analysis={"missing_skills": ["Docker"]},
        )
        match_higher = Match(
            id=uuid4(),
            student_id=student.id,
            internship_id=internship2.id,
            overall_score=95,
            skill_score=98,
            vector_score=92,
            attribute_score=95,
            why_you_match="Excellent fit for AI skills.",
            skill_gap_analysis={"missing_skills": []},
        )
        other_match = Match(
            id=uuid4(),
            student_id=other_student.id,
            internship_id=internship1.id,
            overall_score=99,
            skill_score=99,
            vector_score=99,
            attribute_score=99,
        )
        db.add_all([match_lower, match_higher, other_match])
        db.commit()

        target_match_id_higher = match_higher.id
        target_match_id_lower = match_lower.id
        target_internship2_id = internship2.id
        target_internship1_id = internship1.id
    finally:
        db.close()

    response = client.get("/api/v1/matches", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()

    matches = data["matches"]
    assert len(matches) == 2

    first_match = matches[0]
    assert first_match["match_id"] == str(target_match_id_higher)
    assert first_match["overall_score"] == 95
    assert first_match["skill_score"] == 98
    assert first_match["vector_score"] == 92
    assert first_match["internship"]["id"] == str(target_internship2_id)
    assert first_match["internship"]["title"] == "AI Research Intern"
    assert first_match["internship"]["company"] == "NexaAI"
    assert first_match["internship"]["location"] == "San Francisco, CA"

    second_match = matches[1]
    assert second_match["match_id"] == str(target_match_id_lower)
    assert second_match["overall_score"] == 80
    assert second_match["internship"]["id"] == str(target_internship1_id)

    assert "why_you_match" not in first_match
    assert "skill_gap_analysis" not in first_match
    assert "attribute_score" not in first_match


def test_repository_query_level_ownership_enforcement():
    """Test 4: Direct repository test proving ownership restriction is enforced by SQL query."""
    user_a = uuid4()
    user_b = uuid4()

    db = TestingSessionLocal()
    try:
        student_a = StudentProfile(id=uuid4(), user_id=user_a, full_name="User A")
        student_b = StudentProfile(id=uuid4(), user_id=user_b, full_name="User B")

        db.add_all([student_a, student_b])
        db.flush()

        internship = InternshipListing(
            id=uuid4(),
            title="DevOps Intern",
            company="OpsTech",
            location="Remote",
            work_type="remote",
            description="DevOps engineering",
        )
        db.add(internship)
        db.flush()

        match_a = Match(
            id=uuid4(),
            student_id=student_a.id,
            internship_id=internship.id,
            overall_score=85,
            skill_score=85,
            vector_score=85,
            attribute_score=85,
        )
        db.add(match_a)
        db.commit()

        matches_a = MatchRepository.get_matches_for_user(db=db, user_id=user_a)
        assert len(matches_a) == 1
        assert matches_a[0][0].id == match_a.id

        matches_b = MatchRepository.get_matches_for_user(db=db, user_id=user_b)
        assert len(matches_b) == 0
    finally:
        db.close()


# POST /api/v1/matches/calculate ENDPOINT TESTS (1 - 11)


def test_post_calculate_without_jwt_returns_401(client: TestClient, monkeypatch):
    """Test 1: Unauthenticated POST /matches/calculate returns 401 UNAUTHORIZED."""
    called = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.matches.enqueue_match_calculation",
        lambda **kwargs: called.append(1),
    )

    response = client.post("/api/v1/matches/calculate")
    assert response.status_code == 401

    db = TestingSessionLocal()
    try:
        assert db.query(ProcessingJob).count() == 0
    finally:
        db.close()
    assert called == []


def test_post_calculate_authenticated_success_202(client: TestClient, monkeypatch):
    """Test 2: Authenticated POST returns HTTP 202 and exact payload schema."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    monkeypatch.setattr(
        "app.api.v1.endpoints.matches.enqueue_match_calculation",
        lambda **kwargs: None,
    )

    response = client.post(
        "/api/v1/matches/calculate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 202
    data = response.json()

    assert set(data.keys()) == {"job_id", "status", "message"}
    assert data["status"] == "queued"
    assert data["message"] == "Matching calculation enqueued."


def test_post_calculate_persists_exactly_one_processing_job(client: TestClient, monkeypatch):
    """Test 3: POST persists exactly one ProcessingJob with status=queued and progress=0."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    monkeypatch.setattr(
        "app.api.v1.endpoints.matches.enqueue_match_calculation",
        lambda **kwargs: None,
    )

    response = client.post(
        "/api/v1/matches/calculate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 202
    job_id_str = response.json()["job_id"]

    db = TestingSessionLocal()
    try:
        jobs = db.query(ProcessingJob).all()
        assert len(jobs) == 1
        job = jobs[0]
        assert str(job.id) == job_id_str
        assert job.user_id == user_id
        assert job.job_type == "match_calculation"
        assert job.status == "queued"
        assert job.progress_percent == 0
    finally:
        db.close()


def test_post_calculate_identity_is_jwt_derived(client: TestClient, monkeypatch):
    """Tests 4 & 5 & 6: Identity is JWT-derived, limit=50, and job_id matches ProcessingJob."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    enqueue_args = {}

    def mock_enqueue(job_id, user_id, candidate_limit):
        enqueue_args["job_id"] = job_id
        enqueue_args["user_id"] = user_id
        enqueue_args["candidate_limit"] = candidate_limit

    monkeypatch.setattr(
        "app.api.v1.endpoints.matches.enqueue_match_calculation",
        mock_enqueue,
    )

    response = client.post(
        "/api/v1/matches/calculate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 202
    job_id_str = response.json()["job_id"]

    assert str(enqueue_args["job_id"]) == job_id_str
    assert enqueue_args["user_id"] == user_id
    assert enqueue_args["candidate_limit"] == 50


def test_post_calculate_commit_before_enqueue_mandatory(client: TestClient, monkeypatch):
    """
    Test 7 (MANDATORY): Enqueue monkeypatch opens a fresh TestingSessionLocal and proves
    ProcessingJob is ALREADY committed and visible in the database before enqueue executes.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    committed_job_visible = []

    def mock_enqueue_check_commit(job_id, user_id, candidate_limit):
        # Open a fresh independent database session to verify commit occurred before enqueue
        fresh_db = TestingSessionLocal()
        try:
            persisted = fresh_db.query(ProcessingJob).filter_by(id=job_id).first()
            if persisted and persisted.status == "queued" and persisted.progress_percent == 0:
                committed_job_visible.append(True)
            else:
                committed_job_visible.append(False)
        finally:
            fresh_db.close()

    monkeypatch.setattr(
        "app.api.v1.endpoints.matches.enqueue_match_calculation",
        mock_enqueue_check_commit,
    )

    response = client.post(
        "/api/v1/matches/calculate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 202
    assert committed_job_visible == [True]


def test_post_calculate_enqueue_failure_returns_503_and_marks_job_failed(
    client: TestClient, monkeypatch
):
    """
    Tests 8 & 9 & 10: Enqueue failure returns 503, updates original job to failed (100%),
    does not create a second job, and persists safe generic error message.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    sensitive_error = "Redis Connection Error with redis://user:SECRET@redis:6379/0"

    def failing_enqueue(job_id, user_id, candidate_limit):
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(
        "app.api.v1.endpoints.matches.enqueue_match_calculation",
        failing_enqueue,
    )

    response = client.post(
        "/api/v1/matches/calculate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503

    db = TestingSessionLocal()
    try:
        jobs = db.query(ProcessingJob).all()
        # Proves exactly ONE ProcessingJob exists (no duplicate job created)
        assert len(jobs) == 1
        job = jobs[0]
        assert job.status == "failed"
        assert job.progress_percent == 100
        assert job.result is None
        assert job.error == "Failed to enqueue match calculation job."
        assert "SECRET" not in (job.error or "")
    finally:
        db.close()


def test_post_calculate_db_create_failure_prevents_enqueue(client: TestClient, monkeypatch):
    """Test 11: DB create failure before enqueue ensures enqueue helper is never called."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    called = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.matches.enqueue_match_calculation",
        lambda **kwargs: called.append(1),
    )

    def failing_create(db, user_id, job_type):
        raise RuntimeError("DB Disk Full")

    monkeypatch.setattr(
        "app.repositories.processing_job.ProcessingJobRepository.create",
        failing_create,
    )

    with pytest.raises(RuntimeError, match="DB Disk Full"):
        client.post(
            "/api/v1/matches/calculate",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert called == []

    db = TestingSessionLocal()
    try:
        assert db.query(ProcessingJob).count() == 0
    finally:
        db.close()


# ENQUEUE SERVICE HELPER TESTS (12 - 17)


def test_enqueue_helper_delegates_to_shared_backpressure(monkeypatch):
    """Test 12: Match enqueue delegates to the shared bounded RQ boundary."""
    calls = []

    def mock_enqueue(task_path, *args, **kwargs):
        calls.append((task_path, args, kwargs))
        return MagicMock()

    monkeypatch.setattr(
        "app.services.match_enqueue.enqueue_with_backpressure",
        mock_enqueue,
    )

    job_id = uuid4()
    user_id = uuid4()

    enqueue_match_calculation(
        job_id=job_id,
        user_id=user_id,
        candidate_limit=25,
    )

    assert len(calls) == 1

    task_path, args, kwargs = calls[0]

    assert task_path == "tasks.match_calculation.run_match_calculation"
    assert args == (
        str(job_id),
        str(user_id),
        25,
    )
    assert kwargs == {
        "job_id": str(job_id),
        "job_timeout": 180,
    }


def test_enqueue_helper_default_candidate_limit_is_forwarded(monkeypatch):
    """Test 13: Default candidate_limit=50 reaches the shared enqueue boundary."""
    calls = []

    def mock_enqueue(task_path, *args, **kwargs):
        calls.append((task_path, args, kwargs))
        return MagicMock()

    monkeypatch.setattr(
        "app.services.match_enqueue.enqueue_with_backpressure",
        mock_enqueue,
    )

    job_id = uuid4()
    user_id = uuid4()

    enqueue_match_calculation(
        job_id=job_id,
        user_id=user_id,
    )

    assert len(calls) == 1

    _, args, _ = calls[0]

    assert args == (
        str(job_id),
        str(user_id),
        50,
    )


def test_enqueue_helper_rq_call_shape_and_keyword_protection(monkeypatch):
    """
    Tests 14 & 15 & 16: shared enqueue receives exact dotted task path,
    durable positional primitives, and protected RQ job_id keyword.
    """
    enqueue_calls = []

    def mock_enqueue(task_path, *args, **kwargs):
        enqueue_calls.append((task_path, args, kwargs))
        return MagicMock()

    monkeypatch.setattr(
        "app.services.match_enqueue.enqueue_with_backpressure",
        mock_enqueue,
    )

    job_id = uuid4()
    user_id = uuid4()

    enqueue_match_calculation(
        job_id=job_id,
        user_id=user_id,
        candidate_limit=50,
    )

    assert len(enqueue_calls) == 1

    task_path, args, kwargs = enqueue_calls[0]

    assert task_path == "tasks.match_calculation.run_match_calculation"
    assert args == (
        str(job_id),
        str(user_id),
        50,
    )
    assert kwargs == {
        "job_id": str(job_id),
        "job_timeout": 180,
    }


def test_enqueue_helper_candidate_limit_zero_or_negative_raises_value_error(
    monkeypatch,
):
    """Test 17: invalid candidate limits fail before shared enqueue is called."""
    enqueue_calls = []

    def mock_enqueue(*args, **kwargs):
        enqueue_calls.append((args, kwargs))
        return MagicMock()

    monkeypatch.setattr(
        "app.services.match_enqueue.enqueue_with_backpressure",
        mock_enqueue,
    )

    job_id = uuid4()
    user_id = uuid4()

    with pytest.raises(
        ValueError,
        match="Limit must be > 0",
    ):
        enqueue_match_calculation(
            job_id=job_id,
            user_id=user_id,
            candidate_limit=0,
        )

    with pytest.raises(
        ValueError,
        match="Limit must be > 0",
    ):
        enqueue_match_calculation(
            job_id=job_id,
            user_id=user_id,
            candidate_limit=-10,
        )

    assert enqueue_calls == []


def test_calculate_matches_rate_limited_returns_429_before_job_creation(
    client: TestClient, monkeypatch
):
    """
    Test 18: Rate limit on /matches/calculate returns HTTP 429
    and creates no job/enqueue.
    """
    user_id = uuid4()
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

    monkeypatch.setattr("app.api.v1.endpoints.matches.enforce_rate_limit", failing_rate_limit)

    enqueue_called = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.matches.enqueue_match_calculation",
        lambda *args, **kwargs: enqueue_called.append(1),
    )

    response = client.post(
        "/api/v1/matches/calculate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 429
    assert response.headers.get("retry-after") == "600"
    data = response.json()
    assert data["detail"]["error"]["code"] == "RATE_LIMITED"
    assert enqueue_called == []

    db = TestingSessionLocal()
    try:
        jobs = db.query(ProcessingJob).filter_by(user_id=user_id).all()
        assert len(jobs) == 0
    finally:
        db.close()
