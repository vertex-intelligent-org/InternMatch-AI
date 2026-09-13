"""Employer Shortlist Comparison contract tests."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.core.config import settings
from app.services.employer_shortlist_comparison import (
    EmployerShortlistCandidate,
    EmployerShortlistComparisonResponse,
    generate_employer_shortlist_comparison,
)
from fastapi.testclient import TestClient

from tests.test_employer_candidate_insight import (
    _create_listing,
    _create_submitted_application_with_match,
)
from tests.test_employer_internships import (
    _create_profile,
)


def test_shortlist_endpoint_is_neutral_and_owned(
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

    candidate_a = _create_profile(
        uuid4(),
        "Candidate A",
        account_type="intern",
    )

    candidate_b = _create_profile(
        uuid4(),
        "Candidate B",
        account_type="intern",
    )

    internship_id = _create_listing(
        client,
        monkeypatch,
        employer_id=employer_id,
    )

    application_a = (
        _create_submitted_application_with_match(
            candidate_profile=candidate_a,
            internship_id=internship_id,
        )
    )

    application_b = (
        _create_submitted_application_with_match(
            candidate_profile=candidate_b,
            internship_id=internship_id,
        )
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

    def fake_compare(
        db,
        *,
        employer_user_id,
        internship_id,
        records,
        content_locale,
    ):
        captured["employer_user_id"] = (
            employer_user_id
        )
        captured["internship_id"] = (
            internship_id
        )
        captured["application_ids"] = [
            item[0].id
            for item in records
        ]
        captured["locale"] = (
            content_locale
        )

        return (
            EmployerShortlistComparisonResponse(
                internship_id=(
                    internship_id
                ),
                comparison_summary=(
                    "Both candidates provide "
                    "role-relevant evidence."
                ),
                shared_role_requirements=[
                    "Python",
                ],
                candidates=[
                    EmployerShortlistCandidate(
                        application_id=(
                            application_a
                        ),
                        match_score=88,
                        evidence_highlights=[
                            "Python evidence",
                        ],
                        gaps_to_validate=[
                            "Redis exposure",
                        ],
                        interview_focus=[
                            "API design",
                        ],
                        matching_skills=[
                            "Python",
                        ],
                        missing_skills=[
                            "Redis",
                        ],
                    ),
                    EmployerShortlistCandidate(
                        application_id=(
                            application_b
                        ),
                        match_score=88,
                        evidence_highlights=[
                            "FastAPI evidence",
                        ],
                        gaps_to_validate=[
                            "Docker exposure",
                        ],
                        interview_focus=[
                            "Service design",
                        ],
                        matching_skills=[
                            "FastAPI",
                        ],
                        missing_skills=[
                            "Docker",
                        ],
                    ),
                ],
                ranked=False,
                recommendation_provided=False,
                human_decision_required=True,
            )
        )

    monkeypatch.setattr(
        (
            "app.api.v1.endpoints."
            "internships."
            "generate_employer_"
            "shortlist_comparison"
        ),
        fake_compare,
    )

    response = client.post(
        (
            f"/api/v1/internships/"
            f"{internship_id}/"
            "shortlist-comparison"
            "?content_locale=en"
        ),
        json={
            "application_ids": [
                str(application_a),
                str(application_b),
            ],
        },
        headers={
            "Authorization": (
                f"Bearer "
                f"valid-user-{employer_id}"
            ),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["ranked"] is False
    assert (
        body["recommendation_provided"]
        is False
    )
    assert (
        body["human_decision_required"]
        is True
    )
    assert len(body["candidates"]) == 2

    assert (
        captured["application_ids"]
        == [
            application_a,
            application_b,
        ]
    )


def test_shortlist_requires_two_to_five(
    client: TestClient,
    mock_supabase_auth,
):
    employer_id = uuid4()

    _create_profile(
        employer_id,
        "Employer Recruiter",
        account_type="employer",
    )

    response = client.post(
        (
            f"/api/v1/internships/"
            f"{uuid4()}/"
            "shortlist-comparison"
        ),
        json={
            "application_ids": [
                str(uuid4()),
            ],
        },
        headers={
            "Authorization": (
                f"Bearer "
                f"valid-user-{employer_id}"
            ),
        },
    )

    assert response.status_code == 422


def test_shortlist_preserves_tenant_isolation(
    client: TestClient,
    monkeypatch,
    mock_supabase_auth,
):
    owner_id = uuid4()
    other_id = uuid4()

    _create_profile(
        owner_id,
        "Owner",
        account_type="employer",
    )

    _create_profile(
        other_id,
        "Other",
        account_type="employer",
    )

    candidate_a = _create_profile(
        uuid4(),
        "Candidate A",
        account_type="intern",
    )

    candidate_b = _create_profile(
        uuid4(),
        "Candidate B",
        account_type="intern",
    )

    internship_id = _create_listing(
        client,
        monkeypatch,
        employer_id=owner_id,
    )

    application_a = (
        _create_submitted_application_with_match(
            candidate_profile=candidate_a,
            internship_id=internship_id,
        )
    )

    application_b = (
        _create_submitted_application_with_match(
            candidate_profile=candidate_b,
            internship_id=internship_id,
        )
    )

    response = client.post(
        (
            f"/api/v1/internships/"
            f"{internship_id}/"
            "shortlist-comparison"
        ),
        json={
            "application_ids": [
                str(application_a),
                str(application_b),
            ],
        },
        headers={
            "Authorization": (
                f"Bearer "
                f"valid-user-{other_id}"
            ),
        },
    )

    assert response.status_code == 404


def test_shortlist_service_is_identity_free_and_unranked(
    monkeypatch,
):
    employer_id = uuid4()
    internship_id = uuid4()

    profile_a = SimpleNamespace(
        id=uuid4(),
        full_name=(
            "IDENTITY A MUST NOT ENTER"
        ),
        headline="Backend Student",
        preferences={
            "department": (
                "Computer Engineering"
            ),
        },
    )

    profile_b = SimpleNamespace(
        id=uuid4(),
        full_name=(
            "IDENTITY B MUST NOT ENTER"
        ),
        headline="Software Student",
        preferences={
            "department": (
                "Software Engineering"
            ),
        },
    )

    app_a = SimpleNamespace(
        id=uuid4()
    )

    app_b = SimpleNamespace(
        id=uuid4()
    )

    match_a = SimpleNamespace(
        overall_score=88,
        skill_gap_analysis={
            "matching_skills": [
                "Python",
                "FastAPI",
            ],
            "missing_skills": [
                "Redis",
            ],
        },
    )

    match_b = SimpleNamespace(
        overall_score=82,
        skill_gap_analysis={
            "matching_skills": [
                "Python",
                "PostgreSQL",
            ],
            "missing_skills": [
                "Docker",
            ],
        },
    )

    internship = SimpleNamespace(
        id=internship_id,
        title="Backend Intern",
        company="Acme",
        location="Remote",
        work_type="remote",
        description="Build APIs.",
        required_skills=[
            "Python",
            "FastAPI",
            "PostgreSQL",
        ],
        preferred_skills=[
            "Redis",
            "Docker",
        ],
        languages=[
            "English",
        ],
        min_education="CS student",
    )

    db = MagicMock()

    db.get.return_value = internship

    contexts = {
        profile_a.id: {
            "skills": [
                "Python",
                "FastAPI",
            ],
            "education_entries": [
                "Computer Engineering",
            ],
            "experience_entries": [
                "Backend internship",
            ],
            "project_entries": [
                "FastAPI project",
            ],
        },
        profile_b.id: {
            "skills": [
                "Python",
                "PostgreSQL",
            ],
            "education_entries": [
                "Software Engineering",
            ],
            "experience_entries": [
                "API project work",
            ],
            "project_entries": [
                "PostgreSQL project",
            ],
        },
    }

    monkeypatch.setattr(
        (
            "app.services."
            "employer_shortlist_comparison."
            "MatchingDataRepository."
            "get_ai_grounding_context"
        ),
        lambda db, student_id: (
            contexts[student_id]
        ),
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

            return SimpleNamespace(
                text=json.dumps(
                    {
                        "comparison_summary": (
                            "The candidates "
                            "provide different "
                            "job-related evidence."
                        ),
                        "shared_role_requirements": [
                            "Python",
                        ],
                        "candidates": [
                            {
                                "alias": (
                                    "Candidate 1"
                                ),
                                "evidence_highlights": [
                                    "FastAPI evidence",
                                ],
                                "gaps_to_validate": [
                                    "Redis exposure",
                                ],
                                "interview_focus": [
                                    "API design",
                                ],
                            },
                            {
                                "alias": (
                                    "Candidate 2"
                                ),
                                "evidence_highlights": [
                                    "PostgreSQL evidence",
                                ],
                                "gaps_to_validate": [
                                    "Docker exposure",
                                ],
                                "interview_focus": [
                                    "Database design",
                                ],
                            },
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
            "employer_shortlist_comparison."
            "create_tracked_gemini_client"
        ),
        lambda *args, **kwargs: (
            fake_client
        ),
    )

    result = (
        generate_employer_shortlist_comparison(
            db,
            employer_user_id=employer_id,
            internship_id=internship_id,
            records=[
                (
                    app_a,
                    profile_a,
                    match_a,
                ),
                (
                    app_b,
                    profile_b,
                    match_b,
                ),
            ],
            content_locale="en",
        )
    )

    assert result.ranked is False
    assert (
        result.recommendation_provided
        is False
    )
    assert (
        result.human_decision_required
        is True
    )

    assert (
        result.candidates[0].match_score
        == 88
    )
    assert (
        result.candidates[1].match_score
        == 82
    )

    prompt_context = captured[
        "contents"
    ]

    provider_context = json.loads(
        prompt_context
    )

    for provider_candidate in provider_context[
        "candidates"
    ]:
        canonical_match = provider_candidate[
            "canonical_match"
        ]

        assert (
            "overall_score"
            not in canonical_match
        )
        assert (
            "matching_skills"
            in canonical_match
        )
        assert (
            "missing_skills"
            in canonical_match
        )

    assert (
        "IDENTITY A MUST NOT ENTER"
        not in prompt_context
    )
    assert (
        "IDENTITY B MUST NOT ENTER"
        not in prompt_context
    )

    assert (
        str(app_a.id)
        not in prompt_context
    )
    assert (
        str(app_b.id)
        not in prompt_context
    )
    assert (
        str(profile_a.id)
        not in prompt_context
    )
    assert (
        str(profile_b.id)
        not in prompt_context
    )

    assert (
        '"alias": "Candidate 1"'
        in prompt_context
    )
    assert (
        '"alias": "Candidate 2"'
        in prompt_context
    )
