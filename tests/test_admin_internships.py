"""Server-authorized internship listing administration tests."""

from uuid import UUID, uuid4

from app.core.config import settings
from app.db.models import (
    Application,
    InternshipListing,
    StudentProfile,
)
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
                metadata_json=(
                    {
                        "created_via":
                            "admin_console",
                        "created_by_admin_user_id":
                            str(uuid4()),
                    }
                    if (
                        listing_source
                        == "curated"
                        and employer_user_id
                        is None
                    )
                    else {}
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
    assert response.json()["admin_managed"] is True
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

def test_admin_can_manage_listing_applicants(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    listing_id = _create_listing()

    candidate_a_user_id = uuid4()
    candidate_b_user_id = uuid4()

    with TestingSessionLocal() as db:
        candidate_a = StudentProfile(
            id=uuid4(),
            user_id=candidate_a_user_id,
            full_name="Admin Candidate A",
            preferences={
                "account_type": "intern",
                "department": "Computer Science",
            },
        )
        candidate_b = StudentProfile(
            id=uuid4(),
            user_id=candidate_b_user_id,
            full_name="Admin Candidate B",
            preferences={
                "account_type": "intern",
                "department": "Engineering",
            },
        )

        db.add_all([
            candidate_a,
            candidate_b,
        ])
        db.flush()

        application_a = Application(
            id=uuid4(),
            student_id=candidate_a.id,
            internship_id=listing_id,
            status="applied",
            generated_cover_letter=(
                "Candidate A cover letter."
            ),
        )
        application_b = Application(
            id=uuid4(),
            student_id=candidate_b.id,
            internship_id=listing_id,
            status="applied",
            generated_cover_letter=(
                "Candidate B cover letter."
            ),
        )

        db.add_all([
            application_a,
            application_b,
        ])
        db.commit()

        application_a_id = application_a.id
        application_b_id = application_b.id

    headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    applicants = client.get(
        (
            f"/api/v1/admin/internships/"
            f"{listing_id}/applicants"
        ),
        headers=headers,
    )

    assert applicants.status_code == 200
    assert applicants.json()["total"] == 2

    interview = client.post(
        (
            f"/api/v1/admin/internships/"
            f"{listing_id}/applicants/"
            f"{application_a_id}/interview"
        ),
        headers=headers,
        json={
            "scheduled_at": (
                "2099-01-15T10:30:00+03:00"
            ),
            "mode": "online",
            "location": (
                "https://meet.example.com/interview"
            ),
            "message": "See you then.",
        },
    )

    assert interview.status_code == 200
    assert (
        interview.json()["status"]
        == "interviewing"
    )

    accepted = client.patch(
        (
            f"/api/v1/admin/internships/"
            f"{listing_id}/applicants/"
            f"{application_a_id}/status"
        ),
        headers=headers,
        json={
            "status": "accepted",
        },
    )

    assert accepted.status_code == 200
    assert (
        accepted.json()["status"]
        == "accepted"
    )

    rejected = client.patch(
        (
            f"/api/v1/admin/internships/"
            f"{listing_id}/applicants/"
            f"{application_b_id}/status"
        ),
        headers=headers,
        json={
            "status": "rejected",
        },
    )

    assert rejected.status_code == 200
    assert (
        rejected.json()["status"]
        == "rejected"
    )

    with TestingSessionLocal() as db:
        persisted_a = db.get(
            Application,
            application_a_id,
        )
        persisted_b = db.get(
            Application,
            application_b_id,
        )

        assert persisted_a.status == "accepted"
        assert (
            persisted_a.interview_location
            == "https://meet.example.com/interview"
        )
        assert persisted_b.status == "rejected"


def test_admin_can_delete_listing_without_applications(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    listing_id = _create_listing()

    headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    response = client.delete(
        (
            f"/api/v1/admin/internships/"
            f"{listing_id}"
        ),
        headers=headers,
    )

    assert response.status_code == 204

    with TestingSessionLocal() as db:
        assert (
            db.get(
                InternshipListing,
                listing_id,
            )
            is None
        )


def test_admin_delete_fails_closed_when_any_application_exists(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    listing_id = _create_listing()
    candidate_user_id = uuid4()

    with TestingSessionLocal() as db:
        candidate = StudentProfile(
            id=uuid4(),
            user_id=candidate_user_id,
            full_name="Draft Candidate",
            preferences={
                "account_type": "intern",
            },
        )
        db.add(candidate)
        db.flush()

        db.add(
            Application(
                id=uuid4(),
                student_id=candidate.id,
                internship_id=listing_id,
                status="saved",
                generated_cover_letter=(
                    "Candidate draft must be preserved."
                ),
            )
        )
        db.commit()

    headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    response = client.delete(
        (
            f"/api/v1/admin/internships/"
            f"{listing_id}"
        ),
        headers=headers,
    )

    assert response.status_code == 409

    with TestingSessionLocal() as db:
        assert (
            db.get(
                InternshipListing,
                listing_id,
            )
            is not None
        )

def test_admin_recruiter_actions_reject_employer_owned_listing(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    employer_user_id = uuid4()

    listing_id = _create_listing(
        listing_source="employer",
        employer_user_id=employer_user_id,
    )

    clean_listing_id = _create_listing(
        listing_source="employer",
        employer_user_id=employer_user_id,
    )

    candidate_user_id = uuid4()

    with TestingSessionLocal() as db:
        candidate = StudentProfile(
            id=uuid4(),
            user_id=candidate_user_id,
            full_name="Employer Candidate",
            preferences={
                "account_type": "intern",
            },
        )

        db.add(candidate)
        db.flush()

        application = Application(
            id=uuid4(),
            student_id=candidate.id,
            internship_id=listing_id,
            status="applied",
            generated_cover_letter=(
                "Employer-owned application."
            ),
        )

        db.add(application)
        db.commit()

        application_id = application.id

    headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    detail = client.get(
        (
            f"/api/v1/admin/internships/"
            f"{listing_id}"
        ),
        headers=headers,
    )

    assert detail.status_code == 200
    assert detail.json()["admin_managed"] is False

    applicants = client.get(
        (
            f"/api/v1/admin/internships/"
            f"{listing_id}/applicants"
        ),
        headers=headers,
    )

    applicant_detail = client.get(
        (
            f"/api/v1/admin/internships/"
            f"{listing_id}/applicants/"
            f"{application_id}"
        ),
        headers=headers,
    )

    status_update = client.patch(
        (
            f"/api/v1/admin/internships/"
            f"{listing_id}/applicants/"
            f"{application_id}/status"
        ),
        headers=headers,
        json={
            "status": "accepted",
        },
    )

    interview = client.post(
        (
            f"/api/v1/admin/internships/"
            f"{listing_id}/applicants/"
            f"{application_id}/interview"
        ),
        headers=headers,
        json={
            "scheduled_at":
                "2099-01-15T10:30:00+03:00",
            "mode": "online",
            "location":
                "https://example.invalid/interview",
            "message": "Boundary test.",
        },
    )

    delete_clean_employer_listing = (
        client.delete(
            (
                f"/api/v1/admin/internships/"
                f"{clean_listing_id}"
            ),
            headers=headers,
        )
    )

    assert applicants.status_code == 409
    assert applicant_detail.status_code == 409
    assert status_update.status_code == 409
    assert interview.status_code == 409

    assert (
        delete_clean_employer_listing.status_code
        == 409
    )

    with TestingSessionLocal() as db:
        persisted_application = db.get(
            Application,
            application_id,
        )

        persisted_listing = db.get(
            InternshipListing,
            clean_listing_id,
        )

        assert (
            persisted_application.status
            == "applied"
        )

        assert (
            persisted_application
            .interview_scheduled_at
            is None
        )

        assert persisted_listing is not None



def test_admin_candidate_cv_is_brokered_without_provider_url(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    listing_id = _create_listing()

    candidate_user_id = uuid4()
    candidate_profile_id = uuid4()
    application_id = uuid4()

    storage_path = (
        f"{candidate_user_id}/"
        "private-candidate-cv.pdf"
    )

    with TestingSessionLocal() as db:
        candidate = StudentProfile(
            id=candidate_profile_id,
            user_id=candidate_user_id,
            full_name="Private CV Candidate",
            cv_storage_path=storage_path,
            preferences={
                "account_type": "intern",
            },
        )

        application = Application(
            id=application_id,
            student_id=candidate.id,
            internship_id=listing_id,
            status="applied",
            generated_cover_letter=(
                "Submitted application."
            ),
        )

        db.add_all([
            candidate,
            application,
        ])
        db.commit()

    calls = {}

    def fake_download_candidate_cv(
        *,
        user_id,
        storage_path,
    ):
        calls["user_id"] = user_id
        calls["storage_path"] = (
            storage_path
        )

        return (
            b"%PDF-1.7\n"
            b"secure-admin-cv"
        )

    monkeypatch.setattr(
        (
            "app.api.v1.endpoints."
            "admin_internships."
            "download_candidate_cv"
        ),
        fake_download_candidate_cv,
    )

    admin_headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    path = (
        "/api/v1/admin/internships/"
        f"{listing_id}/applicants/"
        f"{application_id}/cv/content"
    )

    response = client.get(
        path,
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        .startswith("application/pdf")
    )
    assert (
        response.headers[
            "content-disposition"
        ]
        == (
            'inline; filename='
            '"candidate-cv.pdf"'
        )
    )
    assert (
        response.headers[
            "cache-control"
        ]
        == "private, no-store, max-age=0"
    )
    assert (
        response.headers["pragma"]
        == "no-cache"
    )
    assert (
        response.headers[
            "x-content-type-options"
        ]
        == "nosniff"
    )
    assert (
        response.headers[
            "referrer-policy"
        ]
        == "no-referrer"
    )

    assert response.content == (
        b"%PDF-1.7\n"
        b"secure-admin-cv"
    )

    assert (
        calls["user_id"]
        == candidate_user_id
    )
    assert (
        calls["storage_path"]
        == storage_path
    )

    # Private storage metadata/provider URLs
    # are never serialized to the caller.
    assert (
        storage_path.encode("utf-8")
        not in response.content
    )
    assert (
        b"supabase.co"
        not in response.content
    )

    # Anonymous browser/API access is blocked.
    unauthenticated = client.get(
        path
    )
    assert (
        unauthenticated.status_code
        == 401
    )

    # A normal student token is not an admin token.
    student_user_id = uuid4()
    student_token = (
        f"student-cv-{student_user_id}"
    )

    _register_token(
        mock_supabase_auth,
        token=student_token,
        user_id=student_user_id,
        email="student@example.test",
    )

    student_response = client.get(
        path,
        headers={
            "Authorization":
                f"Bearer {student_token}"
        },
    )

    assert (
        student_response.status_code
        == 403
    )

    # An employer token also has no admin authority.
    employer_user_id = uuid4()
    employer_token = (
        f"employer-cv-{employer_user_id}"
    )

    _register_token(
        mock_supabase_auth,
        token=employer_token,
        user_id=employer_user_id,
        email="employer@example.test",
    )

    employer_response = client.get(
        path,
        headers={
            "Authorization":
                f"Bearer {employer_token}"
        },
    )

    assert (
        employer_response.status_code
        == 403
    )


def test_admin_candidate_cv_fails_closed_across_resource_boundaries(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    listing_a = _create_listing()
    listing_b = _create_listing()

    employer_owned_listing = (
        _create_listing(
            listing_source="employer",
            employer_user_id=uuid4(),
        )
    )

    with TestingSessionLocal() as db:
        submitted_candidate = (
            StudentProfile(
                id=uuid4(),
                user_id=uuid4(),
                full_name="Submitted Candidate",
                cv_storage_path=(
                    "submitted-user/cv.pdf"
                ),
                preferences={
                    "account_type": "intern",
                },
            )
        )

        saved_candidate = (
            StudentProfile(
                id=uuid4(),
                user_id=uuid4(),
                full_name="Saved Candidate",
                cv_storage_path=(
                    "saved-user/cv.pdf"
                ),
                preferences={
                    "account_type": "intern",
                },
            )
        )

        no_cv_candidate = (
            StudentProfile(
                id=uuid4(),
                user_id=uuid4(),
                full_name="No CV Candidate",
                cv_storage_path=None,
                preferences={
                    "account_type": "intern",
                },
            )
        )

        db.add_all([
            submitted_candidate,
            saved_candidate,
            no_cv_candidate,
        ])
        db.flush()

        submitted_application = (
            Application(
                id=uuid4(),
                student_id=(
                    submitted_candidate.id
                ),
                internship_id=listing_a,
                status="applied",
            )
        )

        saved_application = (
            Application(
                id=uuid4(),
                student_id=saved_candidate.id,
                internship_id=listing_a,
                status="saved",
            )
        )

        no_cv_application = (
            Application(
                id=uuid4(),
                student_id=no_cv_candidate.id,
                internship_id=listing_a,
                status="applied",
            )
        )

        db.add_all([
            submitted_application,
            saved_application,
            no_cv_application,
        ])
        db.commit()

        submitted_application_id = (
            submitted_application.id
        )
        saved_application_id = (
            saved_application.id
        )
        no_cv_application_id = (
            no_cv_application.id
        )

    def storage_must_not_be_reached(
        **_kwargs,
    ):
        raise AssertionError(
            "Unauthorized boundary reached CV storage."
        )

    monkeypatch.setattr(
        (
            "app.api.v1.endpoints."
            "admin_internships."
            "download_candidate_cv"
        ),
        storage_must_not_be_reached,
    )

    headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    wrong_listing = client.get(
        (
            "/api/v1/admin/internships/"
            f"{listing_b}/applicants/"
            f"{submitted_application_id}"
            "/cv/content"
        ),
        headers=headers,
    )

    assert wrong_listing.status_code == 404

    saved_draft = client.get(
        (
            "/api/v1/admin/internships/"
            f"{listing_a}/applicants/"
            f"{saved_application_id}"
            "/cv/content"
        ),
        headers=headers,
    )

    assert saved_draft.status_code == 404

    missing_cv = client.get(
        (
            "/api/v1/admin/internships/"
            f"{listing_a}/applicants/"
            f"{no_cv_application_id}"
            "/cv/content"
        ),
        headers=headers,
    )

    assert missing_cv.status_code == 404

    employer_boundary = client.get(
        (
            "/api/v1/admin/internships/"
            f"{employer_owned_listing}"
            "/applicants/"
            f"{submitted_application_id}"
            "/cv/content"
        ),
        headers=headers,
    )

    # Admin recruiter actions are intentionally
    # isolated from employer-owned listings.
    assert (
        employer_boundary.status_code
        == 409
    )
