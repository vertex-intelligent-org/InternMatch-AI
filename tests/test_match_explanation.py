"""
Unit & Integration Tests for Grounded Match Explanation (Gate 2.27).
Tests POST /api/v1/matches/{id}/explanation async endpoint authentication,
tenant isolation, grounding from persisted match/profile data, LLM mocking,
caching/persistence of why_you_match, and preservation of deterministic scores.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.db.models import (
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
from app.services.match_explanation import (
    LLMMatchExplanation,
    generate_grounded_match_explanation,
    get_or_create_match_explanation,
)
from fastapi import HTTPException
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal

pytestmark = pytest.mark.usefixtures("mock_supabase_auth")


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure all related tables are cleared before and after each test."""
    db = TestingSessionLocal()
    try:
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


def _mock_gemini_explanation_generate(monkeypatch, explanation_obj: LLMMatchExplanation):
    """Helper to mock Gemini client structured generate_content method."""
    mock_response = MagicMock()
    mock_response.text = explanation_obj.model_dump_json()

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    monkeypatch.setattr(
        "app.services.match_explanation.settings.GEMINI_API_KEY",
        "gemini-test-match-explanation",
    )
    monkeypatch.setattr(
        "app.services.match_explanation.genai.Client",
        lambda api_key: mock_client,
    )
    return mock_client


# ---------------------------------------------------------------------------
# 1. AUTHENTICATION & ACCESS CONTROL TESTS (1 - 3)
# ---------------------------------------------------------------------------



class _DirectMatchExplanationResponse:
    """Small adapter for legacy service-level assertions."""

    def __init__(self, status_code, payload):
        import json

        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(
            payload,
            default=str,
        )
        self.content = self.text.encode(
            "utf-8"
        )

    def json(self):
        return self._payload


def _direct_match_explanation_service_request(
    url,
    headers=None,
    **_kwargs,
):
    """
    Exercise the Match Explanation service directly.

    The production HTTP boundary is now asynchronous POST/202.
    Provider/cache/persistence behavior belongs at service level,
    while endpoint auth/ownership/validation remain HTTP tests.
    """
    from urllib.parse import (
        parse_qs,
        urlparse,
    )
    from uuid import UUID

    from app.services.match_explanation import (
        get_or_create_match_explanation,
    )

    parsed = urlparse(str(url))
    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    if (
        len(parts) < 3
        or parts[-1] != "explanation"
    ):
        raise AssertionError(
            f"Unexpected match explanation URL: {url}"
        )

    match_id = UUID(parts[-2])

    query = parse_qs(
        parsed.query
    )

    locale = query.get(
        "content_locale",
        ["en"],
    )[0]

    authorization = (
        (headers or {})
        .get("Authorization", "")
        .strip()
    )

    prefix = "Bearer valid-user-"

    if not authorization.startswith(
        prefix
    ):
        return _DirectMatchExplanationResponse(
            401,
            {"detail": "Not authenticated"},
        )

    user_id = UUID(
        authorization[len(prefix):]
    )

    db = TestingSessionLocal()

    try:
        try:
            result = (
                get_or_create_match_explanation(
                    db=db,
                    match_id=match_id,
                    user_id=user_id,
                    content_locale=locale,
                )
            )
        except ValueError:
            # The old synchronous endpoint translated
            # service-availability ValueError to safe 503.
            # Durable worker failure transport is covered
            # separately by Part C worker tests.
            return _DirectMatchExplanationResponse(
                503,
                {
                    "detail":
                    "Match explanation service is "
                    "temporarily unavailable."
                },
            )
        except Exception:
            return _DirectMatchExplanationResponse(
                500,
                {
                    "detail":
                    "Failed to retrieve match explanation."
                },
            )

        if result is None:
            return _DirectMatchExplanationResponse(
                404,
                {"detail": "Match not found."},
            )

        return _DirectMatchExplanationResponse(
            200,
            result.model_dump(
                mode="json"
            ),
        )
    finally:
        db.close()


