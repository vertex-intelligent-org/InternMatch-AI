"""Gate 2 employer organization verification API tests."""

from uuid import UUID, uuid4

import pytest
from app.core.config import settings
from app.db.models import (
    EmployerOrganization,
    EmployerVerificationEvent,
    InternshipListing,
    StudentProfile,
)
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal


def _create_employer_profile(user_id):
    db = TestingSessionLocal()
    try:
        db.add(
            StudentProfile(
                user_id=user_id,
                full_name="Employer User",
                preferences={
                    "account_type": "employer",
                },
            )
        )
        db.commit()
    finally:
        db.close()


def _create_student_profile(user_id):
    db = TestingSessionLocal()
    try:
        db.add(
            StudentProfile(
                user_id=user_id,
                full_name="Student User",
                preferences={
                    "account_type": "intern",
                },
            )
        )
        db.commit()
    finally:
        db.close()


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


def _organization_payload(
    *,
    business_email="hr@acme.example",
):
    return {
        "legal_name": "Acme Teknoloji Anonim Sirketi",
        "display_name": "Acme",
        "website_url": "https://acme.example/careers",
        "business_email": business_email,
        "country_code": "tr",
        "registration_number": "TR-123456",
        "tax_number": "1234567890",
        "representative_name": "Ada Recruiter",
        "representative_role": "HR Manager",
    }


