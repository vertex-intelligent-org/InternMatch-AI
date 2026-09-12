"""
EMP-MVP4C ? AI Interview Prep regression coverage.

Validates:
- candidate ownership isolation
- interviewing status requirement
- scheduled interview requirement
- structured Gemini result contract
- Redis cache reuse without duplicate Gemini generation
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.core.config import settings
from app.db.models import Application, InternshipListing, Match, StudentProfile
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal

pytestmark = pytest.mark.usefixtures("mock_supabase_auth")


@pytest.fixture(autouse=True)
def clean_database():
    db = TestingSessionLocal()

    try:
        db.query(Match).delete()
        db.query(Application).delete()
        db.query(InternshipListing).delete()
        db.query(StudentProfile).delete()
        db.commit()
    finally:
        db.close()

    yield

    db = TestingSessionLocal()

    try:
        db.query(Match).delete()
        db.query(Application).delete()
        db.query(InternshipListing).delete()
        db.query(StudentProfile).delete()
        db.commit()
    finally:
        db.close()


def _create_interviewing_application(
    *,
    user_id,
    status="interviewing",
    scheduled=True,
):
    db = TestingSessionLocal()

    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Interview Candidate",
            headline="Backend Engineering Student",
            preferences={
                "account_type": "intern",
            },
        )

        db.add(profile)
        db.flush()

        internship = InternshipListing(
            id=uuid4(),
            title="Backend Engineer Intern",
            company="Example Labs",
            location="Istanbul",
            work_type="hybrid",
            description=(
                "Build secure APIs using Python, FastAPI, "
                "PostgreSQL, and Docker."
            ),
            required_skills=[
                "Python",
                "FastAPI",
                "PostgreSQL",
            ],
            preferred_skills=[
                "Docker",
            ],
            publication_status="published",
            is_active=True,
        )

        db.add(internship)
        db.flush()

        application = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=internship.id,
            status=status,
            interview_scheduled_at=(
                datetime.now(timezone.utc)
                + timedelta(days=2)
                if scheduled
                else None
            ),
            interview_mode="online" if scheduled else None,
            interview_location=(
                "https://meet.example.com/interview"
                if scheduled
                else None
            ),
            interview_message=(
                "Please be ready to discuss backend projects."
                if scheduled
                else None
            ),
        )

        db.add(application)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=internship.id,
            overall_score=88,
            skill_score=90,
            vector_score=85,
            attribute_score=87,
            skill_gap_analysis={
                "matching_skills": [
                    "Python",
                    "FastAPI",
                ],
                "missing_skills": [
                    "PostgreSQL",
                ],
                "summary": "",
                "recommendations": [],
            },
        )

        db.add(match)
        db.commit()

        return application.id

    finally:
        db.close()



class _DirectInterviewPrepResponse:
    """Small adapter for service-level regression assertions."""

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


def _direct_interview_prep_service_request(
    url,
    headers=None,
    **_kwargs,
):
    """
    Exercise interview-prep provider/cache logic directly.

    Ownership/status/scheduled-interview validation remains covered
    by the real asynchronous HTTP endpoint tests above.
    """
    from urllib.parse import (
        parse_qs,
        urlparse,
    )
    from uuid import UUID

    from app.repositories.application import (
        ApplicationRepository,
    )
    from app.services.interview_prep import (
        get_or_create_interview_prep,
    )

    parsed = urlparse(str(url))
    parts = [
        part
        for part in parsed.path.split("/")
        if part
    ]

    if (
        len(parts) < 3
        or parts[-1] != "interview-prep"
    ):
        raise AssertionError(
            f"Unexpected interview-prep URL: {url}"
        )

    application_id = UUID(
        parts[-2]
    )

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
        return _DirectInterviewPrepResponse(
            401,
            {"detail": "Not authenticated"},
        )

    user_id = UUID(
        authorization[len(prefix):]
    )

    db = TestingSessionLocal()

    try:
        record = (
            ApplicationRepository
            .get_with_internship_for_user(
                db=db,
                application_id=application_id,
                user_id=user_id,
            )
        )

        if not record:
            return _DirectInterviewPrepResponse(
                404,
                {"detail": "Application not found."},
            )

        application, internship = record

        try:
            result = (
                get_or_create_interview_prep(
                    db=db,
                    application=application,
                    internship=internship,
                    user_id=user_id,
                    content_locale=locale,
                )
            )
        except ValueError:
            return _DirectInterviewPrepResponse(
                503,
                {
                    "detail":
                    "AI interview preparation is "
                    "temporarily unavailable."
                },
            )

        return _DirectInterviewPrepResponse(
            200,
            result.model_dump(
                mode="json"
            ),
        )
    finally:
        db.close()


def test_interview_prep_requires_candidate_ownership(
    client: TestClient,
):
    owner_user_id = uuid4()
    other_user_id = uuid4()

    application_id = _create_interviewing_application(
        user_id=owner_user_id,
    )

    response = client.post(
        f"/api/v1/applications/{application_id}/interview-prep",
        headers={
            "Authorization": f"Bearer valid-user-{other_user_id}"
        },
    )

    assert response.status_code == 404


def test_interview_prep_requires_interviewing_status(
    client: TestClient,
):
    user_id = uuid4()

    application_id = _create_interviewing_application(
        user_id=user_id,
        status="applied",
        scheduled=True,
    )

    response = client.post(
        f"/api/v1/applications/{application_id}/interview-prep",
        headers={
            "Authorization": f"Bearer valid-user-{user_id}"
        },
    )

    assert response.status_code == 409


def test_interview_prep_requires_scheduled_interview(
    client: TestClient,
):
    user_id = uuid4()

    application_id = _create_interviewing_application(
        user_id=user_id,
        status="interviewing",
        scheduled=False,
    )

    response = client.post(
        f"/api/v1/applications/{application_id}/interview-prep",
        headers={
            "Authorization": f"Bearer valid-user-{user_id}"
        },
    )

    assert response.status_code == 409


def test_interview_prep_returns_structured_gemini_response(
    client: TestClient,
    monkeypatch,
):
    user_id = uuid4()

    application_id = _create_interviewing_application(
        user_id=user_id,
    )

    from app.services import interview_prep as service

    class FakeResponse:
        text = """
        {
          "preparation_summary":
            "Focus on concrete backend examples and explain your API design choices.",
          "likely_questions": [
            "Describe a FastAPI project you built.",
            "How would you secure an API endpoint?",
            "How do you approach database schema design?"
          ],
          "focus_areas": [
            "PostgreSQL",
            "API security"
          ],
          "strengths_to_highlight": [
            "Python",
            "FastAPI"
          ],
          "questions_to_ask": [
            "What would success look like during this internship?",
            "How does the engineering team review code?"
          ]
        }
        """

    calls = []

    class FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return FakeResponse()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.models = FakeModels()

    class FakeRedis:
        def get(self, key):
            return None

        def set(self, key, value, ex=None):
            return True

    monkeypatch.setattr(
        service.genai,
        "Client",
        FakeClient,
    )

    monkeypatch.setattr(
        service,
        "_get_redis_client",
        lambda: FakeRedis(),
    )

    monkeypatch.setattr(
        settings,
        "GEMINI_API_KEY",
        "test-gemini-key",
    )

    response = _direct_interview_prep_service_request(
        f"/api/v1/applications/{application_id}/interview-prep"
        "?content_locale=en",
        headers={
            "Authorization": f"Bearer valid-user-{user_id}"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["application_id"] == str(application_id)
    assert data["interview_scheduled_at"] is not None

    assert data["preparation_summary"] == (
        "Focus on concrete backend examples and explain "
        "your API design choices."
    )

    assert len(data["likely_questions"]) == 3

    assert data["focus_areas"] == [
        "PostgreSQL",
        "API security",
    ]

    assert data["strengths_to_highlight"] == [
        "Python",
        "FastAPI",
    ]

    assert len(data["questions_to_ask"]) == 2

    assert len(calls) == 1

    assert calls[0]["model"] == settings.LLM_MODEL_NAME


def test_interview_prep_uses_cache_without_second_gemini_call(
    client: TestClient,
    monkeypatch,
):
    user_id = uuid4()

    application_id = _create_interviewing_application(
        user_id=user_id,
    )

    from app.services import interview_prep as service

    store = {}
    gemini_calls = []

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, ex=None):
            store[key] = value
            return True

    class FakeResponse:
        text = """
        {
          "preparation_summary":
            "Prepare concrete examples from your backend work.",
          "likely_questions": [
            "How do you design REST APIs?",
            "How do you debug backend failures?",
            "How do you validate incoming data?"
          ],
          "focus_areas": [
            "PostgreSQL"
          ],
          "strengths_to_highlight": [
            "Python"
          ],
          "questions_to_ask": [
            "What technologies does the team use?",
            "How is intern mentorship structured?"
          ]
        }
        """

    class FakeModels:
        def generate_content(self, **kwargs):
            gemini_calls.append(kwargs)
            return FakeResponse()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(
        service,
        "_get_redis_client",
        lambda: FakeRedis(),
    )

    monkeypatch.setattr(
        service.genai,
        "Client",
        FakeClient,
    )

    monkeypatch.setattr(
        settings,
        "GEMINI_API_KEY",
        "test-gemini-key",
    )

    url = (
        f"/api/v1/applications/{application_id}/interview-prep"
        "?content_locale=en"
    )

    headers = {
        "Authorization": f"Bearer valid-user-{user_id}"
    }

    first = _direct_interview_prep_service_request(
        url,
        headers=headers,
    )

    second = _direct_interview_prep_service_request(
        url,
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200

    assert first.json() == second.json()

    assert len(gemini_calls) == 1
