"""Private employer compliance evidence storage tests."""

import hashlib
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.services.employer_compliance_storage import (
    COMPLIANCE_SIGNED_URL_EXPIRY_SECONDS,
    MAX_COMPLIANCE_EVIDENCE_SIZE_BYTES,
    ComplianceStorageValidationError,
    ComplianceStoredObject,
    generate_compliance_evidence_signed_url,
    store_compliance_evidence,
)


@pytest.fixture(autouse=True)
def valid_storage_settings(monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings.SUPABASE_URL",
        "https://valid-project.supabase.co",
    )
    monkeypatch.setattr(
        "app.core.config.settings.SUPABASE_SERVICE_ROLE_KEY",
        "valid-service-role-secret",
    )
    monkeypatch.setattr(
        "app.core.config.settings.COMPLIANCE_STORAGE_BUCKET",
        "employer-compliance-evidence",
    )


def _client():
    bucket = MagicMock()
    bucket.upload.return_value = {
        "path": "stored.pdf"
    }
    bucket.create_signed_url.return_value = {
        "signedURL": "https://signed.example/evidence"
    }

    storage = MagicMock()
    storage.from_.return_value = bucket

    client = MagicMock()
    client.storage = storage

    return client, bucket


def test_valid_pdf_is_private_server_generated_and_hashed(
    monkeypatch,
):
    client, bucket = _client()

    monkeypatch.setattr(
        "app.services.employer_compliance_storage.create_client",
        lambda url, key: client,
    )

    organization_id = uuid4()
    claim_id = uuid4()
    content = b"%PDF-1.7 compliance evidence"

    result = store_compliance_evidence(
        organization_id=organization_id,
        claim_id=claim_id,
        filename="insurance-policy.pdf",
        content_type="application/pdf",
        content=content,
    )

    assert isinstance(
        result,
        ComplianceStoredObject,
    )

    assert result.storage_path.startswith(
        f"{organization_id}/{claim_id}/"
    )

    assert result.storage_path.endswith(
        ".pdf"
    )

    assert "insurance-policy" not in (
        result.storage_path
    )

    assert result.sha256_hex == hashlib.sha256(
        content
    ).hexdigest()

    client.storage.from_.assert_called_once_with(
        "employer-compliance-evidence"
    )

    bucket.upload.assert_called_once()


@pytest.mark.parametrize(
    ("filename", "content_type", "content"),
    [
        (
            "evidence.png",
            "image/png",
            b"%PDF-fake",
        ),
        (
            "evidence.pdf",
            "application/pdf",
            b"not-a-pdf",
        ),
        (
            "evidence.docx",
            "application/pdf",
            b"%PDF-fake",
        ),
    ],
)
def test_invalid_evidence_is_rejected_before_storage(
    monkeypatch,
    filename,
    content_type,
    content,
):
    calls = []

    monkeypatch.setattr(
        "app.services.employer_compliance_storage.create_client",
        lambda url, key: calls.append(1),
    )

    with pytest.raises(
        ComplianceStorageValidationError
    ):
        store_compliance_evidence(
            organization_id=uuid4(),
            claim_id=uuid4(),
            filename=filename,
            content_type=content_type,
            content=content,
        )

    assert calls == []


def test_oversize_evidence_is_rejected(
    monkeypatch,
):
    calls = []

    monkeypatch.setattr(
        "app.services.employer_compliance_storage.create_client",
        lambda url, key: calls.append(1),
    )

    with pytest.raises(
        ComplianceStorageValidationError,
        match="10 MB",
    ):
        store_compliance_evidence(
            organization_id=uuid4(),
            claim_id=uuid4(),
            filename="evidence.pdf",
            content_type="application/pdf",
            content=(
                b"%PDF-"
                + b"a"
                * MAX_COMPLIANCE_EVIDENCE_SIZE_BYTES
            ),
        )

    assert calls == []


def test_signed_url_requires_exact_claim_path(
    monkeypatch,
):
    client, _ = _client()

    monkeypatch.setattr(
        "app.services.employer_compliance_storage.create_client",
        lambda url, key: client,
    )

    organization_id = uuid4()
    claim_id = uuid4()
    other_claim_id = uuid4()

    path = (
        f"{organization_id}/"
        f"{other_claim_id}/"
        f"{uuid4()}.pdf"
    )

    with pytest.raises(
        ComplianceStorageValidationError,
        match="does not belong",
    ):
        generate_compliance_evidence_signed_url(
            organization_id=organization_id,
            claim_id=claim_id,
            storage_path=path,
        )


def test_signed_url_is_short_lived_and_private(
    monkeypatch,
):
    client, bucket = _client()

    monkeypatch.setattr(
        "app.services.employer_compliance_storage.create_client",
        lambda url, key: client,
    )

    organization_id = uuid4()
    claim_id = uuid4()

    path = (
        f"{organization_id}/"
        f"{claim_id}/"
        f"{uuid4()}.pdf"
    )

    url = generate_compliance_evidence_signed_url(
        organization_id=organization_id,
        claim_id=claim_id,
        storage_path=path,
    )

    assert url == (
        "https://signed.example/evidence"
    )

    bucket.create_signed_url.assert_called_once_with(
        path,
        COMPLIANCE_SIGNED_URL_EXPIRY_SECONDS,
    )


def test_placeholder_service_credentials_are_rejected(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.core.config.settings.SUPABASE_SERVICE_ROLE_KEY",
        "sb_serv_placeholder",
    )

    with pytest.raises(
        ComplianceStorageValidationError,
        match="SUPABASE_SERVICE_ROLE_KEY",
    ):
        store_compliance_evidence(
            organization_id=uuid4(),
            claim_id=uuid4(),
            filename="evidence.pdf",
            content_type="application/pdf",
            content=b"%PDF-valid",
        )
