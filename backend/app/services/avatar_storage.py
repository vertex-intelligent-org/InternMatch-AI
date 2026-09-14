"""
Secure Profile Avatar Intake & Supabase Storage Service Foundation
Provides trusted server-side upload boundary for candidate profile avatar images.
Validates MIME type, magic bytes, size limits (<= 5 MB), and delegates to Supabase Storage.
"""

from dataclasses import dataclass
from typing import Optional
from uuid import UUID, uuid4

from supabase import create_client

from app.core.config import settings

MAX_AVATAR_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MiB
AVATAR_SIGNED_URL_EXPIRY_SECONDS: int = 3600  # 1 hour

ALLOWED_IMAGE_MIMES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class AvatarStorageValidationError(ValueError):
    """Raised when Avatar upload validation (MIME type, size, extension, credentials) fails."""

    pass


@dataclass(frozen=True)
class AvatarStoredObject:
    """Read-only result container for successfully uploaded avatar document metadata."""

    storage_path: str
    content_type: str
    size_bytes: int


def _validate_image_bytes(content: bytes) -> tuple[str, str]:
    """
    Inspect magic bytes to derive verified MIME type and canonical extension.
    Returns (mime_type, extension) or raises AvatarStorageValidationError.
    """
    if len(content) < 12:
        raise AvatarStorageValidationError("Image file content is corrupted or too short")

    # JPEG signature: FF D8 FF
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"

    # PNG signature: 89 50 4E 47 0D 0A 1A 0A
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"

    # WebP signature: RIFF....WEBP
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp", "webp"

    raise AvatarStorageValidationError(
        "Unsupported image format. Allowed formats are JPEG, PNG, and WebP."
    )


def _get_supabase_storage_client():
    """Construct trusted Supabase client dynamically at call-time using service-role credentials."""
    url = settings.SUPABASE_URL.strip() if settings.SUPABASE_URL else ""
    key = (
        settings.SUPABASE_SERVICE_ROLE_KEY.strip()
        if settings.SUPABASE_SERVICE_ROLE_KEY
        else ""
    )
    bucket = (
        settings.AVATAR_STORAGE_BUCKET.strip()
        if settings.AVATAR_STORAGE_BUCKET
        else "avatars"
    )

    if not url or "placeholder" in url.lower():
        raise AvatarStorageValidationError(
            "SUPABASE_URL configuration is missing or placeholder value"
        )

    if not key or "placeholder" in key.lower():
        raise AvatarStorageValidationError(
            "SUPABASE_SERVICE_ROLE_KEY configuration is missing or placeholder value"
        )

    if not bucket:
        raise AvatarStorageValidationError(
            "AVATAR_STORAGE_BUCKET configuration is missing or empty"
        )

    client = create_client(url, key)
    return client, bucket


def store_candidate_avatar(
    *,
    user_id: UUID,
    content_type: Optional[str] = None,
    content: bytes,
) -> AvatarStoredObject:
    """
    Validate and store candidate avatar image in private Supabase Storage bucket.
    Enforces <= 5 MB limit, binary signature check, and server-side object path:
    {user_id}/{uuid4}.{ext}.
    """
    if not isinstance(user_id, UUID):
        raise AvatarStorageValidationError("user_id must be a valid UUID")

    if not isinstance(content, bytes):
        raise AvatarStorageValidationError("Avatar file content must be raw bytes")

    size_bytes = len(content)
    if size_bytes == 0:
        raise AvatarStorageValidationError("Avatar file content cannot be empty")

    if size_bytes > MAX_AVATAR_SIZE_BYTES:
        raise AvatarStorageValidationError(
            f"Avatar file size ({size_bytes} bytes) exceeds maximum limit of 5 MB"
        )

    # Validate image magic bytes directly from binary stream
    verified_mime, verified_ext = _validate_image_bytes(content)

    # If content_type header was supplied, ensure it matches
    if content_type:
        clean_mime = content_type.strip().lower()
        if clean_mime in ("image/jpg", "image/pjpeg"):
            clean_mime = "image/jpeg"
        if clean_mime not in ALLOWED_IMAGE_MIMES:
            raise AvatarStorageValidationError(
                f"Unsupported content type '{content_type}'. "
                "Allowed types: image/jpeg, image/png, image/webp"
            )
        if clean_mime != verified_mime:
            raise AvatarStorageValidationError(
                f"Content-Type header '{content_type}' does not match "
                f"file binary content '{verified_mime}'"
            )

    # Server-side object key format: {user_id}/{uuid4}.{ext} inside the avatars bucket
    object_key = f"{user_id}/{uuid4()}.{verified_ext}"

    client, bucket = _get_supabase_storage_client()

    client.storage.from_(bucket).upload(
        path=object_key,
        file=content,
        file_options={"content-type": verified_mime},
    )

    return AvatarStoredObject(
        storage_path=object_key,
        content_type=verified_mime,
        size_bytes=size_bytes,
    )


def generate_avatar_signed_url(
    *,
    user_id: UUID,
    storage_path: Optional[str],
    expires_in: int = AVATAR_SIGNED_URL_EXPIRY_SECONDS,
) -> Optional[str]:
    """
    Generate short-lived signed download URL for private avatar object.
    Verifies that the requested storage_path belongs strictly to target user_id ({user_id}/...).
    Returns None if storage_path is empty or generation fails.
    """
    if not storage_path or not isinstance(storage_path, str) or not storage_path.strip():
        return None

    clean_path = storage_path.strip()

    # Path ownership assertion: must start with {user_id}/
    expected_prefix = f"{user_id}/"
    if not clean_path.startswith(expected_prefix):
        return None

    try:
        client, bucket = _get_supabase_storage_client()
        res = client.storage.from_(bucket).create_signed_url(
            path=clean_path,
            expires_in=expires_in,
        )
        if isinstance(res, dict) and "signedURL" in res:
            return res["signedURL"]
        if isinstance(res, dict) and "signedUrl" in res:
            return res["signedUrl"]
        if hasattr(res, "signed_url"):
            return res.signed_url
        if isinstance(res, str):
            return res
        return None
    except Exception:
        return None


def delete_candidate_avatar(
    *,
    user_id: UUID,
    storage_path: Optional[str],
) -> bool:
    """
    Delete avatar object from private Supabase Storage bucket.
    Verifies storage_path ownership ({user_id}/...) before deletion.
    """
    if not storage_path or not isinstance(storage_path, str) or not storage_path.strip():
        return False

    clean_path = storage_path.strip()

    # Path ownership assertion: must start with {user_id}/
    expected_prefix = f"{user_id}/"
    if not clean_path.startswith(expected_prefix):
        return False

    try:
        client, bucket = _get_supabase_storage_client()
        client.storage.from_(bucket).remove([clean_path])
        return True
    except Exception:
        return False