def test_unauthenticated_explanation_request_returns_401(client: TestClient):
    """Test 1: Unauthenticated GET returns 401 UNAUTHORIZED."""
    match_id = uuid4()
    response = client.post(f"/api/v1/matches/{match_id}/explanation")
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_nonexistent_match_returns_404(client: TestClient):
    """Test 2: Requesting explanation for nonexistent match returns 404."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    nonexistent_id = uuid4()

    response = client.post(
        f"/api/v1/matches/{nonexistent_id}/explanation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Match not found."


def test_other_user_match_returns_404_tenant_isolation(client: TestClient):
    """Test 3: Another user's match returns 404 (never exposed)."""
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
            skill_gap_analysis={
                "matching_skills": ["Python"],
                "missing_skills": ["Docker"],
            },
        )
        db.add(match_a)
        db.commit()
        target_match_id = match_a.id
    finally:
        db.close()

    response = client.post(
        f"/api/v1/matches/{target_match_id}/explanation",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Match not found."


# ---------------------------------------------------------------------------
# 2. GROUNDED EXPLANATION GENERATION & PERSISTENCE (4 - 10)
# ---------------------------------------------------------------------------


def test_authenticated_owner_gets_explanation_successfully(client: TestClient, monkeypatch):
    """
    Test 4: Authenticated owner receives full grounded explanation with
    exact contract schema, matching/missing skills copied from canonical gap,
    and overall_score matching persisted Match.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Jane Student",
            headline="CS Junior @ State Tech",
        )
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Python Cloud Intern",
            company="CloudTech",
            location="Remote",
            work_type="remote",
            description="Develop Python APIs on AWS.",
            required_skills=["Python", "FastAPI"],
            preferred_skills=["Docker", "Redis"],
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
            skill_gap_analysis={
                "matching_skills": ["Python", "FastAPI"],
                "missing_skills": ["Docker", "Redis"],
                "summary": "",
                "recommendations": [],
            },
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    mock_llm_output = LLMMatchExplanation(
        why_you_match=(
            "Your experience with Python and FastAPI matches CloudTech's core "
            "backend stack perfectly."
        ),
        skill_gap_summary=("You are missing 2 preferred containerization and caching skills."),
        recommendations=[
            "Complete a 2-hour tutorial on Docker basics.",
            "Learn basic Redis key-value caching patterns.",
        ],
    )
    _mock_gemini_explanation_generate(monkeypatch, mock_llm_output)

    response = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()

    # Exact contract schema verification
    assert data["match_id"] == str(target_match_id)
    assert data["overall_score"] == 88
    assert data["why_you_match"] == mock_llm_output.why_you_match
    assert data["matching_skills"] == ["Python", "FastAPI"]
    assert data["missing_skills"] == ["Docker", "Redis"]
    assert data["skill_gap_analysis"]["summary"] == mock_llm_output.skill_gap_summary
    assert data["skill_gap_analysis"]["recommendations"] == mock_llm_output.recommendations


def test_generated_explanation_is_persisted_and_cached(client: TestClient, monkeypatch):
    """
    Test 5: First request generates and persists why_you_match and gap recommendations.
    Second request returns the cached result without calling Gemini.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Backend Intern",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Backend dev.",
            required_skills=["Python"],
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=92,
            skill_score=95,
            vector_score=90,
            attribute_score=90,
            skill_gap_analysis={
                "matching_skills": ["Python"],
                "missing_skills": ["Docker"],
                "summary": "",
                "recommendations": [],
            },
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    mock_llm_output = LLMMatchExplanation(
        why_you_match="Great Python skills for the backend role.",
        skill_gap_summary="Missing Docker containerization skill.",
        recommendations=["Practice Dockerizing apps."],
    )
    mock_client = _mock_gemini_explanation_generate(monkeypatch, mock_llm_output)

    # First call: triggers Gemini generate_content
    resp1 = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200
    assert mock_client.models.generate_content.call_count == 1

    # Verify database was updated
    db = TestingSessionLocal()
    try:
        persisted_match = db.query(Match).filter_by(id=target_match_id).first()
        assert persisted_match is not None
        assert persisted_match.skill_gap_analysis is not None
        assert persisted_match.why_you_match == mock_llm_output.why_you_match
        assert persisted_match.skill_gap_analysis["summary"] == mock_llm_output.skill_gap_summary
        assert (
            persisted_match.skill_gap_analysis["recommendations"] == mock_llm_output.recommendations
        )
        # Verify deterministic scores were NOT altered
        assert persisted_match.overall_score == 92
        assert persisted_match.skill_score == 95
        assert persisted_match.vector_score == 90
        assert persisted_match.attribute_score == 90
    finally:
        db.close()

    # Second call: uses cached explanation (Gemini not called again)
    resp2 = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["why_you_match"] == mock_llm_output.why_you_match
    assert mock_client.models.generate_content.call_count == 1


def test_matching_and_missing_skills_are_never_overwritten_by_llm(client: TestClient, monkeypatch):
    """Test 6: matching_skills and missing_skills are strictly preserved."""
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

        canonical_matching = ["Python", "FastAPI", "SQL"]
        canonical_missing = ["Kubernetes", "AWS"]

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=75,
            skill_score=80,
            vector_score=70,
            attribute_score=75,
            skill_gap_analysis={
                "matching_skills": canonical_matching,
                "missing_skills": canonical_missing,
                "summary": "",
                "recommendations": [],
            },
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    mock_llm_output = LLMMatchExplanation(
        why_you_match="Solid candidate for Python stack.",
        skill_gap_summary="Gap in cloud and orchestration.",
        recommendations=["Study Kubernetes."],
    )
    _mock_gemini_explanation_generate(monkeypatch, mock_llm_output)

    resp = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["matching_skills"] == canonical_matching
    assert data["missing_skills"] == canonical_missing


def test_provider_failure_returns_safe_503_and_does_not_leak_secrets(
    client: TestClient, monkeypatch
):
    """Test 7: Gemini failure returns HTTP 503 and does not leak secrets."""
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
            skill_gap_analysis={
                "matching_skills": ["Python"],
                "missing_skills": [],
            },
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    def failing_gemini(*args, **kwargs):
        raise ValueError("GEMINI_API_KEY configuration is missing or placeholder value")

    monkeypatch.setattr(
        "app.services.match_explanation.generate_grounded_match_explanation",
        failing_gemini,
    )

    response = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    assert "sk-" not in response.text
    assert "GEMINI_API_KEY" not in response.text


def test_malformed_canonical_skill_gap_handled_gracefully(client: TestClient, monkeypatch):
    """Test 8: Match with None skill_gap_analysis is handled gracefully."""
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
            overall_score=70,
            skill_score=70,
            vector_score=70,
            attribute_score=70,
            skill_gap_analysis=None,  # None instead of dict
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    mock_llm_output = LLMMatchExplanation(
        why_you_match="Good fit.",
        skill_gap_summary="No specific gaps.",
        recommendations=[],
    )
    _mock_gemini_explanation_generate(monkeypatch, mock_llm_output)

    response = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["matching_skills"] == []
    assert data["missing_skills"] == []


def test_generate_grounded_match_explanation_unit(monkeypatch):
    """Test 9: Direct unit test for generate_grounded_match_explanation."""
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

    mock_llm_output = LLMMatchExplanation(
        why_you_match="Alex has strong PyTorch fundamentals for Nexa.",
        skill_gap_summary="No missing required skills.",
        recommendations=["Review transformer architectures."],
    )
    _mock_gemini_explanation_generate(monkeypatch, mock_llm_output)

    result = generate_grounded_match_explanation(
        profile=profile,
        internship=listing,
        overall_score=94,
        matching_skills=["Python", "PyTorch"],
        missing_skills=[],
        candidate_skills=["Python", "PyTorch", "Git"],
        education_entries=["B.S. CS at Tech (2023-2027)"],
    )

    assert result.why_you_match == mock_llm_output.why_you_match
    assert result.skill_gap_summary == mock_llm_output.skill_gap_summary
    assert result.recommendations == mock_llm_output.recommendations


def test_get_or_create_match_explanation_returns_none_for_missing_record():
    """Test 10: get_or_create_match_explanation returns None for missing match."""
    db = TestingSessionLocal()
    try:
        result = get_or_create_match_explanation(
            db=db,
            match_id=uuid4(),
            user_id=uuid4(),
        )
        assert result is None
    finally:
        db.close()


def test_get_match_explanation_rate_limited_returns_429(client: TestClient, monkeypatch):
    """
    Test 11: Rate limit on GET /matches/{id}/explanation returns HTTP 429
    before LLM generation.
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

    monkeypatch.setattr("app.api.v1.endpoints.matches.enforce_rate_limit", failing_rate_limit)

    llm_called = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.matches.enqueue_match_explanation_generation",
        lambda *args, **kwargs: llm_called.append(1),
    )

    response = client.post(
        f"/api/v1/matches/{match_id}/explanation",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 429
    assert response.headers.get("retry-after") == "600"
    data = response.json()
    assert data["detail"]["error"]["code"] == "RATE_LIMITED"
    assert llm_called == []


# ---------------------------------------------------------------------------
# 3. LOCALE-SAFE WHY YOU MATCH TESTS (GATE 2.38F-C5E2)
# ---------------------------------------------------------------------------


class FakeMatchExplanationRedis:
    """In-memory Redis fake for match explanation locale caching tests."""

    def __init__(self, should_fail: bool = False):
        self.store = {}
        self.ttls = {}
        self.should_fail = should_fail
        self.set_calls = []
        self.delete_calls = []

    def get(self, key: str):
        if self.should_fail:
            import redis
            raise redis.ConnectionError("Simulated Redis connection failure")
        return self.store.get(key)

    def set(self, key: str, value: str, ex=None, nx=False):
        if self.should_fail:
            import redis
            raise redis.ConnectionError("Simulated Redis connection failure")
        self.set_calls.append({"key": key, "value": value, "ex": ex, "nx": nx})
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        if ex:
            self.ttls[key] = ex
        return True

    def delete(self, *keys: str):
        if self.should_fail:
            import redis
            raise redis.ConnectionError("Simulated Redis connection failure")
        deleted = 0
        for k in keys:
            self.delete_calls.append(k)
            if k in self.store:
                del self.store[k]
                deleted += 1
        return deleted


def test_get_match_explanation_backward_compatible_default_locale(
    client: TestClient, monkeypatch
):
    """Verify endpoint without content_locale defaults to English behavior."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Backend Intern",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
            required_skills=["Python"],
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=85,
            skill_score=85,
            vector_score=85,
            attribute_score=85,
            why_you_match="Persisted English narrative.",
            skill_gap_analysis={
                "matching_skills": ["Python"],
                "missing_skills": [],
                "summary": "Persisted English summary.",
                "recommendations": ["Persisted English Rec"],
            },
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    gemini_mock = MagicMock()
    monkeypatch.setattr(
        "app.services.match_explanation.generate_grounded_match_explanation",
        gemini_mock,
    )

    # 1. No content_locale parameter
    res_default = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_default.status_code == 200
    assert res_default.json()["why_you_match"] == "Persisted English narrative."

    # 2. Explicit content_locale=en
    res_en = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=en",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_en.status_code == 200
    assert res_en.json()["why_you_match"] == "Persisted English narrative."
    gemini_mock.assert_not_called()

    # Malformed recommendations must invalidate the canonical English cache.
    repair_output = LLMMatchExplanation(
        why_you_match="Regenerated English narrative.",
        skill_gap_summary="Regenerated English summary.",
        recommendations=["Regenerated English Rec"],
    )
    gemini_mock.return_value = repair_output

    db = TestingSessionLocal()
    try:
        persisted = db.query(Match).filter_by(id=target_match_id).first()
        persisted.skill_gap_analysis = {
            **persisted.skill_gap_analysis,
            "recommendations": "malformed-not-a-list",
        }
        db.commit()
    finally:
        db.close()

    res_repaired = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=en",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_repaired.status_code == 200
    assert res_repaired.json()["why_you_match"] == repair_output.why_you_match
    assert (
        res_repaired.json()["skill_gap_analysis"]["recommendations"]
        == repair_output.recommendations
    )
    assert gemini_mock.call_count == 1

    db = TestingSessionLocal()
    try:
        persisted = db.query(Match).filter_by(id=target_match_id).first()
        assert persisted.skill_gap_analysis["recommendations"] == repair_output.recommendations
    finally:
        db.close()


def test_get_match_explanation_invalid_locale_returns_422(client: TestClient):
    """Verify non-supported content_locale returns HTTP 422."""
    user_id = uuid4()
    match_id = uuid4()
    token = f"valid-user-{user_id}"

    response = client.post(
        f"/api/v1/matches/{match_id}/explanation?content_locale=fr",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422

    response_malformed = client.post(
        f"/api/v1/matches/{match_id}/explanation?content_locale=invalid",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response_malformed.status_code == 422


def test_get_match_explanation_tr_does_not_use_english_db_cache_and_does_not_mutate_db(
    client: TestClient, monkeypatch
):
    """
    CRITICAL INVARIANTS:
    1. Turkish request must NOT treat existing English DB narrative as a cache hit.
    2. Turkish generation must NOT overwrite match.why_you_match in DB.
    3. Turkish generation must NOT overwrite skill_gap_analysis summary/recs in DB.
    4. matching_skills and missing_skills remain strictly canonical technical identifiers.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Jane Doe")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="AI Engineer Intern",
            company="NexaAI",
            location="Istanbul, Turkey",
            work_type="hybrid",
            description="Build LLMs.",
            required_skills=["Python", "PyTorch"],
            preferred_skills=["Docker"],
        )
        db.add(listing)
        db.flush()

        canonical_matching = ["Python", "PyTorch"]
        canonical_missing = ["Docker"]

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=90,
            skill_score=95,
            vector_score=85,
            attribute_score=90,
            why_you_match="Canonical English why you match narrative.",
            skill_gap_analysis={
                "matching_skills": canonical_matching,
                "missing_skills": canonical_missing,
                "summary": "Canonical English summary.",
                "recommendations": ["Canonical English Rec 1"],
            },
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    fake_redis = FakeMatchExplanationRedis()
    monkeypatch.setattr(
        "app.services.match_explanation._get_redis_client",
        lambda: fake_redis,
    )

    mock_llm_output = LLMMatchExplanation(
        why_you_match="Python ve PyTorch deneyiminiz NexaAI icin mukemmel bir eslesmedir.",
        skill_gap_summary="Docker becerisinde eksiklik var.",
        recommendations=["Temel Docker egitimini tamamlayin."],
    )
    _mock_gemini_explanation_generate(monkeypatch, mock_llm_output)

    response = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=tr",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()

    # Response contains Turkish localized narrative
    assert data["why_you_match"] == mock_llm_output.why_you_match
    assert data["skill_gap_analysis"]["summary"] == mock_llm_output.skill_gap_summary
    assert data["skill_gap_analysis"]["recommendations"] == mock_llm_output.recommendations

    # Response contains canonical skills & score
    assert data["overall_score"] == 90
    assert data["matching_skills"] == canonical_matching
    assert data["missing_skills"] == canonical_missing

    # PROOF: DB was NOT mutated by TR generation!
    db = TestingSessionLocal()
    try:
        persisted = db.query(Match).filter_by(id=target_match_id).first()
        assert persisted.why_you_match == "Canonical English why you match narrative."
        assert persisted.skill_gap_analysis["summary"] == "Canonical English summary."
        assert persisted.skill_gap_analysis["recommendations"] == ["Canonical English Rec 1"]
        assert persisted.skill_gap_analysis["matching_skills"] == canonical_matching
        assert persisted.skill_gap_analysis["missing_skills"] == canonical_missing
    finally:
        db.close()


def test_get_match_explanation_ar_does_not_use_english_db_cache_and_does_not_mutate_db(
    client: TestClient, monkeypatch
):
    """
    Verify Arabic request generates and returns Arabic narrative without mutating DB.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Ahmad")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Backend Intern",
            company="AlphaCorp",
            location="Remote",
            work_type="remote",
            description="Dev.",
            required_skills=["Python"],
            preferred_skills=["Redis"],
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
            why_you_match="English DB narrative.",
            skill_gap_analysis={
                "matching_skills": ["Python"],
                "missing_skills": ["Redis"],
                "summary": "English DB summary.",
                "recommendations": ["English Rec 1"],
            },
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    fake_redis = FakeMatchExplanationRedis()
    monkeypatch.setattr(
        "app.services.match_explanation._get_redis_client",
        lambda: fake_redis,
    )

    mock_llm_output = LLMMatchExplanation(
        why_you_match="\u0646\u0635 \u0639\u0631\u0628\u064a.",
        skill_gap_summary="\u0645\u0644\u062e\u0635 \u0639\u0631\u0628\u064a.",
        recommendations=["\u062a\u0648\u0635\u064a\u0629 \u0639\u0631\u0628\u064a\u0629."],
    )
    _mock_gemini_explanation_generate(monkeypatch, mock_llm_output)

    response = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=ar",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["why_you_match"] == mock_llm_output.why_you_match
    assert data["skill_gap_analysis"]["summary"] == mock_llm_output.skill_gap_summary
    assert data["matching_skills"] == ["Python"]
    assert data["missing_skills"] == ["Redis"]

    # PROOF: DB was NOT mutated by AR generation!
    db = TestingSessionLocal()
    try:
        persisted = db.query(Match).filter_by(id=target_match_id).first()
        assert persisted.why_you_match == "English DB narrative."
        assert persisted.skill_gap_analysis["summary"] == "English DB summary."
    finally:
        db.close()


def test_get_match_explanation_tr_redis_cache_hit_avoids_second_gemini_call(
    client: TestClient, monkeypatch
):
    """Verify Turkish cache hit returns cached translation without second Gemini call."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Student")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Backend Intern",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
            required_skills=["Python"],
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
            why_you_match="English text",
            skill_gap_analysis={"matching_skills": ["Python"], "missing_skills": []},
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    fake_redis = FakeMatchExplanationRedis()
    monkeypatch.setattr(
        "app.services.match_explanation._get_redis_client",
        lambda: fake_redis,
    )

    mock_llm_output = LLMMatchExplanation(
        why_you_match="Turkce aciklama.",
        skill_gap_summary="Eksik beceri yok.",
        recommendations=["Ileri konular."],
    )
    mock_client = _mock_gemini_explanation_generate(monkeypatch, mock_llm_output)

    # 1. First call triggers Gemini
    res1 = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=tr",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 200
    assert mock_client.models.generate_content.call_count == 1

    # 2. Second call uses Redis cache (Gemini not called again)
    res2 = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=tr",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 200
    assert res2.json()["why_you_match"] == "Turkce aciklama."
    assert mock_client.models.generate_content.call_count == 1


def test_get_match_explanation_tr_and_ar_cache_keys_are_independent(
    client: TestClient, monkeypatch
):
    """Verify Turkish and Arabic maintain isolated Redis cache keys."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Student")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Intern",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
            required_skills=["Python"],
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
            why_you_match="English text",
            skill_gap_analysis={"matching_skills": ["Python"], "missing_skills": []},
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    fake_redis = FakeMatchExplanationRedis()
    monkeypatch.setattr(
        "app.services.match_explanation._get_redis_client",
        lambda: fake_redis,
    )

    def dynamic_mock_gemini(
        profile, internship, overall_score, matching_skills, missing_skills, **kwargs
    ):
        loc = kwargs.get("content_locale", "en")
        if loc == "tr":
            return LLMMatchExplanation(
                why_you_match="Turkce metin",
                skill_gap_summary="Turkce ozet",
                recommendations=[],
            )
        elif loc == "ar":
            return LLMMatchExplanation(
                why_you_match="\u0646\u0635 \u0639\u0631\u0628\u064a",
                skill_gap_summary="\u0645\u0644\u062e\u0635 \u0639\u0631\u0628\u064a",
                recommendations=[],
            )
        return LLMMatchExplanation(
            why_you_match="English text",
            skill_gap_summary="English summary",
            recommendations=[],
        )

    gemini_mock = MagicMock(side_effect=dynamic_mock_gemini)

    monkeypatch.setattr(
        "app.services.match_explanation.generate_grounded_match_explanation",
        gemini_mock,
    )

    res_tr = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=tr",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_tr.status_code == 200
    assert res_tr.json()["why_you_match"] == "Turkce metin"

    res_ar = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=ar",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_ar.status_code == 200
    assert res_ar.json()["why_you_match"] == "\u0646\u0635 \u0639\u0631\u0628\u064a"
    assert gemini_mock.call_count == 2

    # Second Arabic request must hit Redis and must not call Gemini again.
    res_ar_cached = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=ar",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_ar_cached.status_code == 200
    assert res_ar_cached.json()["why_you_match"] == res_ar.json()["why_you_match"]
    assert gemini_mock.call_count == 2


    # Verify 2 distinct content cache keys exist in Redis store (1 for TR, 1 for AR)
    content_cache_keys = [
        k for k in fake_redis.store.keys()
        if ":lock:" not in k and (":tr:" in k or ":ar:" in k)
    ]
    assert len(content_cache_keys) == 2
    assert any(":tr:" in k for k in content_cache_keys)
    assert any(":ar:" in k for k in content_cache_keys)


def test_get_match_explanation_redis_unavailable_fallback_to_english_and_zero_gemini(
    client: TestClient, monkeypatch
):
    """
    CRITICAL COST SAFETY: When Redis fails, return canonical English DB fallback
    if available, and DO NOT make uncached Gemini calls.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Student")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Intern",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
            required_skills=["Python"],
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=85,
            skill_score=85,
            vector_score=85,
            attribute_score=85,
            why_you_match="Canonical English DB Fallback Narrative.",
            skill_gap_analysis={
                "matching_skills": ["Python"],
                "missing_skills": [],
                "summary": "Canonical English DB Summary.",
                "recommendations": ["Canonical English Rec."],
            },
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    fake_failing_redis = FakeMatchExplanationRedis(should_fail=True)
    monkeypatch.setattr(
        "app.services.match_explanation._get_redis_client",
        lambda: fake_failing_redis,
    )

    gemini_mock = MagicMock()
    monkeypatch.setattr(
        "app.services.match_explanation.generate_grounded_match_explanation",
        gemini_mock,
    )

    response = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=tr",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["why_you_match"] == "Canonical English DB Fallback Narrative."
    assert data["skill_gap_analysis"]["summary"] == "Canonical English DB Summary."
    gemini_mock.assert_not_called()


def test_get_match_explanation_active_failure_sentinel_prevents_gemini_retry(
    client: TestClient, monkeypatch
):
    """Verify active failure sentinel in Redis skips Gemini and returns English fallback."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Student")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Intern",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
            required_skills=["Python"],
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=85,
            skill_score=85,
            vector_score=85,
            attribute_score=85,
            why_you_match="English DB Narrative.",
            skill_gap_analysis={
                "matching_skills": ["Python"],
                "missing_skills": [],
                "summary": "English DB Summary.",
                "recommendations": [],
            },
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    fake_redis = FakeMatchExplanationRedis()
    from app.services.match_explanation import (
        CACHE_VERSION,
        compute_match_explanation_context_hash,
    )
    exact_hash = compute_match_explanation_context_hash(
        match_id=target_match_id,
        overall_score=85,
        matching_skills=["Python"],
        missing_skills=[],
        candidate_name="Student",
        internship_title="Intern",
        internship_company="Co",
        internship_location="Remote (remote)",
        internship_description="Dev.",
        internship_required_skills=["Python"],
        internship_preferred_skills=[],
    )
    sentinel_key = (
        f"internmatch:i18n:match-explanation:{CACHE_VERSION}:"
        f"failure:{target_match_id}:tr:{exact_hash}"
    )
    fake_redis.store[sentinel_key] = "1"

    monkeypatch.setattr(
        "app.services.match_explanation._get_redis_client",
        lambda: fake_redis,
    )

    gemini_mock = MagicMock()
    monkeypatch.setattr(
        "app.services.match_explanation.generate_grounded_match_explanation",
        gemini_mock,
    )

    response = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=tr",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["why_you_match"] == "English DB Narrative."
    gemini_mock.assert_not_called()


def test_get_match_explanation_stampede_lock_loser_does_not_call_gemini(
    client: TestClient, monkeypatch
):
    """Verify concurrent request that loses stampede lock does not call Gemini."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Student")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Intern",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
            required_skills=["Python"],
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=85,
            skill_score=85,
            vector_score=85,
            attribute_score=85,
            why_you_match="English DB Narrative.",
            skill_gap_analysis={
                "matching_skills": ["Python"],
                "missing_skills": [],
                "summary": "English DB Summary.",
                "recommendations": [],
            },
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    fake_redis = FakeMatchExplanationRedis()
    from app.services.match_explanation import (
        CACHE_VERSION,
        compute_match_explanation_context_hash,
    )
    exact_hash = compute_match_explanation_context_hash(
        match_id=target_match_id,
        overall_score=85,
        matching_skills=["Python"],
        missing_skills=[],
        candidate_name="Student",
        internship_title="Intern",
        internship_company="Co",
        internship_location="Remote (remote)",
        internship_description="Dev.",
        internship_required_skills=["Python"],
        internship_preferred_skills=[],
    )
    # Lock is held
    lock_key = (
        f"internmatch:i18n:match-explanation:{CACHE_VERSION}:"
        f"lock:{target_match_id}:tr:{exact_hash}"
    )
    fake_redis.store[lock_key] = "1"

    monkeypatch.setattr(
        "app.services.match_explanation._get_redis_client",
        lambda: fake_redis,
    )

    gemini_mock = MagicMock()
    monkeypatch.setattr(
        "app.services.match_explanation.generate_grounded_match_explanation",
        gemini_mock,
    )

    response = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=tr",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["why_you_match"] == "English DB Narrative."
    gemini_mock.assert_not_called()


def test_get_match_explanation_corrupted_redis_cache_is_discarded_and_repaired(
    client: TestClient, monkeypatch
):
    """Verify malformed JSON in Redis is safely deleted and recovered cleanly."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Student")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Intern",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
            required_skills=["Python"],
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=85,
            skill_score=85,
            vector_score=85,
            attribute_score=85,
            why_you_match="English DB Narrative.",
            skill_gap_analysis={
                "matching_skills": ["Python"],
                "missing_skills": [],
                "summary": "English DB Summary.",
                "recommendations": [],
            },
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    fake_redis = FakeMatchExplanationRedis()
    from app.services.match_explanation import (
        CACHE_VERSION,
        compute_match_explanation_context_hash,
    )
    exact_hash = compute_match_explanation_context_hash(
        match_id=target_match_id,
        overall_score=85,
        matching_skills=["Python"],
        missing_skills=[],
        candidate_name="Student",
        internship_title="Intern",
        internship_company="Co",
        internship_location="Remote (remote)",
        internship_description="Dev.",
        internship_required_skills=["Python"],
        internship_preferred_skills=[],
    )
    cache_key = (
        f"internmatch:i18n:match-explanation:{CACHE_VERSION}:"
        f"{target_match_id}:tr:{exact_hash}"
    )
    fake_redis.store[cache_key] = "MALFORMED_JSON_STRING {{"

    monkeypatch.setattr(
        "app.services.match_explanation._get_redis_client",
        lambda: fake_redis,
    )

    mock_llm_output = LLMMatchExplanation(
        why_you_match="Repaired Turkish narrative.",
        skill_gap_summary="Repaired summary.",
        recommendations=["Repaired Rec"],
    )
    _mock_gemini_explanation_generate(monkeypatch, mock_llm_output)

    response = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=tr",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["why_you_match"] == "Repaired Turkish narrative."


