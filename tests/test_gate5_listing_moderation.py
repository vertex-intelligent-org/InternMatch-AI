"""Gate 5 mandatory listing moderation and employer quota UX."""

from __future__ import annotations

import ast
from pathlib import Path


def _function_source(
    path: str,
    function_name: str,
) -> str:
    source = Path(path).read_text(
        encoding="utf-8"
    )

    tree = ast.parse(source)

    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        )
        and node.name == function_name
    ]

    assert len(matches) == 1

    node = matches[0]

    lines = source.splitlines()

    start = min(
        [
            decorator.lineno
            for decorator in node.decorator_list
        ]
        + [node.lineno]
    )

    return "\n".join(
        lines[
            start - 1:
            node.end_lineno
        ]
    )


def test_employer_submission_is_hidden_until_admin_publication():
    block = _function_source(
        "backend/app/repositories/internship.py",
        "create_employer_listing",
    )

    assert (
        'publication_status="under_review"'
        in block
    )

    assert "is_active=False" in block

    assert (
        'publication_status="published"'
        not in block
    )


def test_candidate_visibility_remains_published_only():
    block = _function_source(
        "backend/app/repositories/internship.py",
        "public_internship_visibility_condition",
    )

    assert (
        'publication_status == "published"'
        in block
    )


def test_admin_publication_still_rechecks_listing_capacity():
    block = _function_source(
        "backend/app/api/v1/endpoints/admin_internships.py",
        "reopen_admin_internship",
    )

    capacity = block.index(
        "require_employer_listing_capacity("
    )

    publish = block.index(
        "reopen_listing("
    )

    assert capacity < publish


def test_mobile_quota_and_verification_failures_are_separate():
    source = Path(
        "apps/mobile/src/screens/CreateOpportunityScreen.js"
    ).read_text(
        encoding="utf-8"
    )

    enforce_start = source.index(
        "const enforceVerifiedEmployer"
    )

    enforce_end = source.index(
        "}, [navigation]);",
        enforce_start,
    )

    enforce_block = source[
        enforce_start:enforce_end
    ]

    assert (
        enforce_block.count(
            "navigation.replace('EmployerVerification')"
        )
        == 1
    )

    assert (
        "listingQuotaReached"
        in source
    )

    assert (
        "active_listing_limit"
        in Path(
            "apps/mobile/src/services/api.ts"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert (
        "listingLimitReachedTitle"
        in source
    )

    assert (
        "navigation.navigate('Plans')"
        in source
    )

    assert (
        "activeInternshipCapacity"
        in source
    )


def test_gate5_localization_contract_is_present_in_all_locales():
    for locale in (
        "ar.js",
        "en.js",
        "tr.js",
    ):
        source = Path(
            "apps/mobile/src/localization/locales"
        ).joinpath(
            locale
        ).read_text(
            encoding="utf-8"
        )

        assert (
            "listingLimitReachedTitle:"
            in source
        )

        assert (
            "listingLimitReachedMessage:"
            in source
        )

        assert "upgradeToPro:" in source
        assert "reviewNotice:" in source



def test_employer_edit_invalidates_previous_publication():
    block = _function_source(
        "backend/app/repositories/internship.py",
        "update_employer_listing",
    )

    assert (
        'listing.publication_status = "under_review"'
        in block
    )

    assert "listing.is_active = False" in block



def test_gate5_admin_review_and_visibility_integrity_contract():
    admin_source = Path(
        "backend/app/api/v1/endpoints/admin_internships.py"
    ).read_text(
        encoding="utf-8"
    )

    repo_source = Path(
        "backend/app/repositories/internship.py"
    ).read_text(
        encoding="utf-8"
    )

    analytics_source = Path(
        "backend/app/services/employer_pipeline_analytics.py"
    ).read_text(
        encoding="utf-8"
    )

    api_source = Path(
        "apps/admin/lib/api.ts"
    ).read_text(
        encoding="utf-8"
    )

    ui_source = Path(
        "apps/admin/app/listings/page.tsx"
    ).read_text(
        encoding="utf-8"
    )

    assert '"/{id}/approve"' in admin_source
    assert '"/{id}/request-changes"' in admin_source

    assert (
        'snapshot.publication_status != "under_review"'
        in admin_source
    )

    assert (
        'listing.publication_status = "draft"'
        in admin_source
    )

    approve_start = admin_source.index(
        "def approve_admin_internship("
    )
    approve_end = admin_source.index(
        "def request_changes_admin_internship(",
        approve_start,
    )
    approve_block = admin_source[
        approve_start:approve_end
    ]

    # Approval is a distinct under_review -> published transition.
    # It must not delegate into the closed-listing reopen route.
    assert (
        'publication_status != "under_review"'
        in approve_block
    )
    assert (
        "require_employer_listing_capacity("
        in approve_block
    )
    assert (
        "get_by_id_for_update("
        in approve_block
    )
    assert (
        "InternshipRepository.reopen_listing("
        in approve_block
    )
    assert (
        "return reopen_admin_internship("
        not in approve_block
    )

    # Moderation notification dedupe must never depend on a
    # nonexistent InternshipListing.updated_at attribute.
    assert "listing.updated_at" not in admin_source

    assert (
        "approval_decided_at = datetime.now("
        in approve_block
    )

    request_changes_start = admin_source.index(
        "def request_changes_admin_internship("
    )
    request_changes_block = admin_source[
        request_changes_start:
    ]

    assert (
        "changes_requested_at = datetime.now("
        in request_changes_block
    )


    list_start = admin_source.index(
        "def list_admin_internships("
    )

    list_end = admin_source.index(
        "@router.get(",
        list_start + 1,
    )

    list_block = admin_source[
        list_start:list_end
    ]

    assert (
        'publication_status == "published"'
        in list_block
    )

    assert (
        "InternshipRepository.list_internships("
        in list_block
    )

    count_start = repo_source.index(
        "def count_published_by_employer("
    )

    count_end = repo_source.index(
        "@staticmethod",
        count_start + 1,
    )

    count_block = repo_source[
        count_start:count_end
    ]

    assert (
        "public_internship_visibility_condition()"
        in count_block
    )

    assert (
        "public_internship_visibility_condition()"
        in analytics_source
    )

    assert "approveAdminInternship" in api_source
    assert "requestChangesAdminInternship" in api_source

    assert "Approve & publish" in ui_source
    assert "Request changes" in ui_source

    # Request-changes must carry explicit employer-visible feedback only.
    assert (
        "payload: AdminInternshipChangesRequest"
        in request_changes_block
    )
    assert (
        '"employer_visible_feedback": ('
        in request_changes_block
    )

    schema_source = Path(
        "backend/app/schemas/internship.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "class AdminInternshipChangesRequest"
        in schema_source
    )
    assert (
        "max_length=1000"
        in schema_source
    )
    assert (
        "internal_admin_note"
        not in request_changes_block
    )

    assert (
        "employer_visible_feedback"
        in api_source
    )
    assert (
        "Employer-visible feedback"
        in ui_source
    )


def test_gate5_admin_review_routes_are_registered_and_protected():
    from uuid import uuid4

    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    listing_id = uuid4()

    for action in (
        "approve",
        "request-changes",
    ):
        response = client.post(
            (
                "/api/v1/admin/internships/"
                f"{listing_id}/{action}"
            )
        )

        assert response.status_code == 401
