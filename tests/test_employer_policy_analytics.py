"""Employer product-policy and pipeline-analytics tests."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.services.employer_pipeline_analytics import (
    EmployerPipelineAnalyticsResponse,
    get_employer_pipeline_analytics,
)
from app.services.employer_product_policy import (
    FEATURE_INTERVIEW_KIT,
    EmployerFeatureAccessError,
    get_employer_product_policy,
    require_employer_feature,
)
from fastapi.testclient import TestClient

from tests.test_employer_internships import (
    _create_profile,
)


def test_employer_product_policy_defaults_free(
    monkeypatch,
):
    user_id = uuid4()

    monkeypatch.setattr(
        (
            "app.services.employer_product_policy."
            "get_employer_subscription_snapshot"
        ),
        lambda db, user_id: {
            "plan": "free",
            "is_active": False,
        },
    )

    policy = get_employer_product_policy(
        MagicMock(),
        user_id=user_id,
    )

    assert policy.plan == "free"
    assert policy.is_pro is False
    assert policy.active_listing_limit == 1
    assert policy.candidate_insight_available is True
    assert policy.interview_kit_available is False
    assert policy.shortlist_comparison_available is False
    assert policy.internship_description_available is False
    assert policy.pipeline_analytics_available is False


def test_employer_product_policy_uses_backend_pro_entitlement(
    monkeypatch,
):
    user_id = uuid4()

    monkeypatch.setattr(
        (
            "app.services.employer_product_policy."
            "get_employer_subscription_snapshot"
        ),
        lambda db, user_id: {
            "plan": "employer_pro",
            "is_active": True,
        },
    )

    policy = get_employer_product_policy(
        MagicMock(),
        user_id=user_id,
    )

    assert policy.plan == "employer_pro"
    assert policy.is_pro is True
    assert policy.active_listing_limit is None
    assert policy.candidate_insight_available is True
    assert policy.interview_kit_available is True
    assert policy.shortlist_comparison_available is True
    assert policy.internship_description_available is True
    assert policy.pipeline_analytics_available is True


def test_employer_pro_feature_fails_closed_for_free(
    monkeypatch,
):
    user_id = uuid4()

    monkeypatch.setattr(
        (
            "app.services.employer_product_policy."
            "get_employer_subscription_snapshot"
        ),
        lambda db, user_id: {
            "plan": "free",
            "is_active": False,
        },
    )

    with pytest.raises(
        EmployerFeatureAccessError
    ):
        require_employer_feature(
            MagicMock(),
            user_id=user_id,
            feature_key=FEATURE_INTERVIEW_KIT,
        )


def test_pipeline_analytics_is_current_state_and_tenant_scoped():
    employer_id = uuid4()

    listing_result = MagicMock()
    listing_result.all.return_value = [
        ("draft", 1),
        ("published", 2),
        ("closed", 1),
    ]

    application_result = MagicMock()
    application_result.all.return_value = [
        ("applied", 4),
        ("interviewing", 2),
        ("accepted", 1),
        ("rejected", 1),
    ]

    db = MagicMock()
    db.execute.side_effect = [
        listing_result,
        application_result,
    ]

    # Raw publication_status contains two "published" rows,
    # but only one satisfies the canonical candidate/public
    # visibility predicate. This intentionally models the
    # historical Admin 38 vs Candidate 35 class of mismatch.
    db.scalar.return_value = 1

    result = get_employer_pipeline_analytics(
        db,
        employer_user_id=employer_id,
    )

    assert result.analytics_scope == (
        "current_pipeline_snapshot"
    )
    assert result.total_listings == 4
    assert result.draft_listings == 1
    # Published analytics are candidate-visible listings,
    # not the raw publication_status bucket.
    assert result.published_listings == 1
    assert result.closed_listings == 1

    assert (
        result.total_submitted_applications
        == 8
    )
    assert result.applied == 4
    assert result.interviewing == 2
    assert result.accepted == 1
    assert result.rejected == 1

    assert (
        result.interviewing_share_percent
        == 25.0
    )
    assert result.decision_share_percent == 25.0
    assert (
        result.acceptance_share_among_decisions_percent
        == 50.0
    )

    statements = [
        str(call.args[0])
        for call in db.execute.call_args_list
    ]

    assert len(statements) == 2

    assert db.scalar.call_count == 1

    visible_statement = str(
        db.scalar.call_args.args[0]
    )

    assert "employer_user_id" in visible_statement
    assert "publication_status" in visible_statement
    assert "listing_source" in visible_statement

    assert all(
        "employer_user_id" in statement
        for statement in statements
    )

    assert "applications.status" in statements[1]


def test_pipeline_analytics_endpoint_requires_pro(
    client: TestClient,
    mock_supabase_auth,
):
    employer_id = uuid4()

    _create_profile(
        employer_id,
        "Free Employer",
        account_type="employer",
    )

    response = client.get(
        (
            "/api/v1/internships/"
            "employer-tools/pipeline-analytics"
        ),
        headers={
            "Authorization": (
                f"Bearer valid-user-{employer_id}"
            ),
        },
    )

    assert response.status_code == 403


def test_pipeline_analytics_endpoint_returns_pro_snapshot(
    client: TestClient,
    monkeypatch,
    mock_supabase_auth,
):
    employer_id = uuid4()

    _create_profile(
        employer_id,
        "Pro Employer",
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
            "get_employer_pipeline_analytics"
        ),
        lambda db, employer_user_id: (
            EmployerPipelineAnalyticsResponse(
                total_listings=3,
                draft_listings=0,
                under_review_listings=0,
                published_listings=2,
                closed_listings=1,
                total_submitted_applications=7,
                applied=3,
                interviewing=2,
                accepted=1,
                rejected=1,
                interviewing_share_percent=28.6,
                decision_share_percent=28.6,
                acceptance_share_among_decisions_percent=50.0,
            )
        ),
    )

    response = client.get(
        (
            "/api/v1/internships/"
            "employer-tools/pipeline-analytics"
        ),
        headers={
            "Authorization": (
                f"Bearer valid-user-{employer_id}"
            ),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total_listings"] == 3
    assert (
        body["total_submitted_applications"]
        == 7
    )
    assert body["accepted"] == 1
    assert body["rejected"] == 1
