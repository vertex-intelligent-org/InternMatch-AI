"""Employer compliance claim and evidence API tests."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.core.config import settings
from app.db.models import (
    EmployerComplianceClaim,
    EmployerComplianceEvidence,
    EmployerComplianceEvent,
    EmployerOrganization,
    StudentProfile,
)
from app.services.employer_compliance_storage import (
    ComplianceStoredObject,
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


def _create_employer(
    mock_supabase_auth,
    *,
    user_id=None,
    email="hr@acme.example",
):
    user_id = user_id or uuid4()
    token = f"employer-{user_id}"

    _register_token(
        mock_supabase_auth,
        token=token,
        user_id=user_id,
        email=email,
    )

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

        organization = EmployerOrganization(
            owner_user_id=user_id,
            legal_name="Acme Teknoloji AS",
            display_name="Acme",
            website_url="https://acme.example",
            normalized_domain="acme.example",
            business_email=email,
            country_code="TR",
            registration_number="TR-123",
            tax_number=None,
            representative_name="Ada Recruiter",
            representative_role="HR Manager",
            verification_status="verified",
            organization_type="company",
            verification_method="standard_company",
            submitted_at=datetime.now(
                timezone.utc
            ),
            reviewed_at=datetime.now(
                timezone.utc
            ),
            reviewed_by=uuid4(),
            rejection_reason_code=None,
        )

        db.add(organization)
        db.commit()
        db.refresh(organization)

        return (
            user_id,
            token,
            organization.id,
        )
    finally:
        db.close()


def _admin_headers(
    mock_supabase_auth,
    monkeypatch,
):
    admin_id = uuid4()
    token = f"admin-{admin_id}"

    _register_token(
        mock_supabase_auth,
        token=token,
        user_id=admin_id,
        email="admin@internmatch.college",
    )

    monkeypatch.setattr(
        settings,
        "ADMIN_USER_IDS",
        str(admin_id),
    )

    return {
        "Authorization": f"Bearer {token}"
    }


def _headers(token):
    return {
        "Authorization": f"Bearer {token}"
    }


def _create_claim(
    client,
    token,
    *,
    claim_type="insurance_arrangement",
    scope_key="organization",
):
    response = client.post(
        "/api/v1/employer-compliance/claims",
        headers=_headers(token),
        json={
            "claim_type": claim_type,
            "jurisdiction_country_code": "tr",
            "scope_key": scope_key,
            "statement": "Evidence-backed claim.",
        },
    )

    assert response.status_code == 201

    return response.json()


def test_employer_creates_jurisdiction_scoped_draft(
    client: TestClient,
    mock_supabase_auth,
):
    _, token, organization_id = (
        _create_employer(
            mock_supabase_auth
        )
    )

    claim = _create_claim(
        client,
        token,
    )

    assert claim["organization_id"] == str(
        organization_id
    )

    assert (
        claim["jurisdiction_country_code"]
        == "TR"
    )

    assert claim["status"] == "draft"
    assert claim["version"] == 1
    assert claim["evidence"] == []

    serialized = str(claim).lower()

    assert "storage_path" not in serialized
    assert "internal_note" not in serialized


def test_duplicate_claim_scope_is_conflict(
    client: TestClient,
    mock_supabase_auth,
):
    _, token, _ = _create_employer(
        mock_supabase_auth
    )

    _create_claim(
        client,
        token,
    )

    response = client.post(
        "/api/v1/employer-compliance/claims",
        headers=_headers(token),
        json={
            "claim_type": (
                "insurance_arrangement"
            ),
            "jurisdiction_country_code": "TR",
            "scope_key": "organization",
        },
    )

    assert response.status_code == 409


def test_other_employer_cannot_read_claim(
    client: TestClient,
    mock_supabase_auth,
):
    _, owner_token, _ = _create_employer(
        mock_supabase_auth,
        email="owner@acme.example",
    )

    claim = _create_claim(
        client,
        owner_token,
    )

    _, other_token, _ = _create_employer(
        mock_supabase_auth,
        email="other@other.example",
    )

    response = client.get(
        (
            "/api/v1/employer-compliance/"
            f"claims/{claim['id']}/"
            "evidence/"
            f"{uuid4()}/url"
        ),
        headers=_headers(other_token),
    )

    assert response.status_code == 404


def test_evidence_upload_hides_storage_path_and_bumps_version(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    _, token, organization_id = (
        _create_employer(
            mock_supabase_auth
        )
    )

    claim = _create_claim(
        client,
        token,
        claim_type="completion_certificate",
    )

    claim_id = UUID(claim["id"])

    def fake_store(**kwargs):
        return ComplianceStoredObject(
            storage_path=(
                f"{organization_id}/"
                f"{claim_id}/"
                f"{uuid4()}.pdf"
            ),
            content_type="application/pdf",
            size_bytes=12,
            sha256_hex="a" * 64,
        )

    monkeypatch.setattr(
        "app.api.v1.endpoints.employer_compliance."
        "store_compliance_evidence",
        fake_store,
    )

    response = client.post(
        (
            "/api/v1/employer-compliance/"
            f"claims/{claim['id']}/evidence"
            f"?expected_version={claim['version']}"
        ),
        headers=_headers(token),
        files={
            "file": (
                "certificate.pdf",
                b"%PDF-test",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["version"] == 2
    assert len(body["evidence"]) == 1

    serialized = str(body).lower()

    assert "storage_path" not in serialized
    assert "sha256" not in serialized


def test_submit_requires_evidence(
    client: TestClient,
    mock_supabase_auth,
):
    _, token, _ = _create_employer(
        mock_supabase_auth
    )

    claim = _create_claim(
        client,
        token,
    )

    response = client.post(
        (
            "/api/v1/employer-compliance/"
            f"claims/{claim['id']}/submit"
        ),
        headers=_headers(token),
        json={
            "expected_version": claim["version"]
        },
    )

    assert response.status_code == 422


def test_submit_then_admin_approve_is_version_safe(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    employer_id, token, organization_id = (
        _create_employer(
            mock_supabase_auth
        )
    )

    claim = _create_claim(
        client,
        token,
        claim_type="university_agreement",
        scope_key="uskudar-university",
    )

    claim_id = UUID(claim["id"])

    monkeypatch.setattr(
        "app.api.v1.endpoints.employer_compliance."
        "store_compliance_evidence",
        lambda **kwargs: ComplianceStoredObject(
            storage_path=(
                f"{organization_id}/"
                f"{claim_id}/"
                f"{uuid4()}.pdf"
            ),
            content_type="application/pdf",
            size_bytes=100,
            sha256_hex="b" * 64,
        ),
    )

    upload = client.post(
        (
            "/api/v1/employer-compliance/"
            f"claims/{claim['id']}/evidence"
            f"?expected_version={claim['version']}"
        ),
        headers=_headers(token),
        files={
            "file": (
                "agreement.pdf",
                b"%PDF-agreement",
                "application/pdf",
            )
        },
    )

    assert upload.status_code == 200

    uploaded = upload.json()

    submit = client.post(
        (
            "/api/v1/employer-compliance/"
            f"claims/{claim['id']}/submit"
        ),
        headers=_headers(token),
        json={
            "expected_version": (
                uploaded["version"]
            )
        },
    )

    assert submit.status_code == 200

    pending = submit.json()

    assert pending["status"] == "pending"

    admin_headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    approve = client.post(
        (
            "/api/v1/admin/employer-compliance/"
            f"claims/{claim['id']}/approve"
        ),
        headers=admin_headers,
        json={
            "expected_version": (
                pending["version"]
            ),
            "internal_note": (
                "Agreement evidence reviewed."
            ),
        },
    )

    assert approve.status_code == 200

    approved = approve.json()

    assert approved["status"] == "approved"
    assert (
        approved["version"]
        == pending["version"] + 1
    )

    db = TestingSessionLocal()

    try:
        organization = db.get(
            EmployerOrganization,
            organization_id,
        )

        assert organization is not None

        assert (
            organization.verification_status
            == "verified"
        )

        events = (
            db.query(EmployerComplianceEvent)
            .filter(
                EmployerComplianceEvent.claim_id
                == claim_id
            )
            .all()
        )

        assert any(
            event.action == "approved"
            and event.actor_role == "admin"
            for event in events
        )

        evidence = (
            db.query(EmployerComplianceEvidence)
            .filter(
                EmployerComplianceEvidence.claim_id
                == claim_id
            )
            .one()
        )

        assert (
            evidence.uploaded_by_user_id
            == employer_id
        )
    finally:
        db.close()


def test_stale_version_is_rejected(
    client: TestClient,
    mock_supabase_auth,
):
    _, token, _ = _create_employer(
        mock_supabase_auth
    )

    claim = _create_claim(
        client,
        token,
    )

    response = client.put(
        (
            "/api/v1/employer-compliance/"
            f"claims/{claim['id']}"
        ),
        headers=_headers(token),
        json={
            "expected_version": 999,
            "statement": "Concurrent edit.",
        },
    )

    assert response.status_code == 409


def test_admin_signed_url_is_on_demand_only(
    client: TestClient,
    mock_supabase_auth,
    monkeypatch,
):
    _, token, organization_id = (
        _create_employer(
            mock_supabase_auth
        )
    )

    claim = _create_claim(
        client,
        token,
    )

    claim_id = UUID(claim["id"])
    evidence_id = uuid4()

    db = TestingSessionLocal()

    try:
        db.add(
            EmployerComplianceEvidence(
                id=evidence_id,
                claim_id=claim_id,
                storage_path=(
                    f"{organization_id}/"
                    f"{claim_id}/"
                    f"{uuid4()}.pdf"
                ),
                original_filename="evidence.pdf",
                content_type="application/pdf",
                size_bytes=100,
                sha256_hex="c" * 64,
                uploaded_by_user_id=None,
            )
        )

        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        "app.api.v1.endpoints.employer_compliance."
        "generate_compliance_evidence_signed_url",
        lambda **kwargs: (
            "https://signed.example/admin-evidence"
        ),
    )

    admin_headers = _admin_headers(
        mock_supabase_auth,
        monkeypatch,
    )

    detail = client.get(
        (
            "/api/v1/admin/employer-compliance/"
            f"claims/{claim['id']}"
        ),
        headers=admin_headers,
    )

    assert detail.status_code == 200
    assert "signed.example" not in str(
        detail.json()
    )

    access = client.get(
        (
            "/api/v1/admin/employer-compliance/"
            f"claims/{claim['id']}/evidence/"
            f"{evidence_id}/url"
        ),
        headers=admin_headers,
    )

    assert access.status_code == 200

    assert access.json()["evidence_url"] == (
        "https://signed.example/admin-evidence"
    )


def test_regular_responses_never_expose_raw_storage_path(
    client: TestClient,
    mock_supabase_auth,
):
    _, token, _ = _create_employer(
        mock_supabase_auth
    )

    claim = _create_claim(
        client,
        token,
    )

    response = client.get(
        "/api/v1/employer-compliance/claims",
        headers=_headers(token),
    )

    assert response.status_code == 200

    assert "storage_path" not in str(
        response.json()
    ).lower()
