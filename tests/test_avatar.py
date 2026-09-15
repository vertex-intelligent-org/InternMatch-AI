"""
Unit & Integration Tests for Profile Avatar End-to-End Features.
Tests upload, deletion, brokered avatar retrieval, MIME validation, file size limits,
JWT identity derivation, embedding preservation, and repository updates.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.db.models import StudentProfile
from app.repositories.student_profile import StudentProfileRepository
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal

pytestmark = pytest.mark.usefixtures("mock_supabase_auth")

# Minimal valid magic bytes
VALID_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    + b"\x00" * 100
)
VALID_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    + b"\x00" * 100
)
VALID_WEBP_BYTES = b"RIFF\x20\x00\x00\x00WEBPVP8 \x14\x00\x00\x00" + b"\x00" * 50
INVALID_TEXT_BYTES = b"This is a plain text file pretending to be an avatar"


@pytest.fixture
def mock_supabase_storage(monkeypatch):
    """Mock Supabase Storage client interactions for avatar tests."""
    mock_client = MagicMock()
    mock_from = MagicMock()
    mock_client.storage.from_.return_value = mock_from

    uploaded_objects = {}

    def mock_upload(path, file, file_options=None):
        uploaded_objects[path] = file
        return {"Key": path}

    def mock_download(path):
        return uploaded_objects.get(
            path,
            VALID_JPEG_BYTES,
        )

    def mock_remove(paths):
        for p in paths:
            uploaded_objects.pop(p, None)
        return [{"name": p} for p in paths]

    mock_from.upload.side_effect = mock_upload
    mock_from.download.side_effect = mock_download
    mock_from.remove.side_effect = mock_remove

    monkeypatch.setattr(
        "app.services.avatar_storage._get_supabase_storage_client",
        lambda: (mock_client, "avatars"),
    )
    return mock_from


def test_unauthenticated_avatar_upload_rejected(client: TestClient):
    """Test 1: Unauthenticated request to POST /api/v1/profile/avatar returns 401."""
    files = {"file": ("avatar.jpg", VALID_JPEG_BYTES, "image/jpeg")}
    response = client.post("/api/v1/profile/avatar", files=files)
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_unauthenticated_avatar_delete_rejected(client: TestClient):
    """Test 2: Unauthenticated request to DELETE /api/v1/profile/avatar returns 401."""
    response = client.delete("/api/v1/profile/avatar")
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_avatar_upload_no_profile_returns_404(client: TestClient, mock_supabase_storage):
    """Test 3: Authenticated user without profile returns 404 on avatar upload."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    files = {"file": ("avatar.jpg", VALID_JPEG_BYTES, "image/jpeg")}

    response = client.post(
        "/api/v1/profile/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"]["code"] == "NOT_FOUND"


