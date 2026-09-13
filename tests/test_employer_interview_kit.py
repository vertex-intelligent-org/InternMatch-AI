"""Employer Interview Kit API/service contract tests."""

import json
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import settings
from app.services.employer_interview_kit import (
    EmployerInterviewKitResponse,
    EmployerInterviewQuestion,
    generate_employer_interview_kit,
)
from fastapi.testclient import TestClient

from tests.test_employer_candidate_insight import (
    _create_listing,
    _create_submitted_application_with_match,
)
from tests.test_employer_internships import _create_profile


def test_employer_interview_kit_endpoint_uses_owned_canonical_match(
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
            "_require_employer_feature"
        ),
        lambda *args, **kwargs: None,
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

        return EmployerInterviewKitResponse(
            application_id=application.id,
            internship_id=internship_id,
            match_score=88,
            interview_focus_summary=(
                "Validate backend API experience and Redis exposure."
            ),
            questions=[
                EmployerInterviewQuestion(
                    category="technical",
                    question=(
                        "How have you structured a FastAPI service "
                        "for maintainability?"
                    ),
                    rationale=(
                        "Clarifies practical experience with a "
                        "required framework."
                    ),
                    evidence_basis=(
                        "FastAPI is a canonical matching skill."
                    ),
                ),
                EmployerInterviewQuestion(
                    category="project",
                    question=(
                        "Walk us through a backend project where "
                        "you designed REST APIs."
                    ),
                    rationale=(
                        "Explores supplied project evidence."
                    ),
                    evidence_basis=(
                        "Candidate professional project evidence."
                    ),
                ),
                EmployerInterviewQuestion(
                    category="gap_validation",
                    question=(
                        "Have you worked with Redis or another "
                        "caching system?"
                    ),
                    rationale=(
                        "Clarifies exposure not established "
                        "by current evidence."
                    ),
                    evidence_basis=(
                        "Redis is a canonical missing skill."
                    ),
                ),
                EmployerInterviewQuestion(
                    category="role_context",
                    question=(
                        "How would you approach debugging a slow "
                        "backend endpoint?"
                    ),
                    rationale=(
                        "Explores job-relevant backend reasoning."
                    ),
                    evidence_basis=(
                        "Role requires backend service work."
                    ),
                ),
            ],
            matching_skills=[
                "Python",
                "FastAPI",
                "PostgreSQL",
            ],
            missing_skills=["Redis"],
            human_decision_required=True,
        )

    monkeypatch.setattr(
        (
            "app.api.v1.endpoints.internships."
            "generate_employer_interview_kit"
        ),
        fake_generate,
    )

    response = client.post(
        (
            f"/api/v1/internships/{internship_id}"
            f"/applicants/{application_id}/interview-kit"
            "?content_locale=en"
        ),
        headers={
            "Authorization": f"Bearer valid-user-{employer_id}",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["match_score"] == 88
    assert len(body["questions"]) == 4
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


def test_employer_interview_kit_requires_calculated_match(
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
            f"/applicants/{application_id}/interview-kit"
        ),
        headers={
            "Authorization": f"Bearer valid-user-{employer_id}",
        },
    )

    assert response.status_code == 409
    assert "calculated match" in response.json()["detail"].lower()


def test_employer_interview_kit_preserves_tenant_isolation(
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
            f"/applicants/{application_id}/interview-kit"
        ),
        headers={
            "Authorization": (
                f"Bearer valid-user-{other_employer_id}"
            ),
        },
    )

    assert response.status_code == 404


def test_employer_interview_kit_service_is_grounded_and_identity_free(
    monkeypatch,
):
    employer_id = uuid4()
    application_id = uuid4()
    internship_id = uuid4()
    profile_id = uuid4()

    profile = SimpleNamespace(
        id=profile_id,
        full_name="IDENTITY MUST NOT ENTER KIT",
        headline="Backend Engineering Student",
        preferences={"department": "Computer Engineering"},
    )

    application = SimpleNamespace(
        id=application_id,
        internship_id=internship_id,
    )

    match = SimpleNamespace(
        overall_score=88,
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

    from unittest.mock import MagicMock

    db = MagicMock()
    db.get.return_value = internship

    monkeypatch.setattr(
        (
            "app.services.employer_interview_kit."
            "MatchingDataRepository.get_ai_grounding_context"
        ),
        lambda db, student_id: {
            "skills": ["Python", "FastAPI"],
            "education_entries": [
                "BSc Computer Engineering at Example University",
            ],
            "experience_entries": [
                "Backend Intern: Built REST APIs",
            ],
            "project_entries": [
                "API Platform (Python, FastAPI): Backend services",
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
                        "interview_focus_summary": (
                            "Validate supplied backend evidence "
                            "and Redis exposure."
                        ),
                        "questions": [
                            {
                                "category": "technical",
                                "question": (
                                    "How have you structured "
                                    "FastAPI services?"
                                ),
                                "rationale": (
                                    "Clarifies required-framework "
                                    "experience."
                                ),
                                "evidence_basis": (
                                    "FastAPI is a matching skill."
                                ),
                            },
                            {
                                "category": "experience",
                                "question": (
                                    "Describe an API you built "
                                    "during your backend internship."
                                ),
                                "rationale": (
                                    "Explores supplied experience."
                                ),
                                "evidence_basis": (
                                    "Backend internship evidence."
                                ),
                            },
                            {
                                "category": "project",
                                "question": (
                                    "What design decisions did you "
                                    "make in your API project?"
                                ),
                                "rationale": (
                                    "Explores supplied project work."
                                ),
                                "evidence_basis": (
                                    "API Platform project evidence."
                                ),
                            },
                            {
                                "category": "gap_validation",
                                "question": (
                                    "Have you used Redis or another "
                                    "caching technology?"
                                ),
                                "rationale": (
                                    "Clarifies currently "
                                    "unestablished exposure."
                                ),
                                "evidence_basis": (
                                    "Redis is a canonical "
                                    "missing skill."
                                ),
                            },
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
            "app.services.employer_interview_kit."
            "create_tracked_gemini_client"
        ),
        lambda *args, **kwargs: fake_client,
    )

    result = generate_employer_interview_kit(
        db,
        employer_user_id=employer_id,
        application=application,
        profile=profile,
        match=match,
        internship_id=internship_id,
        content_locale="en",
    )

    assert result.match_score == 88
    assert len(result.questions) == 4
    assert result.matching_skills == ["Python", "FastAPI"]
    assert result.missing_skills == ["Redis"]
    assert result.human_decision_required is True

    prompt_context = captured["contents"]

    assert "IDENTITY MUST NOT ENTER KIT" not in prompt_context
    assert str(profile_id) not in prompt_context
    assert str(employer_id) not in prompt_context
    assert '"matching_skills": ["Python", "FastAPI"]' in prompt_context
    assert '"missing_skills": ["Redis"]' in prompt_context