def test_match_explanation_context_hash_changes_when_authoritative_context_changes():
    from app.services.match_explanation import compute_match_explanation_context_hash

    match_id = uuid4()
    first_hash = compute_match_explanation_context_hash(
        match_id=match_id,
        overall_score=85,
        matching_skills=["Python"],
        missing_skills=["Redis"],
        internship_description="Build backend APIs.",
    )
    identical_hash = compute_match_explanation_context_hash(
        match_id=match_id,
        overall_score=85,
        matching_skills=["Python"],
        missing_skills=["Redis"],
        internship_description="Build backend APIs.",
    )
    changed_hash = compute_match_explanation_context_hash(
        match_id=match_id,
        overall_score=85,
        matching_skills=["Python"],
        missing_skills=["Redis"],
        internship_description="Build backend APIs and Redis systems.",
    )

    assert first_hash == identical_hash
    assert first_hash != changed_hash
def test_get_match_explanation_ar_provider_failure_without_english_cache_returns_grounded_fallback(
    client: TestClient, monkeypatch
):
    """Provider outage must not make Why Me unavailable when canonical match data exists."""
    from google.genai.errors import ServerError

    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Fallback Candidate",
        )
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Backend Intern",
            company="Fallback Co",
            location="Remote",
            work_type="remote",
            description="Backend work.",
            required_skills=["Python", "Redis"],
            preferred_skills=[],
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=82,
            skill_score=82,
            vector_score=82,
            attribute_score=82,
            why_you_match=None,
            skill_gap_analysis={
                "matching_skills": ["Python"],
                "missing_skills": ["Redis"],
                "summary": "",
                "recommendations": [],
            },
        )
        db.add(match)
        db.commit()
        target_match_id = match.id
    finally:
        db.close()

    fake_redis = FakeMatchExplanationRedis()

    monkeypatch.setattr(
        "app.services.match_explanation._get_redis_client",
        lambda: fake_redis,
    )

    gemini_mock = MagicMock(
        side_effect=ServerError(
            503,
            {
                "error": {
                    "code": 503,
                    "message": "High demand",
                    "status": "UNAVAILABLE",
                }
            },
            None,
        )
    )

    monkeypatch.setattr(
        "app.services.match_explanation.generate_grounded_match_explanation",
        gemini_mock,
    )

    response = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=ar",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["overall_score"] == 82
    assert data["matching_skills"] == ["Python"]
    assert data["missing_skills"] == ["Redis"]
    assert "82" in data["why_you_match"]
    assert "Python" in data["why_you_match"]
    assert "Redis" in data["skill_gap_analysis"]["summary"]
    assert gemini_mock.call_count == 1


