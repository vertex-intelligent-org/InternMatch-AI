"""Employer internship-description assistant tests."""

import json
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import settings
from app.services.employer_internship_description import (
    EmployerInternshipDescriptionRequest,
    EmployerInternshipDescriptionResponse,
    generate_employer_internship_description,
)
from fastapi.testclient import TestClient

from tests.test_employer_internships import _create_profile


def _payload():
    return {
        "title": "Backend Engineering Intern",
        "raw_description": (
            "Help build Python backend APIs using FastAPI "
            "and PostgreSQL for our application."
        ),
        "location": "Remote",
        "work_type": "remote",
        "required_skills": [
            "Python",
            "FastAPI",
            "PostgreSQL",
        ],
        "preferred_skills": [
            "Redis",
            "Docker",
        ],
        "languages": [
            "English",
        ],
        "min_education": (
            "Computer Science student"
        ),
    }


def test_description_endpoint_returns_draft_only(
    client: TestClient,
    monkeypatch,
    mock_supabase_auth,
):
    employer_id = uuid4()

    _create_profile(
        employer_id,
        "Employer Recruiter",
        account_type="employer",
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
        *,
        employer_user_id,
        payload,
        content_locale,
    ):
        captured["employer_user_id"] = (
            employer_user_id
        )
        captured["payload"] = payload
        captured["locale"] = content_locale

        return (
            EmployerInternshipDescriptionResponse(
                suggested_description=(
                    "Join the backend team and "
                    "help build Python APIs."
                ),
                responsibilities=[
                    "Build backend APIs.",
                    "Work with PostgreSQL.",
                ],
                requirements_summary=[
                    "Python",
                    "FastAPI",
                    "PostgreSQL",
                    "English",
                    "Computer Science student",
                ],
                preferred_qualifications=[
                    "Redis",
                    "Docker",
                ],
                draft_only=True,
                requires_employer_review=True,
                auto_published=False,
            )
        )

    monkeypatch.setattr(
        (
            "app.api.v1.endpoints.internships."
            "generate_employer_internship_description"
        ),
        fake_generate,
    )

    response = client.post(
        (
            "/api/v1/internships/"
            "employer-tools/"
            "description-assistant"
            "?content_locale=en"
        ),
        json=_payload(),
        headers={
            "Authorization": (
                f"Bearer valid-user-{employer_id}"
            ),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["draft_only"] is True
    assert (
        body["requires_employer_review"]
        is True
    )
    assert body["auto_published"] is False

    assert (
        captured["employer_user_id"]
        == employer_id
    )

    assert (
        captured["payload"].required_skills
        == [
            "Python",
            "FastAPI",
            "PostgreSQL",
        ]
    )


def test_description_endpoint_requires_authentication(
    client: TestClient,
):
    response = client.post(
        (
            "/api/v1/internships/"
            "employer-tools/"
            "description-assistant"
        ),
        json=_payload(),
    )

    assert response.status_code == 401


def test_description_endpoint_validates_input(
    client: TestClient,
    mock_supabase_auth,
):
    employer_id = uuid4()

    _create_profile(
        employer_id,
        "Employer Recruiter",
        account_type="employer",
    )

    invalid = _payload()
    invalid["raw_description"] = "short"

    response = client.post(
        (
            "/api/v1/internships/"
            "employer-tools/"
            "description-assistant"
        ),
        json=invalid,
        headers={
            "Authorization": (
                f"Bearer valid-user-{employer_id}"
            ),
        },
    )

    assert response.status_code == 422


def test_description_service_is_grounded_and_draft_only(
    monkeypatch,
):
    employer_id = uuid4()

    payload = (
        EmployerInternshipDescriptionRequest(
            **_payload()
        )
    )

    captured = {}

    class FakeModels:
        def generate_content(
            self,
            *,
            model,
            contents,
            config,
        ):
            captured["contents"] = contents
            captured["config"] = config

            return SimpleNamespace(
                text=json.dumps(
                    {
                        "suggested_description": (
                            "Help build Python "
                            "backend APIs with "
                            "FastAPI and PostgreSQL."
                        ),
                        "responsibilities": [
                            "Build backend APIs.",
                            "Work with PostgreSQL.",
                        ],
                        "requirements_summary": [
                            "Python",
                            "FastAPI",
                            "PostgreSQL",
                            "English",
                            "Computer Science student",
                        ],
                        "preferred_qualifications": [
                            "Redis",
                            "Docker",
                        ],
                    }
                )
            )

    fake_client = SimpleNamespace(
        models=FakeModels()
    )

    monkeypatch.setattr(
        settings,
        "GEMINI_API_KEY",
        "test-key",
    )

    monkeypatch.setattr(
        (
            "app.services."
            "employer_internship_description."
            "create_tracked_gemini_client"
        ),
        lambda *args, **kwargs: (
            fake_client
        ),
    )

    result = (
        generate_employer_internship_description(
            employer_user_id=employer_id,
            payload=payload,
            content_locale="en",
        )
    )

    assert result.draft_only is True
    assert (
        result.requires_employer_review
        is True
    )
    assert result.auto_published is False

    prompt_context = captured[
        "contents"
    ]

    assert (
        str(employer_id)
        not in prompt_context
    )

    assert (
        '"required_skills": '
        '["Python", "FastAPI", "PostgreSQL"]'
        in prompt_context
    )

    assert (
        '"preferred_skills": '
        '["Redis", "Docker"]'
        in prompt_context
    )
