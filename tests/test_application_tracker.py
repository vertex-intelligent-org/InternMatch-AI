"""
Unit & Integration Tests for Application Tracker (Gate 2.29).
Tests GET /api/v1/applications and PATCH /api/v1/applications/{id}/status,
tenant isolation in SQL, applied_date persistence semantics, notes handling
(omitted vs explicit null vs string), deleted internship historical retention,
and Gate 2.28 regeneration safety.
"""

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from app.db.models import (
    Application,
    ApplicationStatusEvent,
    EducationEntry,
    ExperienceEntry,
    InternshipListing,
    Match,
    ProcessingJob,
    ProjectEntry,
    Skill,
    StudentProfile,
    StudentSkill,
)
from app.repositories.application import ApplicationRepository
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal

pytestmark = pytest.mark.usefixtures("mock_supabase_auth")


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure all related tables are cleared before and after each test."""
    db = TestingSessionLocal()
    try:
        db.query(ApplicationStatusEvent).delete()
        db.query(Application).delete()
        db.query(Match).delete()
        db.query(ProcessingJob).delete()
        db.query(StudentSkill).delete()
        db.query(EducationEntry).delete()
        db.query(ExperienceEntry).delete()
        db.query(ProjectEntry).delete()
        db.query(StudentProfile).delete()
        db.query(Skill).delete()
        db.query(InternshipListing).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = TestingSessionLocal()
    try:
        db.query(ApplicationStatusEvent).delete()
        db.query(Application).delete()
        db.query(Match).delete()
        db.query(ProcessingJob).delete()
        db.query(StudentSkill).delete()
        db.query(EducationEntry).delete()
        db.query(ExperienceEntry).delete()
        db.query(ProjectEntry).delete()
        db.query(StudentProfile).delete()
        db.query(Skill).delete()
        db.query(InternshipListing).delete()
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1. GET /applications TESTS (1 - 7)
# ---------------------------------------------------------------------------


def test_unauthenticated_get_applications_rejected(client: TestClient):
    """Test 1: Unauthenticated GET /applications returns 401."""
    response = client.get("/api/v1/applications")
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_empty_tracker_returns_empty_list(client: TestClient):
    """Test 2: Authenticated user with no applications gets empty list."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    response = client.get(
        "/api/v1/applications",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"applications": []}


def test_owner_sees_own_applications_with_joined_internship(
    client: TestClient,
):
    """Test 3: Owner retrieves applications with company_name and job_title."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Jane Candidate")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Backend Intern",
            company="AlphaCorp",
            location="Remote",
            work_type="remote",
            description="API development.",
        )
        db.add(listing)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            status="saved",
            generated_cover_letter="Cover letter text",
            notes="Interested in their backend team",
        )
        db.add(app)
        db.commit()
        app_id = app.id
        listing_id = listing.id
    finally:
        db.close()

    response = client.get(
        "/api/v1/applications",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["applications"]) == 1
    item = data["applications"][0]
    assert item["id"] == str(app_id)
    assert item["internship_id"] == str(listing_id)
    assert item["company_name"] == "AlphaCorp"
    assert item["job_title"] == "Backend Intern"
    assert item["status"] == "saved"
    assert item["generated_cover_letter"] == "Cover letter text"
    assert item["applied_date"] is None
    assert item["notes"] == "Interested in their backend team"


def test_tenant_isolation_never_exposes_other_user_applications(
    client: TestClient,
):
    """Test 4: User B cannot see User A's application tracker records."""
    user_a = uuid4()
    user_b = uuid4()
    token_b = f"valid-user-{user_b}"

    db = TestingSessionLocal()
    try:
        prof_a = StudentProfile(id=uuid4(), user_id=user_a, full_name="Candidate A")
        db.add(prof_a)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Dev",
            company="Alpha",
            location="Remote",
            work_type="remote",
            description="Dev.",
        )
        db.add(listing)
        db.flush()

        app_a = Application(
            id=uuid4(),
            student_id=prof_a.id,
            internship_id=listing.id,
            status="applied",
        )
        db.add(app_a)
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/api/v1/applications",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 200
    assert response.json() == {"applications": []}


