"""
Unit & Repository Tests for Protected Student Profile Read & Write Endpoints.
Verifies authentication, user-scoped profile retrieval, upsert operations,
404 handling, parameter override protection, and summary_embedding invalidation rules.
"""

from datetime import date
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.db.models import (
    EducationEntry,
    ExperienceEntry,
    ProcessingJob,
    ProjectEntry,
    Skill,
    StudentProfile,
    StudentSkill,
)
from app.repositories.processing_job import ProcessingJobRepository
from app.repositories.student_profile import StudentProfileRepository
from app.services.cv_storage import CVStorageValidationError, CVStoredObject
from fastapi import HTTPException
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal

pytestmark = pytest.mark.usefixtures("mock_supabase_auth")


def _get_or_create_test_skill(db, name: str) -> Skill:
    """Reuse shared Skill taxonomy rows across StaticPool-backed tests."""
    skill = db.query(Skill).filter(Skill.name == name).one_or_none()
    if skill is None:
        skill = Skill(name=name)
        db.add(skill)
        db.flush()
    return skill


def test_unauthenticated_profile_request_returns_401(client: TestClient):
    """Test 1: Unauthenticated request to GET /api/v1/profile returns 401 UNAUTHORIZED."""
    response = client.get("/api/v1/profile")
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_authenticated_user_without_profile_returns_404(client: TestClient):
    """Test 2: Authenticated user with no database profile returns 404 NOT FOUND."""
    no_profile_user_id = uuid4()
    token = f"valid-user-{no_profile_user_id}"

    response = client.get("/api/v1/profile", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["code"] == "NOT_FOUND"
    assert "Student profile not found" in data["detail"]["error"]["message"]


def test_authenticated_user_with_profile_returns_own_profile(client: TestClient):
    """Test 3: Authenticated user with existing profile returns 200 OK with their own profile."""
    user_id = uuid4()
    db = TestingSessionLocal()

    profile = StudentProfile(
        user_id=user_id,
        full_name="Jane Student",
        headline="Software Engineering Intern Candidate",
        cv_storage_path="cvs/jane_doe_cv.pdf",
        preferences={"work_types": ["remote"], "desired_locations": ["Remote"]},
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    db.close()

    token = f"valid-user-{user_id}"
    response = client.get("/api/v1/profile", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user_id)
    assert data["full_name"] == "Jane Student"
    assert data["headline"] == "Software Engineering Intern Candidate"


def test_client_supplied_user_id_cannot_override_jwt_identity(client: TestClient):
    """Test 4: Client-supplied user_id parameter cannot override JWT sub identity."""
    authenticated_user_id = uuid4()
    other_user_id = uuid4()

    db = TestingSessionLocal()
    # Create profile for authenticated user
    auth_profile = StudentProfile(
        user_id=authenticated_user_id,
        full_name="Authenticated User",
        headline="Real Profile",
    )
    # Create profile for victim user
    other_profile = StudentProfile(
        user_id=other_user_id,
        full_name="Victim User",
        headline="Other Profile",
    )
    db.add_all([auth_profile, other_profile])
    db.commit()
    db.close()

    token = f"valid-user-{authenticated_user_id}"

    # Attempt attacker override via query parameter
    response = client.get(
        f"/api/v1/profile?user_id={other_user_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(authenticated_user_id)
    assert data["full_name"] == "Authenticated User"
    assert data["full_name"] != "Victim User"


def test_repository_scopes_query_strictly_to_user_id():
    """Test 5: StudentProfileRepository.get_by_user_id queries strictly the target user_id."""
    user_a = uuid4()
    user_b = uuid4()

    db = TestingSessionLocal()
    profile_a = StudentProfile(user_id=user_a, full_name="User A")
    profile_b = StudentProfile(user_id=user_b, full_name="User B")
    db.add_all([profile_a, profile_b])
    db.commit()

    # Query user A
    res_a = StudentProfileRepository.get_by_user_id(db, user_id=user_a)
    assert res_a is not None
    assert res_a.user_id == user_a
    assert res_a.full_name == "User A"

    # Query user B
    res_b = StudentProfileRepository.get_by_user_id(db, user_id=user_b)
    assert res_b is not None
    assert res_b.user_id == user_b
    assert res_b.full_name == "User B"

    # Query non-existent user C
    res_c = StudentProfileRepository.get_by_user_id(db, user_id=uuid4())
    assert res_c is None

    db.close()


def test_unauthenticated_put_profile_returns_401(client: TestClient):
    """Test 6: Unauthenticated PUT /api/v1/profile returns 401 UNAUTHORIZED."""
    payload = {"full_name": "New Candidate"}
    response = client.put("/api/v1/profile", json=payload)
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_put_profile_cannot_create_canonical_account(client: TestClient):
    """PUT /profile is update-only; canonical creation belongs to auth signup."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    response = client.put(
        "/api/v1/profile",
        json={
            "full_name": "Unauthorized Bootstrap",
            "preferences": {
                "account_type": "employer",
                "work_types": ["remote"],
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409

    db = TestingSessionLocal()
    try:
        profile = StudentProfileRepository.get_by_user_id(
            db,
            user_id=user_id,
        )
        assert profile is None
    finally:
        db.close()


def test_authenticated_user_can_update_existing_profile(client: TestClient):
    """Test 8: Authenticated user can update their existing profile via PUT."""
    user_id = uuid4()
    db = TestingSessionLocal()

    initial_profile = StudentProfile(
        user_id=user_id,
        full_name="Original Name",
        headline="Old Headline",
    )
    db.add(initial_profile)
    db.commit()
    db.close()

    token = f"valid-user-{user_id}"
    update_payload = {
        "full_name": "Updated Name",
        "headline": "New Lead Engineer",
        "preferences": {"work_types": ["remote"]},
    }

    response = client.put(
        "/api/v1/profile",
        json=update_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user_id)
    assert data["full_name"] == "Updated Name"
    assert data["headline"] == "New Lead Engineer"


def test_client_supplied_user_id_in_body_cannot_override_jwt(
    client: TestClient,
):
    """Client user_id cannot redirect an update to another user's profile."""
    authenticated_user_id = uuid4()
    victim_user_id = uuid4()

    db = TestingSessionLocal()
    try:
        authenticated_profile = StudentProfile(
            user_id=authenticated_user_id,
            full_name="Authenticated User",
            headline="Original Headline",
            preferences={"account_type": "intern"},
        )
        victim_profile = StudentProfile(
            user_id=victim_user_id,
            full_name="Victim Full Name",
            headline="Victim Headline",
            preferences={"account_type": "intern"},
        )
        db.add_all([authenticated_profile, victim_profile])
        db.commit()
    finally:
        db.close()

    token = f"valid-user-{authenticated_user_id}"

    malicious_payload = {
        "user_id": str(victim_user_id),
        "full_name": "Authenticated User Updated",
        "headline": "Updated Headline",
    }

    response = client.put(
        "/api/v1/profile",
        json=malicious_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["user_id"] == str(authenticated_user_id)
    assert data["user_id"] != str(victim_user_id)
    assert data["full_name"] == "Authenticated User Updated"
    assert data["headline"] == "Updated Headline"

    db_verify = TestingSessionLocal()
    try:
        authenticated = StudentProfileRepository.get_by_user_id(
            db_verify,
            authenticated_user_id,
        )
        victim = StudentProfileRepository.get_by_user_id(
            db_verify,
            victim_user_id,
        )

        assert authenticated is not None
        assert authenticated.full_name == "Authenticated User Updated"
        assert authenticated.headline == "Updated Headline"

        assert victim is not None
        assert victim.full_name == "Victim Full Name"
        assert victim.headline == "Victim Headline"
    finally:
        db_verify.close()

def test_second_user_profile_remains_unchanged_on_update(client: TestClient):
    """Test 10: Updating user A's profile leaves user B's profile completely untouched."""
    user_a = uuid4()
    user_b = uuid4()

    db = TestingSessionLocal()
    prof_a = StudentProfile(user_id=user_a, full_name="User A Original")
    prof_b = StudentProfile(user_id=user_b, full_name="User B Original")
    db.add_all([prof_a, prof_b])
    db.commit()
    db.close()

    token_a = f"valid-user-{user_a}"
    payload_a = {"full_name": "User A Modified"}

    response = client.put(
        "/api/v1/profile",
        json=payload_a,
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 200

    db_check = TestingSessionLocal()
    check_b = StudentProfileRepository.get_by_user_id(db_check, user_b)
    assert check_b is not None
    assert check_b.full_name == "User B Original"
    db_check.close()


def test_invalid_profile_input_rejected(client: TestClient):
    """Test 11: Invalid profile input (e.g. empty full_name) is rejected with 422."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    invalid_payload = {"full_name": ""}
    response = client.put(
        "/api/v1/profile",
        json=invalid_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_put_profile_persists_in_fresh_database_session(
    client: TestClient,
):
    """PUT /profile updates an existing canonical profile and commits it."""
    user_id = uuid4()

    db = TestingSessionLocal()
    try:
        db.add(
            StudentProfile(
                user_id=user_id,
                full_name="Original Student",
                headline="Original Headline",
                preferences={"account_type": "intern"},
            )
        )
        db.commit()
    finally:
        db.close()

    token = f"valid-user-{user_id}"

    response = client.put(
        "/api/v1/profile",
        json={
            "full_name": "Persisted Student",
            "headline": "Persisted Headline",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    db_fresh = TestingSessionLocal()
    try:
        persisted = StudentProfileRepository.get_by_user_id(
            db_fresh,
            user_id=user_id,
        )

        assert persisted is not None
        assert persisted.full_name == "Persisted Student"
        assert persisted.headline == "Persisted Headline"
        assert persisted.preferences["account_type"] == "intern"
    finally:
        db_fresh.close()

def test_upsert_changing_headline_clears_summary_embedding():
    """Test 13: Changing headline clears existing summary_embedding."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        prof = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="Student", headline="Old Headline"
        )
        StudentProfileRepository.set_summary_embedding(db, prof, [0.1] * 1536)
        db.commit()

        # Update headline
        updated = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="Student", headline="New Headline"
        )
        assert updated.summary_embedding is None
    finally:
        db.close()


def test_upsert_changing_preferences_clears_summary_embedding():
    """Test 14: Changing preferences clears existing summary_embedding."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        prof = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="Student", preferences={"work_types": ["remote"]}
        )
        StudentProfileRepository.set_summary_embedding(db, prof, [0.1] * 1536)
        db.commit()

        # Update preferences
        updated = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="Student", preferences={"work_types": ["onsite"]}
        )
        assert updated.summary_embedding is None
    finally:
        db.close()


def test_upsert_changing_full_name_preserves_summary_embedding():
    """Test 15: Changing full_name preserves existing summary_embedding."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        prof = StudentProfileRepository.upsert_by_user_id(db, user_id=user_id, full_name="Old Name")
        StudentProfileRepository.set_summary_embedding(db, prof, [0.1] * 1536)
        db.commit()

        updated = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="New Name"
        )
        assert updated.summary_embedding == [0.1] * len(updated.summary_embedding)
    finally:
        db.close()


def test_upsert_changing_cv_storage_path_preserves_summary_embedding():
    """Test 16: Changing cv_storage_path preserves existing summary_embedding."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        prof = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="Student", cv_storage_path="cv1.pdf"
        )
        StudentProfileRepository.set_summary_embedding(db, prof, [0.1] * 1536)
        db.commit()

        updated = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="Student", cv_storage_path="cv2.pdf"
        )
        assert updated.summary_embedding == [0.1] * len(updated.summary_embedding)
    finally:
        db.close()


def test_upsert_identical_values_preserves_summary_embedding():
    """Test 17: Upsert with identical effective values preserves existing summary_embedding."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        prof = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="Same Student", headline="Same Headline"
        )
        vec = [0.2] * 1536
        StudentProfileRepository.set_summary_embedding(db, prof, vec)
        db.commit()

        # Re-upsert with identical fields
        same = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="Same Student", headline="Same Headline"
        )
        assert same.summary_embedding == vec
    finally:
        db.close()


