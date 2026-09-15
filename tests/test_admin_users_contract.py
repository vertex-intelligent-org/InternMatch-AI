from types import SimpleNamespace
from uuid import uuid4

from app.api.v1.endpoints.admin_users import (
    AdminUserDetail,
    AdminUserListResponse,
    AdminUserSummary,
    _build_directory,
)
from app.main import app
from fastapi.testclient import TestClient


def test_admin_users_routes_are_registered_and_admin_protected():
    client = TestClient(app)

    user_id = uuid4()

    list_response = client.get(
        "/api/v1/admin/users",
        headers={
            "Accept": "application/json",
        },
    )

    detail_response = client.get(
        f"/api/v1/admin/users/{user_id}",
        headers={
            "Accept": "application/json",
        },
    )

    assert list_response.status_code == 401
    assert detail_response.status_code == 401


def test_admin_user_public_models_exclude_sensitive_storage_and_auth_fields():
    models = (
        AdminUserSummary,
        AdminUserListResponse,
        AdminUserDetail,
    )

    forbidden = {
        "password",
        "password_hash",
        "access_token",
        "refresh_token",
        "cv_storage_path",
        "avatar_storage_path",
        "registration_number",
        "tax_number",
    }

    for model in models:
        assert (
            forbidden
            & set(model.model_fields)
            == set()
        )


def test_directory_merges_student_and_employer_identity_by_user_id():
    user_id = uuid4()
    organization_id = uuid4()

    student = SimpleNamespace(
        user_id=user_id,
        full_name="Candidate Name",
        headline="Backend Engineer",
        created_at=None,
        updated_at=None,
    )

    organization = SimpleNamespace(
        owner_user_id=user_id,
        id=organization_id,
        display_name="Acme Labs",
        legal_name="Acme Labs Ltd",
        business_email="jobs@acme.example",
        verification_status="verified",
        organization_type="company",
        country_code="TR",
        created_at=None,
        updated_at=None,
    )

    items = _build_directory(
        students=[student],
        organizations=[organization],
        query=None,
        role=None,
    )

    assert len(items) == 1

    item = items[0]

    assert item.user_id == user_id
    assert item.roles == [
        "student",
        "employer",
    ]
    assert item.display_name == "Acme Labs"
    assert item.headline == "Backend Engineer"
    assert item.organization_id == organization_id


def test_directory_searches_safe_admin_metadata_only():
    student = SimpleNamespace(
        user_id=uuid4(),
        full_name="Ada Candidate",
        headline="Python Developer",
        created_at=None,
        updated_at=None,
    )

    organization = SimpleNamespace(
        owner_user_id=uuid4(),
        id=uuid4(),
        display_name="Vertex Robotics",
        legal_name="Vertex Robotics Ltd",
        business_email="careers@vertex.example",
        verification_status="pending",
        organization_type="company",
        country_code="TR",
        created_at=None,
        updated_at=None,
    )

    candidate_results = _build_directory(
        students=[student],
        organizations=[organization],
        query="python",
        role=None,
    )

    employer_results = _build_directory(
        students=[student],
        organizations=[organization],
        query="careers@vertex",
        role=None,
    )

    assert len(candidate_results) == 1
    assert candidate_results[0].roles == [
        "student"
    ]

    assert len(employer_results) == 1
    assert employer_results[0].roles == [
        "employer"
    ]


def test_directory_role_filter_is_fail_closed():
    student = SimpleNamespace(
        user_id=uuid4(),
        full_name="Candidate",
        headline=None,
        created_at=None,
        updated_at=None,
    )

    organization = SimpleNamespace(
        owner_user_id=uuid4(),
        id=uuid4(),
        display_name="Employer",
        legal_name="Employer Ltd",
        business_email="jobs@example.com",
        verification_status="pending",
        organization_type="company",
        country_code="TR",
        created_at=None,
        updated_at=None,
    )

    students = _build_directory(
        students=[student],
        organizations=[organization],
        query=None,
        role="student",
    )

    employers = _build_directory(
        students=[student],
        organizations=[organization],
        query=None,
        role="employer",
    )

    assert len(students) == 1
    assert students[0].roles == [
        "student"
    ]

    assert len(employers) == 1
    assert employers[0].roles == [
        "employer"
    ]



def test_admin_users_frontend_contract():
    from pathlib import Path

    types_source = Path(
        "apps/admin/lib/types.ts"
    ).read_text(
        encoding="utf-8"
    )

    api_source = Path(
        "apps/admin/lib/api.ts"
    ).read_text(
        encoding="utf-8"
    )

    page_source = Path(
        "apps/admin/app/users/page.tsx"
    ).read_text(
        encoding="utf-8"
    )

    assert "AdminUserSummary" in types_source
    assert "AdminUserDetail" in types_source
    assert "AdminUserAuditEvent" in types_source

    assert (
        "export async function listAdminUsers("
        in api_source
    )

    assert (
        "export async function getAdminUser("
        in api_source
    )

    assert "'/admin/users?'" in api_source
    assert "'/admin/users/'" in api_source

    assert "Audit timeline" in page_source
    assert "Search users" in page_source
    assert '["/users", "Users"]' in page_source
    assert "href={href}" in page_source

    forbidden = (
        "cv_storage_path",
        "avatar_storage_path",
        "password_hash",
        "refresh_token",
    )

    for value in forbidden:
        assert value not in page_source
        assert value not in types_source


def test_existing_admin_pages_link_to_users_directory():
    from pathlib import Path

    paths = (
        Path("apps/admin/app/page.tsx"),
        Path("apps/admin/app/listings/page.tsx"),
        Path("apps/admin/app/compliance/page.tsx"),
    )

    for path in paths:
        source = path.read_text(
            encoding="utf-8"
        )

        assert (
            source.count('href="/users"')
            == 2
        )
