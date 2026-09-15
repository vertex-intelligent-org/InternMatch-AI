"""
Secure CV Intake & Supabase Storage Service Foundation
Provides trusted server-side upload boundary for candidate CV documents (PDF/DOCX).
Validates MIME type, extension agreement, size limits, and delegates to Supabase Storage.
"""

import io
import zipfile
from dataclasses import dataclass
from uuid import UUID, uuid4

from supabase import create_client

from app.core.config import settings

MAX_CV_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MiB

ALLOWED_MIME_EXTENSIONS = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


class CVStorageValidationError(ValueError):
    """Raised when CV upload validation (MIME type, size, extension, credentials) fails."""

    pass


@dataclass(frozen=True)
class CVStoredObject:
    """Read-only result container for successfully uploaded CV document metadata."""

    storage_path: str
    content_type: str
    size_bytes: int


def store_candidate_cv(
    *,
    user_id: UUID,
    filename: str,
    content_type: str,
    content: bytes,
) -> CVStoredObject:
    """
    Validate and store candidate CV document in Supabase Storage under server-side object key.
    Enforces MIME type allowlist, filename extension agreement, 10 MiB size limit,
    and server-side path formatting: {user_id}/{uuid4}.{ext}.
    Constructs Supabase client dynamically at call-time using service-role credentials.
    """
    if not isinstance(content, bytes):
        raise CVStorageValidationError("CV file content must be raw bytes")

    size_bytes = len(content)
    if size_bytes == 0:
        raise CVStorageValidationError("CV file content cannot be empty")

    if size_bytes > MAX_CV_SIZE_BYTES:
        raise CVStorageValidationError(
            f"CV file size ({size_bytes} bytes) exceeds maximum limit of 10 MB"
        )

    clean_filename = filename.strip() if isinstance(filename, str) else ""
    if not clean_filename:
        raise CVStorageValidationError("Filename cannot be empty")

    clean_mime = content_type.strip() if isinstance(content_type, str) else ""
    if not clean_mime:
        raise CVStorageValidationError("Content type cannot be empty")

    if clean_mime not in ALLOWED_MIME_EXTENSIONS:
        raise CVStorageValidationError(
            f"Unsupported content type '{clean_mime}'. Supported MIME types are "
            "application/pdf and application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        )

    expected_ext = ALLOWED_MIME_EXTENSIONS[clean_mime]

    if "." not in clean_filename:
        raise CVStorageValidationError(f"Filename '{clean_filename}' missing file extension")

    actual_ext = clean_filename.rsplit(".", 1)[-1].lower()
    if actual_ext not in ("pdf", "docx"):
        raise CVStorageValidationError(
            f"Unsupported file extension '.{actual_ext}'. Supported extensions are .pdf and .docx"
        )

    if actual_ext != expected_ext:
        raise CVStorageValidationError(
            f"MIME type '{clean_mime}' does not match file extension '.{actual_ext}' "
            f"(expected .{expected_ext})"
        )

    # 8. File signature and container structure validation
    if expected_ext == "pdf":
        if not content.startswith(b"%PDF-"):
            raise CVStorageValidationError(
                "File signature does not match expected PDF format."
            )
    elif expected_ext == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                namelist = zf.namelist()
                if (
                    "[Content_Types].xml" not in namelist
                    or "word/document.xml" not in namelist
                ):
                    raise CVStorageValidationError(
                        "File signature does not match expected DOCX format."
                    )
        except Exception as exc:
            if isinstance(exc, CVStorageValidationError):
                raise
            raise CVStorageValidationError(
                "File signature does not match expected DOCX format."
            ) from exc

    # Validate Supabase configuration credentials before constructing client
    url = settings.SUPABASE_URL.strip() if settings.SUPABASE_URL else ""
    key = settings.SUPABASE_SERVICE_ROLE_KEY.strip() if settings.SUPABASE_SERVICE_ROLE_KEY else ""
    bucket = settings.CV_STORAGE_BUCKET.strip() if settings.CV_STORAGE_BUCKET else ""

    if not url or "placeholder" in url.lower():
        raise CVStorageValidationError("SUPABASE_URL configuration is missing or placeholder value")

    if not key or "placeholder" in key.lower():
        raise CVStorageValidationError(
            "SUPABASE_SERVICE_ROLE_KEY configuration is missing or placeholder value"
        )

    if not bucket:
        raise CVStorageValidationError("CV_STORAGE_BUCKET configuration is missing or empty")

    # Generate server-side object key: {user_id}/{uuid4}.{ext}
    object_key = f"{user_id}/{uuid4()}.{expected_ext}"

    # Construct Supabase client dynamically at call time
    supabase = create_client(url, key)
    supabase.storage.from_(bucket).upload(
        path=object_key,
        file=content,
        file_options={"content-type": clean_mime},
    )

    return CVStoredObject(
        storage_path=object_key,
        content_type=clean_mime,
        size_bytes=size_bytes,
    )


def download_candidate_cv(
    *,
    user_id: UUID,
    storage_path: str,
) -> bytes:
    """
    Download candidate CV document bytes from private Supabase Storage bucket.
    Validates that storage_path belongs strictly to the target user ({user_id}/...)
    and has a valid extension (.pdf or .docx).
    Constructs Supabase client dynamically at call time using service-role credentials.
    Rejects empty downloaded object.
    Propagates provider exceptions unchanged.
    """
    if not isinstance(user_id, UUID):
        raise CVStorageValidationError("user_id must be a valid UUID")

    if not isinstance(storage_path, str) or not storage_path.strip():
        raise CVStorageValidationError("storage_path cannot be empty")

    clean_path = storage_path.strip()

    expected_prefix = f"{user_id}/"
    if not clean_path.startswith(expected_prefix):
        raise CVStorageValidationError(
            f"Unauthorized storage path access: storage path '{clean_path}' "
            f"does not belong to user '{user_id}'"
        )

    if "." not in clean_path:
        raise CVStorageValidationError(f"Storage path '{clean_path}' missing file extension")

    ext = clean_path.rsplit(".", 1)[-1].lower()
    if ext not in ("pdf", "docx"):
        raise CVStorageValidationError(
            f"Unsupported file extension '.{ext}'. Supported extensions are .pdf and .docx"
        )

    url = settings.SUPABASE_URL.strip() if settings.SUPABASE_URL else ""
    key = settings.SUPABASE_SERVICE_ROLE_KEY.strip() if settings.SUPABASE_SERVICE_ROLE_KEY else ""
    bucket = settings.CV_STORAGE_BUCKET.strip() if settings.CV_STORAGE_BUCKET else ""

    if not url or "placeholder" in url.lower():
        raise CVStorageValidationError("SUPABASE_URL configuration is missing or placeholder value")

    if not key or "placeholder" in key.lower():
        raise CVStorageValidationError(
            "SUPABASE_SERVICE_ROLE_KEY configuration is missing or placeholder value"
        )

    if not bucket:
        raise CVStorageValidationError("CV_STORAGE_BUCKET configuration is missing or empty")

    supabase = create_client(url, key)
    res = supabase.storage.from_(bucket).download(clean_path)

    if not res or len(res) == 0:
        raise CVStorageValidationError("Downloaded CV object is empty")

    return res


def delete_candidate_cv(
    *,
    user_id: UUID,
    storage_path: str,
) -> None:
    """
    Best-effort deletion of candidate CV document from Supabase Storage.
    Validates storage_path ownership before attempting deletion.
    """
    if not isinstance(user_id, UUID):
        raise CVStorageValidationError("user_id must be a valid UUID")

    if not isinstance(storage_path, str) or not storage_path.strip():
        raise CVStorageValidationError("storage_path cannot be empty")

    clean_path = storage_path.strip()
    expected_prefix = f"{user_id}/"
    if not clean_path.startswith(expected_prefix):
        raise CVStorageValidationError(
            f"Unauthorized storage path access: storage path '{clean_path}' "
            f"does not belong to user '{user_id}'"
        )

    url = settings.SUPABASE_URL.strip() if settings.SUPABASE_URL else ""
    key = settings.SUPABASE_SERVICE_ROLE_KEY.strip() if settings.SUPABASE_SERVICE_ROLE_KEY else ""
    bucket = settings.CV_STORAGE_BUCKET.strip() if settings.CV_STORAGE_BUCKET else ""

    if (
        not url
        or "placeholder" in url.lower()
        or not key
        or "placeholder" in key.lower()
        or not bucket
    ):
        return

    supabase = create_client(url, key)
    supabase.storage.from_(bucket).remove([clean_path])