def test_updating_user_a_never_clears_user_b_embedding():
    """Test 18: Updating user A never clears user B embedding."""
    user_a = uuid4()
    user_b = uuid4()
    db = TestingSessionLocal()
    try:
        StudentProfileRepository.upsert_by_user_id(db, user_id=user_a, full_name="A")
        prof_b = StudentProfileRepository.upsert_by_user_id(db, user_id=user_b, full_name="B")
        vec_b = [0.3] * 1536
        StudentProfileRepository.set_summary_embedding(db, prof_b, vec_b)
        db.commit()

        # Update user A
        StudentProfileRepository.upsert_by_user_id(db, user_id=user_a, full_name="A Modified")

        check_b = StudentProfileRepository.get_by_user_id(db, user_id=user_b)
        assert check_b is not None
        assert check_b.summary_embedding == vec_b
    finally:
        db.close()


def test_endpoint_put_commits_invalidated_state_visible_in_fresh_session(client: TestClient):
    """Test 19: Endpoint PUT commits invalidated summary_embedding, visible in fresh DB session."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        prof = StudentProfileRepository.upsert_by_user_id(
            db, user_id=user_id, full_name="Initial Name", headline="Old"
        )
        StudentProfileRepository.set_summary_embedding(db, prof, [0.5] * 1536)
        db.commit()
    finally:
        db.close()

    token = f"valid-user-{user_id}"
    payload = {"full_name": "Updated Name", "headline": "New"}

    resp = client.put("/api/v1/profile", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    fresh_db = TestingSessionLocal()
    try:
        persisted = StudentProfileRepository.get_by_user_id(fresh_db, user_id=user_id)
        assert persisted is not None
        assert persisted.summary_embedding is None
    finally:
        fresh_db.close()


# CV INTAKE ENDPOINT & STRUCTURED GET /profile TESTS (20 - 30)


def test_unauthenticated_post_profile_cv_returns_401(client: TestClient):
    """Test 20: Unauthenticated POST /api/v1/profile/cv returns 401 UNAUTHORIZED."""
    files = {"file": ("resume.pdf", b"%PDF content", "application/pdf")}
    response = client.post("/api/v1/profile/cv", files=files)
    assert response.status_code == 401
    data = response.json()
    assert data["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_post_profile_cv_valid_pdf_success(client: TestClient, monkeypatch):
    """Test 21: Valid PDF upload returns 202, creates ProcessingJob, commits before enqueue."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    storage_calls = []
    fake_storage_path = f"{user_id}/resume_123.pdf"

    def mock_store(*, user_id, filename, content_type, content):
        storage_calls.append((user_id, filename, content_type, content))
        return CVStoredObject(
            storage_path=fake_storage_path,
            content_type=content_type,
            size_bytes=len(content),
        )

    enqueue_calls = []

    def mock_enqueue(job_id, user_id, storage_path, content_locale="en"):
        # Verify job is ALREADY committed and visible in fresh DB session
        db_check = TestingSessionLocal()
        try:
            job_in_db = ProcessingJobRepository.get_by_id(db_check, job_id=job_id)
            assert job_in_db is not None
            assert job_in_db.status == "queued"
            assert job_in_db.user_id == user_id
            assert job_in_db.job_type == "cv_extraction"
        finally:
            db_check.close()

        enqueue_calls.append((job_id, user_id, storage_path))
        return MagicMock(id=str(job_id))

    monkeypatch.setattr("app.api.v1.endpoints.profile.store_candidate_cv", mock_store)
    monkeypatch.setattr("app.api.v1.endpoints.profile.enqueue_cv_extraction", mock_enqueue)

    pdf_bytes = b"%PDF-1.4 mock pdf content"
    files = {"file": ("my_resume.pdf", pdf_bytes, "application/pdf")}

    response = client.post(
        "/api/v1/profile/cv",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    assert data["message"] == "CV processing enqueued successfully."
    assert data["estimated_seconds"] == 60

    assert len(storage_calls) == 1
    assert storage_calls[0][0] == user_id
    assert storage_calls[0][1] == "my_resume.pdf"
    assert storage_calls[0][2] == "application/pdf"
    assert storage_calls[0][3] == pdf_bytes

    assert len(enqueue_calls) == 1
    assert enqueue_calls[0][1] == user_id
    assert enqueue_calls[0][2] == fake_storage_path


def test_post_profile_cv_valid_docx_success(client: TestClient, monkeypatch):
    """Test 22: Valid DOCX upload returns 202 and enqueues task."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    fake_storage_path = f"{user_id}/resume_456.docx"

    monkeypatch.setattr(
        "app.api.v1.endpoints.profile.store_candidate_cv",
        lambda *, user_id, filename, content_type, content: CVStoredObject(
            storage_path=fake_storage_path,
            content_type=content_type,
            size_bytes=len(content),
        ),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.profile.enqueue_cv_extraction",
        lambda job_id, user_id, storage_path, content_locale="en": MagicMock(),
    )

    docx_bytes = b"PK\x03\x04 mock docx content"
    files = {"file": ("resume.docx", docx_bytes, docx_mime)}

    response = client.post(
        "/api/v1/profile/cv",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    assert data["message"] == "CV processing enqueued successfully."


def test_post_profile_cv_jwt_user_id_used_and_client_cannot_override(
    client: TestClient, monkeypatch
):
    """Test 23: JWT identity is authoritative; client-supplied user_id form data is ignored."""
    authenticated_user_id = uuid4()
    other_user_id = uuid4()
    token = f"valid-user-{authenticated_user_id}"

    storage_users = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.profile.store_candidate_cv",
        lambda *, user_id, filename, content_type, content: (
            storage_users.append(user_id)
            or CVStoredObject(
                storage_path=f"{user_id}/test.pdf",
                content_type=content_type,
                size_bytes=len(content),
            )
        ),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.profile.enqueue_cv_extraction",
        lambda job_id, user_id, storage_path, content_locale="en": MagicMock(),
    )

    files = {"file": ("resume.pdf", b"%PDF content", "application/pdf")}
    data = {"user_id": str(other_user_id), "job_type": "wrong_type"}

    response = client.post(
        "/api/v1/profile/cv",
        files=files,
        data=data,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 202
    assert storage_users == [authenticated_user_id]
    assert storage_users[0] != other_user_id


def test_post_profile_cv_over_10mb_rejected_with_413_payload_too_large(
    client: TestClient, monkeypatch
):
    """Test 24: Upload payload exceeding 10 MiB is rejected with HTTP 413 Payload Too Large."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    storage_called = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.profile.store_candidate_cv",
        lambda *args, **kwargs: storage_called.append(1),
    )

    oversized_bytes = b"X" * (10 * 1024 * 1024 + 10)
    files = {"file": ("huge_resume.pdf", oversized_bytes, "application/pdf")}

    response = client.post(
        "/api/v1/profile/cv",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 413
    data = response.json()
    assert data["detail"]["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert "exceeds maximum limit of 10 MB" in data["detail"]["error"]["message"]
    assert storage_called == []


def test_post_profile_cv_invalid_mime_returns_400(client: TestClient, monkeypatch):
    """Test 25: Storage validation error (e.g. invalid MIME/extension) returns HTTP 400."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    def mock_store_fail(*args, **kwargs):
        raise CVStorageValidationError("Unsupported content type 'image/png'")

    monkeypatch.setattr("app.api.v1.endpoints.profile.store_candidate_cv", mock_store_fail)

    files = {"file": ("picture.png", b"png bytes", "image/png")}

    response = client.post(
        "/api/v1/profile/cv",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["code"] == "BAD_REQUEST"
    assert "Unsupported content type" in data["detail"]["error"]["message"]


def test_post_profile_cv_enqueue_failure_marks_job_failed_and_returns_503(
    client: TestClient, monkeypatch
):
    """Test 26: Redis/RQ enqueue failure updates committed job to failed and returns HTTP 503."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    monkeypatch.setattr(
        "app.api.v1.endpoints.profile.store_candidate_cv",
        lambda *, user_id, filename, content_type, content: CVStoredObject(
            storage_path=f"{user_id}/resume.pdf",
            content_type=content_type,
            size_bytes=len(content),
        ),
    )

    def mock_failing_enqueue(*args, **kwargs):
        raise ConnectionError("Redis connection refused on port 6379")

    monkeypatch.setattr("app.api.v1.endpoints.profile.enqueue_cv_extraction", mock_failing_enqueue)

    files = {"file": ("resume.pdf", b"%PDF content", "application/pdf")}

    response = client.post(
        "/api/v1/profile/cv",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    data = response.json()
    assert data["detail"]["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert "Failed to enqueue CV extraction job" in data["detail"]["error"]["message"]

    # Verify in fresh DB session that job exists, is marked failed, and has error message
    db_check = TestingSessionLocal()
    try:
        jobs = (
            db_check.query(ProcessingJob).filter_by(user_id=user_id, job_type="cv_extraction").all()
        )
        assert len(jobs) == 1
        persisted_job = jobs[0]
        assert persisted_job.status == "failed"
        assert persisted_job.progress_percent == 100
        assert persisted_job.error == "Failed to enqueue CV extraction job."
        assert "Redis connection refused" not in (persisted_job.error or "")
    finally:
        db_check.close()


def test_post_profile_cv_no_parsing_llm_or_embedding_in_request_path(
    client: TestClient, monkeypatch
):
    """Test 27: Request path does NOT invoke parser, LLM extraction, or embedding generation."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    forbidden_calls = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.profile.store_candidate_cv",
        lambda *, user_id, filename, content_type, content: CVStoredObject(
            storage_path=f"{user_id}/resume.pdf",
            content_type=content_type,
            size_bytes=len(content),
        ),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.profile.enqueue_cv_extraction",
        lambda job_id, user_id, storage_path, content_locale="en": MagicMock(),
    )

    # Monkeypatch parser / LLM / embeddings if imported anywhere in endpoint module
    monkeypatch.setattr(
        "app.services.cv_parser.extract_cv_text",
        lambda *args, **kwargs: forbidden_calls.append("parser"),
    )
    monkeypatch.setattr(
        "app.services.cv_profile_extraction.extract_structured_candidate_profile",
        lambda *args, **kwargs: forbidden_calls.append("llm"),
    )
    monkeypatch.setattr(
        "app.services.candidate_embedding.generate_and_persist_candidate_embedding",
        lambda *args, **kwargs: forbidden_calls.append("embedding"),
    )

    files = {"file": ("resume.pdf", b"%PDF content", "application/pdf")}
    response = client.post(
        "/api/v1/profile/cv",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 202
    assert forbidden_calls == []


def test_get_profile_returns_structured_data(client: TestClient):
    """Test 28: GET /profile returns complete structured skills, education, experience, projects."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            user_id=user_id,
            full_name="Sarah Developer",
            headline="Full Stack Engineer",
            preferences={"work_types": ["remote"], "desired_locations": ["London"]},
        )
        db.add(profile)
        db.flush()

        skill_py = _get_or_create_test_skill(db, "Python")
        skill_fastapi = _get_or_create_test_skill(db, "FastAPI")
        db.add_all([skill_py, skill_fastapi])
        db.flush()

        db.add(
            StudentSkill(student_id=profile.id, skill_id=skill_py.id, proficiency_level="advanced")
        )
        db.add(
            StudentSkill(
                student_id=profile.id, skill_id=skill_fastapi.id, proficiency_level="intermediate"
            )
        )

        db.add(
            EducationEntry(
                student_id=profile.id,
                institution="Oxford University",
                degree="B.Sc. Computer Science",
                start_year=2021,
                end_year=2024,
            )
        )
        db.add(
            ExperienceEntry(
                student_id=profile.id,
                company="TechCorp",
                role="Backend Intern",
                description="Built high-performance microservices.",
                start_date=date(2023, 6, 1),
                end_date=date(2023, 9, 1),
            )
        )
        db.add(
            ProjectEntry(
                student_id=profile.id,
                title="AI Career Matcher",
                tech_stack=["Python", "FastAPI", "PostgreSQL"],
                description="Matching system for internships.",
            )
        )
        db.commit()
    finally:
        db.close()

    token = f"valid-user-{user_id}"
    response = client.get("/api/v1/profile", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Sarah Developer"
    assert data["headline"] == "Full Stack Engineer"
    assert data["skills"] == ["FastAPI", "Python"]  # Deterministic alphabetical ordering

    assert len(data["education"]) == 1
    assert data["education"][0]["institution"] == "Oxford University"
    assert data["education"][0]["degree"] == "B.Sc. Computer Science"
    assert data["education"][0]["start_year"] == 2021
    assert data["education"][0]["end_year"] == 2024

    assert len(data["experience"]) == 1
    assert data["experience"][0]["company"] == "TechCorp"
    assert data["experience"][0]["role"] == "Backend Intern"
    assert data["experience"][0]["description"] == "Built high-performance microservices."
    assert data["experience"][0]["start_date"] == "2023-06-01"
    assert data["experience"][0]["end_date"] == "2023-09-01"

    assert len(data["projects"]) == 1
    assert data["projects"][0]["title"] == "AI Career Matcher"
    assert data["projects"][0]["tech_stack"] == ["Python", "FastAPI", "PostgreSQL"]

    assert data["preferences"] == {"work_types": ["remote"], "desired_locations": ["London"]}

    # Security check: internal summary_embedding and raw text must NOT be exposed
    assert "summary_embedding" not in data
    assert "raw_cv_text" not in data


def test_get_profile_remains_user_scoped_with_structured_data(client: TestClient):
    """Test 29: GET /profile never leaks user B's structured entities to user A."""
    user_a = uuid4()
    user_b = uuid4()

    db = TestingSessionLocal()
    try:
        prof_a = StudentProfile(user_id=user_a, full_name="User A")
        prof_b = StudentProfile(user_id=user_b, full_name="User B")
        db.add_all([prof_a, prof_b])
        db.flush()

        skill_a = _get_or_create_test_skill(db, "UserASkill")
        skill_b = _get_or_create_test_skill(db, "UserBSkill")
        db.add_all([skill_a, skill_b])
        db.flush()

        db.add(StudentSkill(student_id=prof_a.id, skill_id=skill_a.id))
        db.add(StudentSkill(student_id=prof_b.id, skill_id=skill_b.id))

        db.add(EducationEntry(student_id=prof_a.id, institution="University A", degree="Degree A"))
        db.add(EducationEntry(student_id=prof_b.id, institution="University B", degree="Degree B"))
        db.commit()
    finally:
        db.close()

    token_a = f"valid-user-{user_a}"
    response_a = client.get("/api/v1/profile", headers={"Authorization": f"Bearer {token_a}"})
    assert response_a.status_code == 200
    data_a = response_a.json()
    assert data_a["full_name"] == "User A"
    assert data_a["skills"] == ["UserASkill"]
    assert len(data_a["education"]) == 1
    assert data_a["education"][0]["institution"] == "University A"


def test_post_profile_cv_fake_pdf_signature_rejected_with_400(client: TestClient, monkeypatch):
    """Test 36: Uploading fake PDF bytes with valid MIME/ext returns HTTP 400."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    files = {"file": ("resume.pdf", b"fake non-pdf bytes", "application/pdf")}

    response = client.post(
        "/api/v1/profile/cv",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["code"] == "BAD_REQUEST"
    assert "File signature does not match expected PDF format" in data["detail"]["error"]["message"]

    # Verify no job was created
    db = TestingSessionLocal()
    try:
        jobs = db.query(ProcessingJob).filter_by(user_id=user_id, job_type="cv_extraction").all()
        assert len(jobs) == 0
    finally:
        db.close()


def test_post_profile_cv_fake_docx_signature_rejected_with_400(client: TestClient, monkeypatch):
    """Test 37: Uploading fake DOCX bytes with valid MIME/ext returns HTTP 400."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    files = {"file": ("resume.docx", b"fake non-docx bytes", docx_mime)}

    response = client.post(
        "/api/v1/profile/cv",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"]["code"] == "BAD_REQUEST"
    assert (
        "File signature does not match expected DOCX format" in data["detail"]["error"]["message"]
    )

    # Verify no job was created
    db = TestingSessionLocal()
    try:
        jobs = db.query(ProcessingJob).filter_by(user_id=user_id, job_type="cv_extraction").all()
        assert len(jobs) == 0
    finally:
        db.close()


def test_post_profile_cv_rate_limited_returns_429(client: TestClient, monkeypatch):
    """
    Test 38: Rate limit rejection returns HTTP 429 and aborts before
    storage/job creation.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    def failing_rate_limit(*, user_id, scope):
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many requests. Please retry later.",
                    "details": {"retry_after_seconds": 600},
                    "timestamp": "2026-08-14T00:00:00Z",
                }
            },
            headers={"Retry-After": "600"},
        )

    monkeypatch.setattr("app.api.v1.endpoints.profile.enforce_rate_limit", failing_rate_limit)

    storage_called = []
    monkeypatch.setattr(
        "app.api.v1.endpoints.profile.store_candidate_cv",
        lambda *args, **kwargs: storage_called.append(1),
    )

    files = {"file": ("resume.pdf", b"%PDF-1.4 test", "application/pdf")}

    response = client.post(
        "/api/v1/profile/cv",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 429
    assert response.headers.get("retry-after") == "600"
    data = response.json()
    assert data["detail"]["error"]["code"] == "RATE_LIMITED"
    assert storage_called == []

    # Verify no job was created
    db = TestingSessionLocal()
    try:
        jobs = db.query(ProcessingJob).filter_by(user_id=user_id, job_type="cv_extraction").all()
        assert len(jobs) == 0
    finally:
        db.close()


def test_profile_update_cannot_change_existing_account_type(client: TestClient):
    """Existing canonical account role cannot be changed through PUT /profile."""
    user_id = uuid4()

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            user_id=user_id,
            full_name="Existing Student",
            preferences={
                "account_type": "intern",
                "work_types": ["remote"],
            },
        )
        db.add(profile)
        db.commit()
    finally:
        db.close()

    token = f"valid-user-{user_id}"
    response = client.put(
        "/api/v1/profile",
        json={
            "full_name": "Existing Student",
            "preferences": {
                "account_type": "employer",
                "work_types": ["onsite"],
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["preferences"]["account_type"] == "intern"
    assert data["preferences"]["work_types"] == ["onsite"]

    db_verify = TestingSessionLocal()
    try:
        persisted = StudentProfileRepository.get_by_user_id(
            db_verify,
            user_id=user_id,
        )
        assert persisted is not None
        assert persisted.preferences["account_type"] == "intern"
        assert persisted.preferences["work_types"] == ["onsite"]
    finally:
        db_verify.close()


def test_profile_update_preserves_existing_account_type_when_preferences_omit_it(
    client: TestClient,
):
    """Updating unrelated preferences cannot erase the canonical account role."""
    user_id = uuid4()

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            user_id=user_id,
            full_name="Existing Employer",
            preferences={
                "account_type": "employer",
                "work_types": ["hybrid"],
            },
        )
        db.add(profile)
        db.commit()
    finally:
        db.close()

    token = f"valid-user-{user_id}"
    response = client.put(
        "/api/v1/profile",
        json={
            "full_name": "Existing Employer",
            "preferences": {
                "work_types": ["remote"],
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["preferences"]["account_type"] == "employer"
    assert data["preferences"]["work_types"] == ["remote"]


def test_profile_update_cannot_assign_role_to_legacy_roleless_profile(
    client: TestClient,
):
    """A legacy roleless profile cannot self-promote through profile editing."""
    user_id = uuid4()

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            user_id=user_id,
            full_name="Legacy User",
            preferences={"work_types": ["remote"]},
        )
        db.add(profile)
        db.commit()
    finally:
        db.close()

    token = f"valid-user-{user_id}"
    response = client.put(
        "/api/v1/profile",
        json={
            "full_name": "Legacy User",
            "preferences": {
                "account_type": "employer",
                "work_types": ["hybrid"],
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "account_type" not in data["preferences"]
    assert data["preferences"]["work_types"] == ["hybrid"]