def test_historical_record_with_deleted_internship_preserved(
    client: TestClient,
):
    """
    Test 5 & 6: Application with internship_id=None (deleted listing)
    remains visible with internship_id=null, company_name=null, job_title=null.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Jane Candidate")
        db.add(profile)
        db.flush()

        # Historical application whose internship listing was archived/removed
        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,  # ON DELETE SET NULL
            status="interviewing",
            generated_cover_letter="Historical cover letter",
            applied_date=date(2026, 8, 1),
            notes="Interview completed",
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    response = client.get(
        "/api/v1/applications",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["applications"]) == 1
    item = data["applications"][0]
    assert item["id"] == str(app_id)
    assert item["internship_id"] is None
    assert item["company_name"] is None
    assert item["job_title"] is None
    assert item["status"] == "interviewing"
    assert item["generated_cover_letter"] == "Historical cover letter"
    assert item["applied_date"] == "2026-08-01"
    assert item["notes"] == "Interview completed"


def test_application_serialization_excludes_internal_fields(
    client: TestClient,
):
    """Test 7: Response does not leak student_id or internal timestamps."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="saved",
        )
        db.add(app)
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/api/v1/applications",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    item = response.json()["applications"][0]
    assert "student_id" not in item
    assert "created_at" not in item
    assert "updated_at" not in item


# ---------------------------------------------------------------------------
# 2. PATCH /applications/{id}/status TESTS (8 - 20)
# ---------------------------------------------------------------------------


def test_unauthenticated_patch_status_rejected(client: TestClient):
    """Test 8: Unauthenticated PATCH /applications/{id}/status returns 401."""
    response = client.patch(
        f"/api/v1/applications/{uuid4()}/status",
        json={"status": "applied"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_nonexistent_application_returns_404(client: TestClient):
    """Test 9: Requesting PATCH on nonexistent application returns 404."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    response = client.patch(
        f"/api/v1/applications/{uuid4()}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "applied"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found."


def test_other_user_application_returns_404_tenant_isolation(
    client: TestClient,
):
    """Test 10: Attempting to PATCH another user's application returns 404."""
    user_a = uuid4()
    user_b = uuid4()
    token_b = f"valid-user-{user_b}"

    db = TestingSessionLocal()
    try:
        prof_a = StudentProfile(id=uuid4(), user_id=user_a, full_name="Candidate A")
        db.add(prof_a)
        db.flush()

        app_a = Application(
            id=uuid4(),
            student_id=prof_a.id,
            internship_id=None,
            status="saved",
        )
        db.add(app_a)
        db.commit()
        target_id = app_a.id
    finally:
        db.close()

    response = client.patch(
        f"/api/v1/applications/{target_id}/status",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"status": "applied"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found."


def test_invalid_status_rejected_with_422(client: TestClient):
    """Test 11: Invalid status string returns 422 validation error."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    response = client.patch(
        f"/api/v1/applications/{uuid4()}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "in_progress"},  # Invalid status
    )
    assert response.status_code == 422


@pytest.mark.parametrize("valid_status", ["saved", "applied"])
def test_owner_can_update_candidate_allowed_status(client: TestClient, valid_status):
    """Test 12: Owner can update to allowed candidate statuses (saved, applied)."""

    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="saved",
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    response = client.patch(
        f"/api/v1/applications/{app_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": valid_status},
    )
    assert response.status_code == 200
    assert response.json()["status"] == valid_status


@pytest.mark.parametrize(
    "forbidden_status", ["interviewing", "rejected", "accepted"]
)
def test_candidate_cannot_self_set_employer_status(
    client: TestClient, forbidden_status
):
    """
    Test 12b: Candidate cannot manually set status to
    interviewing, accepted, or rejected (returns 403).
    """

    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="applied",
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    response = client.patch(
        f"/api/v1/applications/{app_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": forbidden_status},
    )
    assert response.status_code == 403
    assert "managed by the employer" in response.json()["detail"]


def test_notes_omitted_preserves_existing_notes(client: TestClient):
    """Test 13: Omitting 'notes' field in PATCH payload preserves existing notes."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="saved",
            notes="Important notes to keep",
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    response = client.patch(
        f"/api/v1/applications/{app_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "applied"},  # 'notes' omitted
    )
    assert response.status_code == 200
    assert response.json()["notes"] == "Important notes to keep"



def test_notes_string_updates_notes(client: TestClient):
    """Test 14: Supplying string 'notes' updates the notes in database."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="saved",
            notes="Old notes",
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    response = client.patch(
        f"/api/v1/applications/{app_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "saved", "notes": "Brand new notes"},
    )
    assert response.status_code == 200
    assert response.json()["notes"] == "Brand new notes"


def test_notes_explicit_null_clears_notes(client: TestClient):
    """Test 15: Explicitly passing 'notes': null clears existing notes."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="saved",
            notes="Notes to be cleared",
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    response = client.patch(
        f"/api/v1/applications/{app_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "saved", "notes": None},  # Explicit null
    )
    assert response.status_code == 200
    assert response.json()["notes"] is None


def test_first_transition_to_applied_sets_applied_date(client: TestClient):
    """Test 16: First transition to 'applied' sets applied_date to UTC today."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="saved",
            applied_date=None,
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    today_str = datetime.now(timezone.utc).date().isoformat()

    response = client.patch(
        f"/api/v1/applications/{app_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "applied"},
    )
    assert response.status_code == 200
    assert response.json()["applied_date"] == today_str


def test_repeat_applied_preserves_original_applied_date(client: TestClient):
    """Test 17: Repeat PATCH to 'applied' preserves existing applied_date."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    original_date = date(2026, 7, 15)

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="applied",
            applied_date=original_date,
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    response = client.patch(
        f"/api/v1/applications/{app_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "applied"},
    )
    assert response.status_code == 200
    assert response.json()["applied_date"] == "2026-07-15"


def test_later_status_transitions_preserve_applied_date(client: TestClient):
    """Test 18: Transitions to interviewing/rejected/accepted preserve applied_date."""
    original_date = date(2026, 7, 20)

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=uuid4(), full_name="Candidate")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="applied",
            applied_date=original_date,
        )
        db.add(app)
        db.commit()

        # Update status via repository to interviewing
        ApplicationRepository.update_status(db=db, application=app, status="interviewing")
        db.commit()
        db.refresh(app)
        assert app.applied_date == original_date

        # Update status via repository to accepted
        ApplicationRepository.update_status(db=db, application=app, status="accepted")
        db.commit()
        db.refresh(app)
        assert app.applied_date == original_date
    finally:
        db.close()


def test_direct_saved_to_interviewing_leaves_applied_date_null():
    """Test 19: Direct transition saved -> interviewing leaves applied_date None."""
    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=uuid4(), full_name="Candidate")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="saved",
            applied_date=None,
        )
        db.add(app)
        db.commit()

        ApplicationRepository.update_status(db=db, application=app, status="interviewing")
        db.commit()
        db.refresh(app)
        assert app.applied_date is None
    finally:
        db.close()