def test_get_match_explanation_active_sentinel_without_english_cache_returns_grounded_fallback(
    client: TestClient, monkeypatch
):
    """Active provider sentinel must return canonical-data fallback without another Gemini call."""
    from app.services.match_explanation import (
        CACHE_VERSION,
        compute_match_explanation_context_hash,
    )

    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Sentinel Candidate",
        )
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Backend Intern",
            company="Sentinel Co",
            location="Remote",
            work_type="remote",
            description="Backend work.",
            required_skills=["Python", "Redis"],
            preferred_skills=[],
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=82,
            skill_score=82,
            vector_score=82,
            attribute_score=82,
            why_you_match=None,
            skill_gap_analysis={
                "matching_skills": ["Python"],
                "missing_skills": ["Redis"],
                "summary": "",
                "recommendations": [],
            },
        )
        db.add(match)
        db.commit()

        target_match_id = match.id
        profile_id = profile.id
    finally:
        db.close()

    db = TestingSessionLocal()
    try:
        profile = db.query(StudentProfile).filter(StudentProfile.id == profile_id).one()

        candidate_skills = []

        exact_hash = compute_match_explanation_context_hash(
            match_id=target_match_id,
            overall_score=82,
            matching_skills=["Python"],
            missing_skills=["Redis"],
            candidate_skills=candidate_skills,
            education_entries=[],
            experience_entries=[],
            project_entries=[],
            candidate_name="Sentinel Candidate",
            candidate_headline=None,
            internship_title="Backend Intern",
            internship_company="Sentinel Co",
            internship_location="Remote (remote)",
            internship_description="Backend work.",
            internship_required_skills=["Python", "Redis"],
            internship_preferred_skills=[],
        )
    finally:
        db.close()

    fake_redis = FakeMatchExplanationRedis()

    sentinel_key = (
        f"internmatch:i18n:match-explanation:{CACHE_VERSION}:failure:"
        f"{target_match_id}:ar:{exact_hash}"
    )

    fake_redis.store[sentinel_key] = "1"

    monkeypatch.setattr(
        "app.services.match_explanation._get_redis_client",
        lambda: fake_redis,
    )

    gemini_mock = MagicMock()

    monkeypatch.setattr(
        "app.services.match_explanation.generate_grounded_match_explanation",
        gemini_mock,
    )

    response = _direct_match_explanation_service_request(
        f"/api/v1/matches/{target_match_id}/explanation?content_locale=ar",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["overall_score"] == 82
    assert data["matching_skills"] == ["Python"]
    assert data["missing_skills"] == ["Redis"]
    assert "82" in data["why_you_match"]
    assert "Python" in data["why_you_match"]
    assert "Redis" in data["skill_gap_analysis"]["summary"]
    gemini_mock.assert_not_called()
