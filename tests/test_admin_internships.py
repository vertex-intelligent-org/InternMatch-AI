"""Server-authorized internship listing administration tests."""

from uuid import UUID, uuid4

from app.core.config import settings
from app.db.models import InternshipListing
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal


def _register_token(
    mock_supabase_auth,
    *,
    token,
    user_id,
    email,
):
    mock_supabase_auth(
        token,
        claims={
            "iss": (
                f"{settings.SUPABASE_URL.rstrip('/')}"
                "/auth/v1"
            ),
            "aud": "authenticated",
            "sub": str(user_id),
            "email": email,
            "role": "authenticated",
        },
    )


def _admin_headers(
    mock_supabase_auth,
    monkeypatch,
):
    user_id = uuid4()
    token = f"admin-listings-{user_id}"

    _register_token(
        mock_supabase_auth,
        token=token,
        user_id=user_id,
        email="admin@internmatch.college",
    )

    monkeypatch.setattr(
        settings,
        "ADMIN_USER_IDS",
        str(user_id),
    )

    return {
        "Authorization": f"Bearer {token}",
    }


def _create_listing(
    *,
    publication_status="published",
    listing_source="curated",
    employer_user_id=None,
):
    listing_id = uuid4()

    db = TestingSessionLocal()
    try:
        db.add(
            InternshipListing(
                id=listing_id,
                employer_user_id=employer_user_id,
                listing_source=listing_source,
                title="Admin Managed Internship",
                company="InternMatch Test Company",
                location="Istanbul",
                work_type="hybrid",
                description="Administrative listing test.",
                required_skills=["Python"],
                preferred_skills=[],
                language="English",
                publication_status=publication_status,
                is_active=(
                    publication_status
                    == "published"
                ),
            )
        )
        db.commit()
    finally:
        db.close()

    return listing_id


def test_admin_listing_routes_require_admin(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    response = client.get(
        "/api/v1/admin/internships"
    )
    assert response.status_code == 401

    user_id = uuid4()
    token = f"non-admin-{user_id}"

    _register_token(
        mock_supabase_auth,
        token=token,
        user_id=user_id,
        email="user@internmatch.college",
    )

    monkeypatch.setattr(
        settings,
        "ADMIN_USER_IDS",
        "",
    )

    response = client.get(
        "/api/v1/admin/internships",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == 403


def _admin_create_payload(**overrides):
    payload = {
        "title": "Platform Engineering Intern",
        "company": "InternMatch AI Team",
        "location": "Istanbul, Turkiye",
        "work_type": "hybrid",
        "description": (
            "Build reliable platform services and internal tooling."
        ),
        "required_skills": ["Python", "Git"],
        "preferred_skills": ["Docker"],
        "language": "English",
        "education_requirements": (
            "Currently enrolled in a relevant degree."
        ),
        "experience_requirements": (
            "Academic or personal software projects."
        ),
        "publication_status": "published",
    }
    payload.update(overrides)
    return payload


def _mock_admin_embedding(monkeypatch):
    monkeypatch.setattr(
        (
            "app.api.v1.endpoints."
            "admin_internships.generate_embedding"
        ),
        lambda _text: [
            0.0
            for _ in range(
                settings.EMBEDDING_DIMENSION
            )
        ],
    )


def test_admin_create_opportunity_requires_admin(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    _mock_admin_embedding(monkeypatch)

    response = client.post(
        "/api/v1/admin/internships",
        json=_admin_create_payload(),
    )
    assert response.status_code == 401

    user_id = uuid4()
    token = f"non-admin-create-{user_id}"

    _register_token(
        mock_supabase_auth,
        token=token,
        user_id=user_id,
        email="user@internmatch.college",
    )

    monkeypatch.setattr(
        settings,
        "ADMIN_USER_IDS",
        "",
    )

    response = client.post(
        "/api/v1/admin/internships",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json=_admin_create_payload(),
    )
    assert response.status_code == 403


def test_admin_can_create_published_curated_opportunity(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    _mock_admin_embedding(monkeypatch)

    headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    response = client.post(
        "/api/v1/admin/internships",
        headers=headers,
        json=_admin_create_payload(),
    )

    assert response.status_code == 201

    body = response.json()

    assert body["company"] == "InternMatch AI Team"
    assert body["publication_status"] == "published"
    assert body["is_active"] is True

    db = TestingSessionLocal()
    try:
        listing = db.get(
            InternshipListing,
            UUID(body["id"]),
        )

        assert listing is not None
        assert listing.listing_source == "curated"
        assert listing.employer_user_id is None
        assert (
            listing.employer_organization_id
            is None
        )
        assert (
            listing.metadata_json[
                "created_via"
            ]
            == "admin_console"
        )
        assert (
            listing.metadata_json[
                "created_by_admin_user_id"
            ]
            is not None
        )
    finally:
        db.close()

    public_response = client.get(
        "/api/v1/internships"
    )

    assert public_response.status_code == 200
    assert body["id"] in {
        item["id"]
        for item in public_response.json()["items"]
    }


def test_admin_can_create_hidden_draft_with_default_company(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    _mock_admin_embedding(monkeypatch)

    headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    payload = _admin_create_payload(
        publication_status="draft"
    )
    payload.pop("company")

    response = client.post(
        "/api/v1/admin/internships",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 201

    body = response.json()

    assert body["company"] == "InternMatch AI Team"
    assert body["publication_status"] == "draft"
    assert body["is_active"] is False

    public_response = client.get(
        "/api/v1/internships"
    )

    assert public_response.status_code == 200
    assert body["id"] not in {
        item["id"]
        for item in public_response.json()["items"]
    }


def test_admin_can_list_and_filter_all_states(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    published_id = _create_listing(
        publication_status="published"
    )
    closed_id = _create_listing(
        publication_status="closed"
    )

    headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    response = client.get(
        "/api/v1/admin/internships",
        headers=headers,
    )
    assert response.status_code == 200

    ids = {
        item["id"]
        for item in response.json()["items"]
    }

    assert str(published_id) in ids
    assert str(closed_id) in ids

    response = client.get(
        (
            "/api/v1/admin/internships"
            "?publication_status=closed"
        ),
        headers=headers,
    )
    assert response.status_code == 200

    items = response.json()["items"]

    assert str(closed_id) in {
        item["id"]
        for item in items
    }
    assert all(
        item["publication_status"] == "closed"
        for item in items
    )


def test_admin_can_read_close_and_reopen_curated_listing(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    listing_id = _create_listing()

    headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    response = client.get(
        f"/api/v1/admin/internships/{listing_id}",
        headers=headers,
    )
    assert response.status_code == 200
    assert (
        response.json()["publication_status"]
        == "published"
    )

    response = client.post(
        f"/api/v1/admin/internships/{listing_id}/close",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["publication_status"] == "closed"
    assert response.json()["is_active"] is False

    response = client.post(
        f"/api/v1/admin/internships/{listing_id}/reopen",
        headers=headers,
    )
    assert response.status_code == 200
    assert (
        response.json()["publication_status"]
        == "published"
    )
    assert response.json()["is_active"] is True


def test_admin_cannot_reopen_unbound_employer_listing(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    listing_id = _create_listing(
        publication_status="closed",
        listing_source="employer",
        employer_user_id=uuid4(),
    )

    headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    response = client.post(
        f"/api/v1/admin/internships/{listing_id}/reopen",
        headers=headers,
    )

    assert response.status_code == 409


def test_admin_listing_detail_returns_404(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    response = client.get(
        f"/api/v1/admin/internships/{uuid4()}",
        headers=headers,
    )

    assert response.status_code == 404