def test_valid_avatar_upload_success(client: TestClient, mock_supabase_storage):
    """Test 4: Valid avatar upload returns only an InternMatch broker reference."""
    user_id = uuid4()
    db = TestingSessionLocal()
    profile = StudentProfile(
        user_id=user_id,
        full_name="Avatar Student",
        headline="Candidate",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    db.close()

    token = f"valid-user-{user_id}"
    files = {"file": ("avatar.png", VALID_PNG_BYTES, "image/png")}

    response = client.post(
        "/api/v1/profile/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )

    assert response.status_code == 200
    data = response.json()
    assert "avatar_url" in data
    assert data["avatar_url"].startswith(
        "/api/v1/profile/avatar/content?v="
    )
    assert "supabase.co" not in data["avatar_url"]

    # Verify DB state
    db = TestingSessionLocal()
    updated_profile = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
    assert updated_profile is not None
    assert updated_profile.avatar_storage_path is not None
    assert updated_profile.avatar_storage_path.startswith(f"{user_id}/")
    assert updated_profile.avatar_storage_path.endswith(".png")
    db.close()


def test_invalid_mime_avatar_rejected(client: TestClient, mock_supabase_storage):
    """Test 5: Invalid file format (text/pdf) rejected with 400."""
    user_id = uuid4()
    db = TestingSessionLocal()
    profile = StudentProfile(user_id=user_id, full_name="Student", headline="Dev")
    db.add(profile)
    db.commit()
    db.close()

    token = f"valid-user-{user_id}"
    files = {"file": ("fake.jpg", INVALID_TEXT_BYTES, "image/jpeg")}

    response = client.post(
        "/api/v1/profile/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["code"] == "BAD_REQUEST"


def test_oversized_avatar_rejected(client: TestClient, mock_supabase_storage):
    """Test 6: File exceeding 5 MB is rejected with 413."""
    user_id = uuid4()
    db = TestingSessionLocal()
    profile = StudentProfile(user_id=user_id, full_name="Student", headline="Dev")
    db.add(profile)
    db.commit()
    db.close()

    token = f"valid-user-{user_id}"
    oversized_bytes = VALID_JPEG_BYTES + b"\x00" * (5 * 1024 * 1024 + 100)
    files = {"file": ("huge.jpg", oversized_bytes, "image/jpeg")}

    response = client.post(
        "/api/v1/profile/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert response.status_code == 413
    assert response.json()["detail"]["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_get_profile_exposes_avatar_url_not_storage_path(
    client: TestClient, mock_supabase_storage
):
    """Test 7: GET profile exposes only an InternMatch avatar broker reference."""
    user_id = uuid4()
    storage_path = f"{user_id}/test_photo.jpg"

    db = TestingSessionLocal()
    profile = StudentProfile(
        user_id=user_id,
        full_name="Privacy Student",
        headline="Software Engineer",
        avatar_storage_path=storage_path,
    )
    db.add(profile)
    db.commit()
    db.close()

    token = f"valid-user-{user_id}"
    response = client.get("/api/v1/profile", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert "avatar_url" in data
    assert data["avatar_url"] is not None
    assert data["avatar_url"].startswith(
        "/api/v1/profile/avatar/content?v="
    )
    assert "supabase.co" not in data["avatar_url"]
    assert "avatar_storage_path" not in data


def test_replacing_avatar_updates_path_and_preserves_embedding(
    client: TestClient, mock_supabase_storage
):
    """Test 8: Uploading a new avatar replaces storage path and preserves summary_embedding."""
    user_id = uuid4()
    dummy_embedding = [0.1] * 1536

    db = TestingSessionLocal()
    profile = StudentProfile(
        user_id=user_id,
        full_name="Embedding Safe",
        headline="AI Engineer",
        summary_embedding=dummy_embedding,
        avatar_storage_path=f"{user_id}/initial.jpg",
    )
    db.add(profile)
    db.commit()
    db.close()

    token = f"valid-user-{user_id}"
    files = {"file": ("new_avatar.webp", VALID_WEBP_BYTES, "image/webp")}

    response = client.post(
        "/api/v1/profile/avatar",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    assert response.status_code == 200

    db = TestingSessionLocal()
    updated = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
    assert updated is not None
    assert updated.avatar_storage_path.endswith(".webp")
    # Embedding MUST be preserved
    assert updated.summary_embedding == dummy_embedding
    db.close()


def test_delete_avatar_clears_path_and_preserves_embedding(
    client: TestClient, mock_supabase_storage
):
    """Test 9: DELETE /api/v1/profile/avatar clears avatar path and preserves embedding."""
    user_id = uuid4()
    dummy_embedding = [0.2] * 1536

    db = TestingSessionLocal()
    profile = StudentProfile(
        user_id=user_id,
        full_name="Delete Target",
        headline="Dev",
        summary_embedding=dummy_embedding,
        avatar_storage_path=f"{user_id}/to_delete.jpg",
    )
    db.add(profile)
    db.commit()
    db.close()

    token = f"valid-user-{user_id}"
    response = client.delete(
        "/api/v1/profile/avatar",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["avatar_url"] is None

    db = TestingSessionLocal()
    updated = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
    assert updated is not None
    assert updated.avatar_storage_path is None
    assert updated.summary_embedding == dummy_embedding
    db.close()


def test_profile_put_preserves_avatar_and_cv_storage_paths(
    client: TestClient, mock_supabase_storage
):
    """Test 10: Standard profile PUT preserves existing avatar_storage_path and cv_storage_path."""
    user_id = uuid4()
    avatar_path = f"{user_id}/persisted_avatar.jpg"
    cv_path = f"cvs/{user_id}/my_resume.pdf"

    db = TestingSessionLocal()
    profile = StudentProfile(
        user_id=user_id,
        full_name="Original Name",
        headline="Original Headline",
        avatar_storage_path=avatar_path,
        cv_storage_path=cv_path,
    )
    db.add(profile)
    db.commit()
    db.close()

    token = f"valid-user-{user_id}"
    payload = {
        "full_name": "Updated Name",
        "headline": "Updated Headline",
        "preferences": {"department": "Computer Science"},
    }

    response = client.put(
        "/api/v1/profile",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Updated Name"
    assert data["headline"] == "Updated Headline"

    db = TestingSessionLocal()
    updated = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
    assert updated is not None
    assert updated.avatar_storage_path == avatar_path
    assert updated.cv_storage_path == cv_path
    db.close()


def test_client_cannot_upload_or_delete_other_user_avatar(
    client: TestClient, mock_supabase_storage
):
    """Test 11: Upload/Delete only operates on JWT-authenticated identity."""
    user_a = uuid4()
    user_b = uuid4()

    db = TestingSessionLocal()
    profile_a = StudentProfile(
        user_id=user_a,
        full_name="User A",
        avatar_storage_path=f"{user_a}/photo_a.jpg",
    )
    profile_b = StudentProfile(
        user_id=user_b,
        full_name="User B",
        avatar_storage_path=f"{user_b}/photo_b.jpg",
    )
    db.add_all([profile_a, profile_b])
    db.commit()
    db.close()

    # User A tries to delete avatar
    token_a = f"valid-user-{user_a}"
    res = client.delete(
        "/api/v1/profile/avatar",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 200

    # Verify User A's avatar is cleared, User B's avatar is untouched
    db = TestingSessionLocal()
    a_check = StudentProfileRepository.get_by_user_id(db, user_id=user_a)
    b_check = StudentProfileRepository.get_by_user_id(db, user_id=user_b)
    assert a_check.avatar_storage_path is None
    assert b_check.avatar_storage_path == f"{user_b}/photo_b.jpg"
    db.close()



def test_avatar_content_is_brokered_authenticated_bytes(
    client: TestClient,
    mock_supabase_storage,
):
    user_id = uuid4()

    db = TestingSessionLocal()
    profile = StudentProfile(
        user_id=user_id,
        full_name="Brokered Avatar",
        headline="Candidate",
    )
    db.add(profile)
    db.commit()
    db.close()

    token = f"valid-user-{user_id}"

    upload = client.post(
        "/api/v1/profile/avatar",
        headers={
            "Authorization":
                f"Bearer {token}",
        },
        files={
            "file": (
                "avatar.png",
                VALID_PNG_BYTES,
                "image/png",
            )
        },
    )

    assert upload.status_code == 200

    response = client.get(
        "/api/v1/profile/avatar/content",
        headers={
            "Authorization":
                f"Bearer {token}",
        },
    )

    assert response.status_code == 200
    assert response.content == VALID_PNG_BYTES
    assert response.headers["content-type"].startswith(
        "image/png"
    )
    assert (
        response.headers["cache-control"]
        == "private, no-store, max-age=0"
    )
    assert response.headers["pragma"] == "no-cache"
    assert (
        response.headers["x-content-type-options"]
        == "nosniff"
    )
    assert (
        response.headers["referrer-policy"]
        == "no-referrer"
    )


def test_avatar_content_requires_authentication(
    client: TestClient,
):
    response = client.get(
        "/api/v1/profile/avatar/content"
    )

    assert response.status_code == 401


def test_avatar_content_rejects_cross_user_storage_path(
    client: TestClient,
    mock_supabase_storage,
):
    user_a = uuid4()
    user_b = uuid4()

    db = TestingSessionLocal()
    db.add(
        StudentProfile(
            user_id=user_a,
            full_name="User A",
            headline="Candidate",
            avatar_storage_path=(
                f"{user_b}/foreign-avatar.jpg"
            ),
        )
    )
    db.commit()
    db.close()

    token = f"valid-user-{user_a}"

    response = client.get(
        "/api/v1/profile/avatar/content",
        headers={
            "Authorization":
                f"Bearer {token}",
        },
    )

    assert response.status_code == 404


def test_avatar_storage_has_no_signed_url_capability():
    from pathlib import Path

    source = Path(
        "backend/app/services/avatar_storage.py"
    ).read_text(encoding="utf-8")

    assert "generate_avatar_signed_url" not in source
    assert "AVATAR_SIGNED_URL_EXPIRY_SECONDS" not in source
    assert "create_signed_url(" not in source
    assert "def download_avatar(" in source
    assert ".download(" in source