def _create_org_via_api(
    client,
    mock_supabase_auth,
    *,
    user_id,
    email="hr@acme.example",
):
    token = f"employer-{user_id}"

    _create_employer_profile(user_id)

    _register_token(
        mock_supabase_auth,
        token=token,
        user_id=user_id,
        email=email,
    )

    response = client.post(
        "/api/v1/employer-organization",
        json=_organization_payload(
            business_email=email
        ),
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 201
    return token, response.json()


def _submit_org(
    client,
    *,
    token,
):
    response = client.post(
        "/api/v1/employer-organization/submit",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == 200
    return response.json()


def _admin_headers(
    mock_supabase_auth,
    monkeypatch,
):
    admin_user_id = uuid4()
    admin_token = f"admin-{admin_user_id}"

    _register_token(
        mock_supabase_auth,
        token=admin_token,
        user_id=admin_user_id,
        email="admin@internmatch.college",
    )

    monkeypatch.setattr(
        settings,
        "ADMIN_USER_IDS",
        str(admin_user_id),
    )

    return (
        admin_user_id,
        {
            "Authorization": f"Bearer {admin_token}",
        },
    )


def test_employer_can_create_unverified_organization(
    client: TestClient,
    mock_supabase_auth,
):
    user_id = uuid4()

    _, organization = _create_org_via_api(
        client,
        mock_supabase_auth,
        user_id=user_id,
    )

    assert organization["owner_user_id"] == str(user_id)
    assert organization["verification_status"] == "unverified"
    assert organization["normalized_domain"] == "acme.example"
    assert organization["country_code"] == "TR"
    assert organization["email_domain_matches_website"] is True
    assert organization["reviewed_at"] is None

    db = TestingSessionLocal()
    try:
        events = (
            db.query(EmployerVerificationEvent)
            .filter(
                EmployerVerificationEvent.organization_id
                == UUID(organization["id"])
            )
            .all()
        )
        assert len(events) == 1
        assert events[0].action == "created"
        assert events[0].new_status == "unverified"
    finally:
        db.close()


def test_student_cannot_create_employer_organization(
    client: TestClient,
    mock_supabase_auth,
):
    user_id = uuid4()
    token = f"student-{user_id}"

    _create_student_profile(user_id)

    _register_token(
        mock_supabase_auth,
        token=token,
        user_id=user_id,
        email="student@example.com",
    )

    response = client.post(
        "/api/v1/employer-organization",
        json=_organization_payload(
            business_email="student@example.com"
        ),
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 403


def test_business_email_must_match_authenticated_email(
    client: TestClient,
    mock_supabase_auth,
):
    user_id = uuid4()
    token = f"employer-{user_id}"

    _create_employer_profile(user_id)

    _register_token(
        mock_supabase_auth,
        token=token,
        user_id=user_id,
        email="owner@acme.example",
    )

    response = client.post(
        "/api/v1/employer-organization",
        json=_organization_payload(
            business_email="other@acme.example"
        ),
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "verification_status",
        "reviewed_by",
        "reviewed_at",
        "rejection_reason_code",
    ],
)
def test_employer_cannot_inject_verification_authority_fields(
    client: TestClient,
    mock_supabase_auth,
    forbidden_field,
):
    user_id = uuid4()
    token = f"employer-{user_id}"

    _create_employer_profile(user_id)

    _register_token(
        mock_supabase_auth,
        token=token,
        user_id=user_id,
        email="hr@acme.example",
    )

    payload = _organization_payload()
    payload[forbidden_field] = "attacker-controlled"

    response = client.post(
        "/api/v1/employer-organization",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 422


def test_employer_can_submit_unverified_org_for_review(
    client: TestClient,
    mock_supabase_auth,
):
    user_id = uuid4()

    token, organization = _create_org_via_api(
        client,
        mock_supabase_auth,
        user_id=user_id,
    )

    submitted = _submit_org(
        client,
        token=token,
    )

    assert submitted["id"] == organization["id"]
    assert submitted["verification_status"] == "pending"
    assert submitted["submitted_at"] is not None
    assert submitted["reviewed_at"] is None

    db = TestingSessionLocal()
    try:
        events = (
            db.query(EmployerVerificationEvent)
            .filter(
                EmployerVerificationEvent.organization_id
                == UUID(organization["id"])
            )
            .order_by(
                EmployerVerificationEvent.created_at.asc()
            )
            .all()
        )
        assert [event.action for event in events] == [
            "created",
            "submitted",
        ]
    finally:
        db.close()


def test_pending_organization_cannot_be_edited(
    client: TestClient,
    mock_supabase_auth,
):
    user_id = uuid4()

    token, _ = _create_org_via_api(
        client,
        mock_supabase_auth,
        user_id=user_id,
    )

    _submit_org(
        client,
        token=token,
    )

    payload = _organization_payload()
    payload["display_name"] = "Changed While Pending"

    response = client.put(
        "/api/v1/employer-organization",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 409


def test_non_admin_cannot_access_review_queue(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    user_id = uuid4()
    token = f"regular-{user_id}"

    _register_token(
        mock_supabase_auth,
        token=token,
        user_id=user_id,
        email="user@example.com",
    )

    monkeypatch.setattr(
        settings,
        "ADMIN_USER_IDS",
        str(uuid4()),
    )

    response = client.get(
        "/api/v1/admin/employer-organizations",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 403


def test_admin_can_approve_pending_organization(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    owner_user_id = uuid4()

    token, organization = _create_org_via_api(
        client,
        mock_supabase_auth,
        user_id=owner_user_id,
    )

    _submit_org(
        client,
        token=token,
    )

    admin_user_id, headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    response = client.post(
        (
            "/api/v1/admin/employer-organizations/"
            f"{organization['id']}/approve"
        ),
        json={
            "internal_note": "Registry and company domain reviewed.",
        },
        headers=headers,
    )

    assert response.status_code == 200
    approved = response.json()
    assert approved["verification_status"] == "verified"
    assert approved["reviewed_at"] is not None

    db = TestingSessionLocal()
    try:
        stored = db.get(
            EmployerOrganization,
            UUID(organization["id"]),
        )
        assert stored is not None
        assert stored.reviewed_by == admin_user_id

        event = (
            db.query(EmployerVerificationEvent)
            .filter(
                EmployerVerificationEvent.organization_id
                == UUID(organization["id"]),
                EmployerVerificationEvent.action
                == "approved",
            )
            .one()
        )
        assert event.reviewer_user_id == admin_user_id
        assert event.internal_note == (
            "Registry and company domain reviewed."
        )
    finally:
        db.close()


def test_admin_can_reject_and_employer_can_resubmit(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    owner_user_id = uuid4()

    token, organization = _create_org_via_api(
        client,
        mock_supabase_auth,
        user_id=owner_user_id,
    )

    _submit_org(
        client,
        token=token,
    )

    _, headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    rejection = client.post(
        (
            "/api/v1/admin/employer-organizations/"
            f"{organization['id']}/reject"
        ),
        json={
            "reason_code": "registration_mismatch",
            "internal_note": "Registry number did not match.",
        },
        headers=headers,
    )

    assert rejection.status_code == 200
    assert rejection.json()["verification_status"] == "rejected"
    assert (
        rejection.json()["rejection_reason_code"]
        == "registration_mismatch"
    )

    update_payload = _organization_payload()
    update_payload["registration_number"] = "TR-CORRECTED"

    update = client.put(
        "/api/v1/employer-organization",
        json=update_payload,
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert update.status_code == 200

    resubmit = client.post(
        "/api/v1/employer-organization/submit",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert resubmit.status_code == 200
    assert resubmit.json()["verification_status"] == "pending"
    assert resubmit.json()["rejection_reason_code"] is None
    assert resubmit.json()["reviewed_at"] is None

    db = TestingSessionLocal()
    try:
        event = (
            db.query(EmployerVerificationEvent)
            .filter(
                EmployerVerificationEvent.organization_id
                == UUID(organization["id"]),
                EmployerVerificationEvent.action
                == "resubmitted",
            )
            .one()
        )
        assert event.previous_status == "rejected"
        assert event.new_status == "pending"
    finally:
        db.close()


def test_admin_suspension_deactivates_employer_listings(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    owner_user_id = uuid4()

    token, organization = _create_org_via_api(
        client,
        mock_supabase_auth,
        user_id=owner_user_id,
    )

    _submit_org(
        client,
        token=token,
    )

    _, headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    approve = client.post(
        (
            "/api/v1/admin/employer-organizations/"
            f"{organization['id']}/approve"
        ),
        json={},
        headers=headers,
    )
    assert approve.status_code == 200

    listing_id = uuid4()

    db = TestingSessionLocal()
    try:
        db.add(
            InternshipListing(
                id=listing_id,
                employer_user_id=owner_user_id,
                title="Backend Intern",
                company="Acme",
                location="Istanbul",
                work_type="hybrid",
                description="Internship description",
                required_skills=["Python"],
                preferred_skills=[],
                language="English",
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    suspend = client.post(
        (
            "/api/v1/admin/employer-organizations/"
            f"{organization['id']}/suspend"
        ),
        json={
            "reason_code": "suspected_abuse",
            "internal_note": "Manual moderation suspension.",
        },
        headers=headers,
    )

    assert suspend.status_code == 200
    assert suspend.json()["verification_status"] == "suspended"

    db = TestingSessionLocal()
    try:
        listing = db.get(
            InternshipListing,
            listing_id,
        )
        assert listing is not None
        assert listing.is_active is False

        event = (
            db.query(EmployerVerificationEvent)
            .filter(
                EmployerVerificationEvent.organization_id
                == UUID(organization["id"]),
                EmployerVerificationEvent.action
                == "suspended",
            )
            .one()
        )
        assert event.reason_code == "suspected_abuse"
    finally:
        db.close()


def test_admin_queue_defaults_to_pending(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    owner_user_id = uuid4()

    token, organization = _create_org_via_api(
        client,
        mock_supabase_auth,
        user_id=owner_user_id,
    )

    _submit_org(
        client,
        token=token,
    )

    _, headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    response = client.get(
        "/api/v1/admin/employer-organizations",
        headers=headers,
    )

    assert response.status_code == 200

    returned_ids = {
        item["id"]
        for item in response.json()
    }

    assert organization["id"] in returned_ids
