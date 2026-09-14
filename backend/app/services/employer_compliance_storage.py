"""
Private Supabase Storage service for employer compliance evidence.

Security contract:
- PDF only
- 10 MiB maximum
- PDF magic-byte validation
- server-generated object keys
- SHA-256 metadata
- strict organization/claim path ownership checks
- short-lived signed URLs only
- service-role storage access only
"""

import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.core.config import settings
from supabase import create_client

MAX_COMPLIANCE_EVIDENCE_SIZE_BYTES = (
    10 * 1024 * 1024
)

COMPLIANCE_SIGNED_URL_EXPIRY_SECONDS = 300


class ComplianceStorageValidationError(ValueError):
    """Raised when compliance evidence fails trusted validation."""

    pass


@dataclass(frozen=True)
class ComplianceStoredObject:
    """Metadata returned after successful private evidence storage."""

    storage_path: str
    content_type: str
    size_bytes: int
    sha256_hex: str


def _storage_config() -> tuple[str, str, str]:
    url = (
        settings.SUPABASE_URL.strip()
        if settings.SUPABASE_URL
        else ""
    )

    key = (
        settings.SUPABASE_SERVICE_ROLE_KEY.strip()
        if settings.SUPABASE_SERVICE_ROLE_KEY
        else ""
    )

    bucket = (
        settings.COMPLIANCE_STORAGE_BUCKET.strip()
        if settings.COMPLIANCE_STORAGE_BUCKET
        else ""
    )

    if not url or "placeholder" in url.lower():
        raise ComplianceStorageValidationError(
            "SUPABASE_URL configuration is missing "
            "or placeholder value"
        )

    if not key or "placeholder" in key.lower():
        raise ComplianceStorageValidationError(
            "SUPABASE_SERVICE_ROLE_KEY configuration "
            "is missing or placeholder value"
        )

    if not bucket:
        raise ComplianceStorageValidationError(
            "COMPLIANCE_STORAGE_BUCKET configuration "
            "is missing or empty"
        )

    return url, key, bucket


def _validate_storage_path(
    *,
    organization_id: UUID,
    claim_id: UUID,
    storage_path: str,
) -> str:
    if not isinstance(
        organization_id,
        UUID,
    ):
        raise ComplianceStorageValidationError(
            "organization_id must be a valid UUID"
        )

    if not isinstance(claim_id, UUID):
        raise ComplianceStorageValidationError(
            "claim_id must be a valid UUID"
        )

    if (
        not isinstance(storage_path, str)
        or not storage_path.strip()
    ):
        raise ComplianceStorageValidationError(
            "storage_path cannot be empty"
        )

    clean_path = storage_path.strip()

    expected_prefix = (
        f"{organization_id}/{claim_id}/"
    )

    if not clean_path.startswith(
        expected_prefix
    ):
        raise ComplianceStorageValidationError(
            "Evidence storage path does not belong "
            "to the requested organization and claim"
        )

    if not clean_path.lower().endswith(
        ".pdf"
    ):
        raise ComplianceStorageValidationError(
            "Compliance evidence storage path "
            "must reference a PDF object"
        )

    return clean_path


def store_compliance_evidence(
    *,
    organization_id: UUID,
    claim_id: UUID,
    filename: str,
    content_type: str,
    content: bytes,
) -> ComplianceStoredObject:
    if not isinstance(content, bytes):
        raise ComplianceStorageValidationError(
            "Evidence content must be raw bytes"
        )

    size_bytes = len(content)

    if size_bytes == 0:
        raise ComplianceStorageValidationError(
            "Evidence file cannot be empty"
        )

    if (
        size_bytes
        > MAX_COMPLIANCE_EVIDENCE_SIZE_BYTES
    ):
        raise ComplianceStorageValidationError(
            "Evidence file exceeds maximum "
            "limit of 10 MB"
        )

    clean_filename = (
        filename.strip()
        if isinstance(filename, str)
        else ""
    )

    if not clean_filename:
        raise ComplianceStorageValidationError(
            "Filename cannot be empty"
        )

    if "." not in clean_filename:
        raise ComplianceStorageValidationError(
            "Evidence filename must have "
            "a .pdf extension"
        )

    extension = (
        clean_filename.rsplit(".", 1)[-1]
        .lower()
    )

    if extension != "pdf":
        raise ComplianceStorageValidationError(
            "Compliance evidence must be a PDF"
        )

    clean_type = (
        content_type.strip().lower()
        if isinstance(content_type, str)
        else ""
    )

    if clean_type != "application/pdf":
        raise ComplianceStorageValidationError(
            "Compliance evidence content type "
            "must be application/pdf"
        )

    if not content.startswith(b"%PDF-"):
        raise ComplianceStorageValidationError(
            "File signature does not match "
            "expected PDF format"
        )

    if not isinstance(
        organization_id,
        UUID,
    ):
        raise ComplianceStorageValidationError(
            "organization_id must be a valid UUID"
        )

    if not isinstance(claim_id, UUID):
        raise ComplianceStorageValidationError(
            "claim_id must be a valid UUID"
        )

    url, key, bucket = _storage_config()

    object_key = (
        f"{organization_id}/"
        f"{claim_id}/"
        f"{uuid4()}.pdf"
    )

    digest = hashlib.sha256(
        content
    ).hexdigest()

    client = create_client(url, key)

    client.storage.from_(bucket).upload(
        path=object_key,
        file=content,
        file_options={
            "content-type": "application/pdf"
        },
    )

    return ComplianceStoredObject(
        storage_path=object_key,
        content_type="application/pdf",
        size_bytes=size_bytes,
        sha256_hex=digest,
    )


def generate_compliance_evidence_signed_url(
    *,
    organization_id: UUID,
    claim_id: UUID,
    storage_path: str,
    expires_in: int = (
        COMPLIANCE_SIGNED_URL_EXPIRY_SECONDS
    ),
) -> str:
    if (
        not isinstance(expires_in, int)
        or expires_in < 60
        or expires_in > 900
    ):
        raise ComplianceStorageValidationError(
            "Compliance evidence signed URL expiry "
            "must be between 60 and 900 seconds"
        )

    clean_path = _validate_storage_path(
        organization_id=organization_id,
        claim_id=claim_id,
        storage_path=storage_path,
    )

    url, key, bucket = _storage_config()

    client = create_client(url, key)

    result = (
        client.storage.from_(bucket)
        .create_signed_url(
            clean_path,
            expires_in,
        )
    )

    signed_url = None

    if isinstance(result, dict):
        signed_url = (
            result.get("signedURL")
            or result.get("signed_url")
        )
    elif hasattr(result, "signed_url"):
        signed_url = result.signed_url

    if (
        not isinstance(signed_url, str)
        or not signed_url.strip()
    ):
        raise ComplianceStorageValidationError(
            "Storage provider did not return "
            "a valid signed evidence URL"
        )

    return signed_url.strip()


def delete_compliance_evidence(
    *,
    organization_id: UUID,
    claim_id: UUID,
    storage_path: str,
) -> None:
    clean_path = _validate_storage_path(
        organization_id=organization_id,
        claim_id=claim_id,
        storage_path=storage_path,
    )

    try:
        url, key, bucket = _storage_config()
    except ComplianceStorageValidationError:
        return

    client = create_client(url, key)

    client.storage.from_(bucket).remove(
        [clean_path]
    )
