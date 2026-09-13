"""Employer Candidate Insight API/service tests."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from app.core.config import settings
from app.db.models import Application, Match
from app.services.employer_candidate_insight import (
    EmployerCandidateInsightResponse,
    generate_employer_candidate_insight,
)
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal
from tests.test_employer_internships import _create_profile


def _create_listing(
    client: TestClient,
    monkeypatch,
    *,
    employer_id,
) -> UUID:
    monkeypatch.setattr(
        "app.api.v1.endpoints.internships.generate_embedding",
        lambda text: [0.1] * settings.EMBEDDING_DIMENSION,
    )

    response = client.post(
        "/api/v1/internships",
        json={
            "title": "Backend Engineering Intern",
            "company": "Ignored Client Company",
            "location": "Remote",
            "work_type": "remote",
            "description": (
                "Build Python APIs and backend services using FastAPI "
                "and PostgreSQL."
            ),
            "required_skills": ["Python", "FastAPI", "PostgreSQL"],
            "preferred_skills": ["Redis", "Docker"],
            "languages": ["English"],
            "min_education": "Computer Science student",
        },
        headers={
            "Authorization": f"Bearer valid-user-{employer_id}",
        },
    )

    assert response.status_code == 201
    return UUID(response.json()["id"])


def _create_submitted_application_with_match(
    *,
    candidate_profile,
    internship_id: UUID,
    include_match: bool = True,
):
    application_id = uuid4()

    db = TestingSessionLocal()

    try:
        application = Application(
            id=application_id,
            student_id=candidate_profile.id,
            internship_id=internship_id,
            status="applied",
            applied_date=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        db.add(application)

        if include_match:
            db.add(
                Match(
                    id=uuid4(),
                    student_id=candidate_profile.id,
                    internship_id=internship_id,
                    overall_score=88,
                    skill_score=90,
                    vector_score=84,
                    attribute_score=80,
                    skill_gap_analysis={
                        "matching_skills": [
                            "Python",
                            "FastAPI",
                            "PostgreSQL",
                        ],
                        "missing_skills": [
                            "Redis",
                        ],
                        "summary": "",
                        "recommendations": [],
                    },
                    created_at=datetime.now(timezone.utc),
                )
            )

        db.commit()
        return application_id

    finally:
        db.close()


def test_employer_candidate_insight_endpoint_uses_owned_canonical_match(
    client: TestClient,
    monkeypatch,
    mock_supabase_auth,
):
    employer_id = uuid4()
    candidate_user_id = uuid4()

    _create_profile(
        employer_id,
        "Employer Recruiter",
        account_type="employer",
    )

    candidate_profile = _create_profile(
        candidate_user_id,
        "Candidate Name",
        account_type="intern",
        preferences={"department": "Computer Engineering"},
    )

    internship_id = _create_listing(
        client,
        monkeypatch,
        employer_id=employer_id,
    )

    application_id = _create_submitted_application_with_match(
        candidate_profile=candidate_profile,
        internship_id=internship_id,
    )

    monkeypatch.setattr(
        (
            "app.api.v1.endpoints.internships."
            "_execute_employer_ai_with_quota_response"
        ),
        lambda *args, callback, **kwargs: callback(),
    )

    captured = {}

    def fake_generate(
        db,
        *,
        employer_user_id,
        application,
        profile,
        match,
        internship_id,
        content_locale,
    ):
        captured["employer_user_id"] = employer_user_id
        captured["application_id"] = application.id
        captured["profile_id"] = profile.id
        captured["match_score"] = match.overall_score
        captured["internship_id"] = internship_id
        captured["locale"] = content_locale

        return EmployerCandidateInsightResponse(
            application_id=application.id,
            internship_id=internship_id,
            match_score=match.overall_score,
            executive_summary=(
                "The candidate has strong backend alignment with the role."
            ),
            strengths=[
                "Python and FastAPI align with required skills.",
                "PostgreSQL aligns with the backend stack.",
            ],
            gaps_to_validate=[
                "Redis experience is not established by the current evidence.",
            ],
            interview_focus=[
                "Ask about caching and background-job experience.",
            ],
            matching_skills=["Python", "FastAPI", "PostgreSQL"],
            missing_skills=["Redis"],
            human_decision_required=True,
        )

    monkeypatch.setattr(
        "app.api.v1.endpoints.internships.generate_employer_candidate_insight",
        fake_generate,
    )

    response = client.post(
        (
            f"/api/v1/internships/{internship_id}"
            f"/applicants/{application_id}/insight"
            "?content_locale=en"
        ),
        headers={
            "Authorization": f"Bearer valid-user-{employer_id}",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["match_score"] == 88
    assert body["matching_skills"] == [
        "Python",
        "FastAPI",
        "PostgreSQL",
    ]
    assert body["missing_skills"] == ["Redis"]
    assert body["human_decision_required"] is True

    assert captured == {
        "employer_user_id": employer_id,
        "application_id": application_id,
        "profile_id": candidate_profile.id,
        "match_score": 88,
        "internship_id": internship_id,
        "locale": "en",
    }


def test_employer_candidate_insight_requires_existing_canonical_match(
    client: TestClient,
    monkeypatch,
    mock_supabase_auth,
):
    employer_id = uuid4()
    candidate_user_id = uuid4()

    _create_profile(
        employer_id,
        "Employer Recruiter",
        account_type="employer",
    )

    candidate_profile = _create_profile(
        candidate_user_id,
        "Candidate Name",
        account_type="intern",
    )

    internship_id = _create_listing(
        client,
        monkeypatch,
        employer_id=employer_id,
    )

    application_id = _create_submitted_application_with_match(
        candidate_profile=candidate_profile,
        internship_id=internship_id,
        include_match=False,
    )

    response = client.post(
        (
            f"/api/v1/internships/{internship_id}"
            f"/applicants/{application_id}/insight"
        ),
        headers={
            "Authorization": f"Bearer valid-user-{employer_id}",
        },
    )

    assert response.status_code == 409
    assert "calculated match" in response.json()["detail"].lower()


def test_employer_candidate_insight_preserves_tenant_isolation(
    client: TestClient,
    monkeypatch,
    mock_supabase_auth,
):
    owner_id = uuid4()
    other_employer_id = uuid4()
    candidate_user_id = uuid4()

    _create_profile(
        owner_id,
        "Owner Employer",
        account_type="employer",
    )

    _create_profile(
        other_employer_id,
        "Other Employer",
        account_type="employer",
    )

    candidate_profile = _create_profile(
        candidate_user_id,
        "Candidate Name",
        account_type="intern",
    )

    internship_id = _create_listing(
        client,
        monkeypatch,
        employer_id=owner_id,
    )

    application_id = _create_submitted_application_with_match(
        candidate_profile=candidate_profile,
        internship_id=internship_id,
    )

    response = client.post(
        (
            f"/api/v1/internships/{internship_id}"
            f"/applicants/{application_id}/insight"
        ),
        headers={
            "Authorization": (
                f"Bearer valid-user-{other_employer_id}"
            ),
        },
    )

    assert response.status_code == 404


def test_candidate_insight_service_excludes_identity_and_uses_canonical_evidence(
    monkeypatch,
):
    employer_id = uuid4()
    application_id = uuid4()
    internship_id = uuid4()
    profile_id = uuid4()

    profile = SimpleNamespace(
        id=profile_id,
        full_name="IDENTITY MUST NOT ENTER PROMPT",
        headline="Backend Engineering Student",
        preferences={"department": "Computer Engineering"},
    )

    application = SimpleNamespace(
        id=application_id,
        internship_id=internship_id,
    )

    match = SimpleNamespace(
        overall_score=88,
        skill_score=90,
        vector_score=84,
        attribute_score=80,
        skill_gap_analysis={
            "matching_skills": ["Python", "FastAPI"],
            "missing_skills": ["Redis"],
        },
    )

    internship = SimpleNamespace(
        id=internship_id,
        title="Backend Engineering Intern",
        company="Acme Corp",
        location="Remote",
        work_type="remote",
        description="Build APIs and backend services.",
        required_skills=["Python", "FastAPI"],
        preferred_skills=["Redis"],
        languages=["English"],
        min_education="Computer Science student",
    )

    db = MagicMock()
    db.get.return_value = internship

    monkeypatch.setattr(
        (
            "app.services.employer_candidate_insight."
            "MatchingDataRepository.get_ai_grounding_context"
        ),
        lambda db, student_id: {
            "skills": ["Python", "FastAPI"],
            "education_entries": [
                "BSc Computer Engineering at Example University",
            ],
            "experience_entries": [
                "Backend Intern at Example Company: Built REST APIs",
            ],
            "project_entries": [
                "API Platform (Python, FastAPI): Built backend services",
            ],
        },
    )

    captured = {}

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["model"] = model
            captured["contents"] = contents
            captured["config"] = config

            return SimpleNamespace(
                text=json.dumps(
                    {
                        "executive_summary": (
                            "The supplied professional evidence aligns "
                            "well with the backend role."
                        ),
                        "strengths": [
                            "Python and FastAPI are directly evidenced.",
                        ],
                        "gaps_to_validate": [
                            "Redis is a stated missing skill.",
                        ],
                        "interview_focus": [
                            "Explore caching experience and Redis exposure.",
                        ],
                    }
                )
            )

    fake_client = SimpleNamespace(models=FakeModels())

    monkeypatch.setattr(
        settings,
        "GEMINI_API_KEY",
        "test-key",
    )

    monkeypatch.setattr(
        (
            "app.services.employer_candidate_insight."
            "create_tracked_gemini_client"
        ),
        lambda *args, **kwargs: fake_client,
    )

    result = generate_employer_candidate_insight(
        db,
        employer_user_id=employer_id,
        application=application,
        profile=profile,
        match=match,
        internship_id=internship_id,
        content_locale="en",
    )

    assert result.match_score == 88
    assert result.matching_skills == ["Python", "FastAPI"]
    assert result.missing_skills == ["Redis"]
    assert result.human_decision_required is True

    prompt_context = captured["contents"]

    assert "IDENTITY MUST NOT ENTER PROMPT" not in prompt_context
    assert str(employer_id) not in prompt_context
    assert str(profile_id) not in prompt_context
    assert '"matching_skills": ["Python", "FastAPI"]' in prompt_context
    assert '"missing_skills": ["Redis"]' in prompt_context