def test_successful_patch_returns_full_updated_contract_schema(
    client: TestClient,
):
    """Test 20: Successful PATCH returns all contract-specified fields."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            listing_source="curated",
            publication_status="published",
            title="Frontend Intern",
            company="BetaTech",
            location="Remote",
            work_type="remote",
            description="React dev.",
        )
        db.add(listing)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            status="saved",
            generated_cover_letter="My cover letter",
        )
        db.add(app)
        db.commit()
        app_id = app.id
        listing_id = listing.id
    finally:
        db.close()

    response = client.patch(
        f"/api/v1/applications/{app_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "applied", "notes": "Applied via portal"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(app_id)
    assert data["internship_id"] == str(listing_id)
    assert data["company_name"] == "BetaTech"
    assert data["job_title"] == "Frontend Intern"
    assert data["status"] == "applied"
    assert data["generated_cover_letter"] == "My cover letter"
    assert data["applied_date"] is not None
    assert data["notes"] == "Applied via portal"


# ---------------------------------------------------------------------------
# 3. GATE 2.28 REGENERATION REGRESSION SAFETY (21)
# ---------------------------------------------------------------------------


def test_gate_2_28_regeneration_preserves_status_notes_applied_date():
    """
    Test 21: Gate 2.28 cover-letter regeneration updates generated_cover_letter
    only and strictly preserves status, notes, applied_date, id, and created_at.
    """
    db = TestingSessionLocal()
    try:
        student_id = uuid4()
        internship_id = uuid4()

        profile = StudentProfile(id=student_id, user_id=uuid4(), full_name="Candidate")
        db.add(profile)
        listing = InternshipListing(
            id=internship_id,
            title="Dev",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
        )
        db.add(listing)
        db.flush()

        original_applied_date = date(2026, 8, 10)
        existing_app = Application(
            id=uuid4(),
            student_id=student_id,
            internship_id=internship_id,
            status="interviewing",
            generated_cover_letter="Version 1 cover letter",
            applied_date=original_applied_date,
            notes="Second round next Tuesday",
        )
        db.add(existing_app)
        db.commit()
        orig_id = existing_app.id
        orig_created_at = existing_app.created_at

        # Call Gate 2.28 repository upsert
        updated_app = ApplicationRepository.upsert_generated_cover_letter(
            db=db,
            student_id=student_id,
            internship_id=internship_id,
            generated_cover_letter="Version 2 regenerated cover letter",
        )
        db.commit()

        assert updated_app.id == orig_id
        assert updated_app.created_at == orig_created_at
        assert updated_app.status == "interviewing"  # PRESERVED
        assert updated_app.applied_date == original_applied_date  # PRESERVED
        assert updated_app.notes == "Second round next Tuesday"  # PRESERVED
        assert updated_app.generated_cover_letter == "Version 2 regenerated cover letter"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 3. GATE 2.38F-C4C-A DETAIL ENDPOINT & TIMELINE EVENT TESTS (22 - 34)
# ---------------------------------------------------------------------------


def test_unauthenticated_detail_request_rejected(client: TestClient):
    """Test 22: Unauthenticated GET /api/v1/applications/{id} returns 401."""
    random_id = uuid4()
    response = client.get(f"/api/v1/applications/{random_id}")
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_owner_can_fetch_own_application_detail(client: TestClient):
    """Test 23: Owner can fetch detail of their own application with 200 OK."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate A")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            title="Frontend Engineering Intern",
            company="Tech Corp",
            location="San Francisco, CA",
            work_type="hybrid",
            description="React Native engineering.",
        )
        db.add(listing)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            status="saved",
            generated_cover_letter="My personalized cover letter.",
            notes="Follow up next week",
        )
        db.add(app)
        db.commit()
        app_id = app.id
        listing_id = listing.id
    finally:
        db.close()

    response = client.get(
        f"/api/v1/applications/{app_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(app_id)
    assert data["internship_id"] == str(listing_id)
    assert data["company_name"] == "Tech Corp"
    assert data["job_title"] == "Frontend Engineering Intern"
    assert data["status"] == "saved"
    assert data["generated_cover_letter"] == "My personalized cover letter."
    assert data["notes"] == "Follow up next week"
    assert "created_at" in data
    assert "updated_at" in data
    assert data["timeline"] == []


def test_other_user_cannot_fetch_application_detail(client: TestClient):
    """
    Test 24: Cross-tenant isolation — User B receives 404 when requesting
    User A's application.
    """
    user_a = uuid4()
    user_b = uuid4()
    token_b = f"valid-user-{user_b}"

    db = TestingSessionLocal()
    try:
        profile_a = StudentProfile(id=uuid4(), user_id=user_a, full_name="User A")
        profile_b = StudentProfile(id=uuid4(), user_id=user_b, full_name="User B")
        db.add_all([profile_a, profile_b])
        db.flush()

        app_a = Application(
            id=uuid4(),
            student_id=profile_a.id,
            internship_id=None,
            status="applied",
            generated_cover_letter="User A cover letter",
        )
        db.add(app_a)
        db.commit()
        app_a_id = app_a.id
    finally:
        db.close()

    response = client.get(
        f"/api/v1/applications/{app_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found."


def test_status_event_cascade_delete():
    """Test 31: Deleting an Application cascades and deletes its ApplicationStatusEvent records."""
    db = TestingSessionLocal()
    try:
        student_id = uuid4()
        profile = StudentProfile(id=student_id, user_id=uuid4(), full_name="User")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=student_id,
            internship_id=None,
            status="applied",
        )
        db.add(app)
        db.flush()

        event = ApplicationStatusEvent(
            id=uuid4(),
            application_id=app.id,
            status="applied",
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(event)
        db.commit()
        app_id = app.id

        # Verify event exists
        assert len(ApplicationRepository.list_events_for_application(db, app_id)) == 1

        # Delete Application
        db.delete(app)
        db.commit()

        # Verify event was cascade deleted
        assert len(ApplicationRepository.list_events_for_application(db, app_id)) == 0
    finally:
        db.close()


def test_repeated_patch_with_same_status_does_not_append_duplicate_event(
    client: TestClient,
):
    """Test 27: Repeating PATCH with identical status does NOT append duplicate timeline events."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="User")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="saved",
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    # First PATCH: transition to applied
    client.patch(
        f"/api/v1/applications/{app_id}/status",
        json={"status": "applied"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Second PATCH: repeated applied
    client.patch(
        f"/api/v1/applications/{app_id}/status",
        json={"status": "applied"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Third PATCH: repeated applied with notes
    client.patch(
        f"/api/v1/applications/{app_id}/status",
        json={"status": "applied", "notes": "Updated note without changing status"},
        headers={"Authorization": f"Bearer {token}"},
    )

    detail_resp = client.get(
        f"/api/v1/applications/{app_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["status"] == "applied"
    assert data["notes"] == "Updated note without changing status"
    assert len(data["timeline"]) == 1  # Exactly ONE event, not 3


def test_timeline_events_returned_in_chronological_order():
    """Test 29: Status events are listed in strict ascending chronological order."""
    db = TestingSessionLocal()
    try:
        student_id = uuid4()
        profile = StudentProfile(id=student_id, user_id=uuid4(), full_name="User")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=student_id,
            internship_id=None,
            status="accepted",
        )
        db.add(app)
        db.flush()

        t1 = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 8, 5, 14, 30, tzinfo=timezone.utc)
        t3 = datetime(2026, 8, 12, 9, 15, tzinfo=timezone.utc)

        event1 = ApplicationStatusEvent(
            id=uuid4(),
            application_id=app.id,
            status="applied",
            occurred_at=t1,
        )
        event2 = ApplicationStatusEvent(
            id=uuid4(),
            application_id=app.id,
            status="interviewing",
            occurred_at=t2,
        )
        event3 = ApplicationStatusEvent(
            id=uuid4(),
            application_id=app.id,
            status="accepted",
            occurred_at=t3,
        )
        # Add out of order to verify sorting query
        db.add_all([event3, event1, event2])
        db.commit()

        events = ApplicationRepository.list_events_for_application(
            db=db, application_id=app.id
        )
        assert len(events) == 3
        assert events[0].status == "applied"
        assert events[1].status == "interviewing"
        assert events[2].status == "accepted"

        # Verify ascending chronological order
        occurred_times = [
            e.occurred_at.replace(tzinfo=timezone.utc)
            if e.occurred_at.tzinfo is None
            else e.occurred_at
            for e in events
        ]
        assert occurred_times == [t1, t2, t3]
    finally:
        db.close()


def test_candidate_submit_appends_exactly_one_applied_event_and_persists_occurred_at(
    client: TestClient,
):
    """
    EMP-MVP3 regression:
    Candidate authority is saved -> applied only.
    Explicit submit appends exactly one persisted applied event.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Timeline Candidate",
        )
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="saved",
            notes=None,
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    submit_response = client.post(
        f"/api/v1/applications/{app_id}/submit",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert submit_response.status_code == 200
    assert submit_response.json()["status"] == "applied"

    detail_response = client.get(
        f"/api/v1/applications/{app_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert detail_response.status_code == 200

    data = detail_response.json()

    assert data["status"] == "applied"
    assert len(data["timeline"]) == 1
    assert data["timeline"][0]["status"] == "applied"
    assert data["timeline"][0]["occurred_at"] is not None

    second_submit = client.post(
        f"/api/v1/applications/{app_id}/submit",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert second_submit.status_code in (400, 409)

    detail_after_second_submit = client.get(
        f"/api/v1/applications/{app_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert detail_after_second_submit.status_code == 200

    timeline_after_second_submit = detail_after_second_submit.json()["timeline"]

    assert len(timeline_after_second_submit) == 1
    assert timeline_after_second_submit[0]["status"] == "applied"


def test_legacy_application_with_no_events_returns_empty_timeline(
    client: TestClient,
):
    """
    Test 30: A legacy application created before the status event system returns
    an empty timeline array (no synthesized or fabricated timestamps).
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="User")
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="interviewing",
            applied_date=date(2026, 7, 20),
            notes="Legacy application from before timeline was enabled",
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    response = client.get(
        f"/api/v1/applications/{app_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "interviewing"
    assert data["applied_date"] == "2026-07-20"
    assert data["notes"] == "Legacy application from before timeline was enabled"
    assert data["timeline"] == []  # Empty, genuine


def test_nonexistent_application_detail_returns_404(client: TestClient):
    """Test 25: Requesting nonexistent application UUID returns 404."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="User")
        db.add(profile)
        db.commit()
    finally:
        db.close()

    response = client.get(
        f"/api/v1/applications/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found."

def test_candidate_submit_sets_applied_date_and_notes_update_preserves_it(
    client: TestClient,
):
    """
    EMP-MVP3 regression:
    explicit Candidate submit sets applied_date exactly once, and a later
    notes-only update does not replace the original application timestamp.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Applied Date Candidate",
        )
        db.add(profile)
        db.flush()

        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=None,
            status="saved",
            notes=None,
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    submit_response = client.post(
        f"/api/v1/applications/{app_id}/submit",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert submit_response.status_code == 200
    assert submit_response.json()["status"] == "applied"
    assert submit_response.json()["applied_date"] is not None

    first_detail_response = client.get(
        f"/api/v1/applications/{app_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert first_detail_response.status_code == 200

    first_detail = first_detail_response.json()

    assert first_detail["status"] == "applied"
    assert first_detail["applied_date"] is not None

    original_applied_date = first_detail["applied_date"]

    notes_response = client.patch(
        f"/api/v1/applications/{app_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "status": "applied",
            "notes": "Candidate follow-up note",
        },
    )

    assert notes_response.status_code == 200
    assert notes_response.json()["status"] == "applied"
    assert notes_response.json()["applied_date"] == original_applied_date

    final_detail_response = client.get(
        f"/api/v1/applications/{app_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert final_detail_response.status_code == 200

    final_detail = final_detail_response.json()

    assert final_detail["applied_date"] == original_applied_date
    assert final_detail["notes"] == "Candidate follow-up note"

    applied_events = [
        event
        for event in final_detail["timeline"]
        if event["status"] == "applied"
    ]

    assert len(applied_events) == 1

def test_candidate_submit_rejects_active_legacy_unknown_listing(
    client: TestClient,
):
    """
    A4 security regression:
    active alone is not sufficient authority for Candidate submission.
    legacy_unknown listings must remain non-public and non-submittable.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Boundary Candidate",
        )
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            listing_source="legacy_unknown",
            title="Hidden Legacy Internship",
            company="Unknown Source",
            location="Remote",
            work_type="remote",
            description="Must not accept new candidate submissions.",
            required_skills=[],
            preferred_skills=[],
            language="English",
            publication_status="published",
            is_active=True,
        )
        db.add(listing)
        db.flush()

        application = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            status="saved",
            notes=None,
        )
        db.add(application)
        db.commit()

        application_id = application.id
    finally:
        db.close()

    response = client.post(
        f"/api/v1/applications/{application_id}/submit",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "This internship opportunity is not currently "
        "available for new submissions."
    )

    db = TestingSessionLocal()
    try:
        application = db.get(Application, application_id)
        assert application is not None
        assert application.status == "saved"

        events = (
            db.query(ApplicationStatusEvent)
            .filter(
                ApplicationStatusEvent.application_id
                == application_id
            )
            .all()
        )
        assert events == []
    finally:
        db.close()


def test_candidate_status_patch_rejects_active_legacy_unknown_listing(
    client: TestClient,
):
    """
    A4 security regression:
    PATCH saved -> applied must enforce the same canonical public boundary
    as explicit POST submit.
    """
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Patch Boundary Candidate",
        )
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            listing_source="legacy_unknown",
            title="Hidden Patch Internship",
            company="Unknown Source",
            location="Remote",
            work_type="remote",
            description="Must remain unavailable for submission.",
            required_skills=[],
            preferred_skills=[],
            language="English",
            publication_status="published",
            is_active=True,
        )
        db.add(listing)
        db.flush()

        application = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            status="saved",
            notes=None,
        )
        db.add(application)
        db.commit()

        application_id = application.id
    finally:
        db.close()

    response = client.patch(
        f"/api/v1/applications/{application_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "applied"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "This internship opportunity is not currently "
        "available for new submissions."
    )

    db = TestingSessionLocal()
    try:
        application = db.get(Application, application_id)
        assert application is not None
        assert application.status == "saved"

        events = (
            db.query(ApplicationStatusEvent)
            .filter(
                ApplicationStatusEvent.application_id
                == application_id
            )
            .all()
        )
        assert events == []
    finally:
        db.close()
