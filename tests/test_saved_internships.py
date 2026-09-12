"""
Regression and Integration Tests for Candidate Saved Internships
Validates:
- GET /api/v1/saved-internships
- POST /api/v1/saved-internships/{internship_id}
- DELETE /api/v1/saved-internships/{internship_id}
- Strict isolation, idempotency, DB uniqueness, and application separation.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.db.models import Application, InternshipListing, SavedInternship, StudentProfile
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from tests.db import TestingSessionLocal

pytestmark = pytest.mark.usefixtures("mock_supabase_auth")


@pytest.fixture(autouse=True)
def clean_database_tables():
    """Ensure relevant tables are cleared before and after each test."""
    db = TestingSessionLocal()
    try:
        db.query(SavedInternship).delete()
        db.query(Application).delete()
        db.query(InternshipListing).delete()
        db.query(StudentProfile).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = TestingSessionLocal()
    try:
        db.query(SavedInternship).delete()
        db.query(Application).delete()
        db.query(InternshipListing).delete()
        db.query(StudentProfile).delete()
        db.commit()
    finally:
        db.close()


def create_test_internship(
    title: str = "Software Engineer Intern",
    company: str = "Acme Corp",
    location: str = "Remote",
    work_type: str = "remote",
) -> InternshipListing:
    """Helper to insert a test internship listing into the database."""
    db = TestingSessionLocal()
    try:
        listing = InternshipListing(
            listing_source="curated",
            id=uuid4(),
            title=title,
            company=company,
            location=location,
            work_type=work_type,
            description="Build modern backend systems with Python and FastAPI.",
            required_skills=["Python", "FastAPI"],
            preferred_skills=["Docker", "PostgreSQL"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(listing)
        db.commit()
        db.refresh(listing)
        return listing
    finally:
        db.close()


def create_test_profile(user_id=None, full_name="Jane Doe") -> StudentProfile:
    """Helper to insert a test student profile."""
    uid = user_id or uuid4()
    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=uid,
            full_name=full_name,
            headline="Software Engineering Student",
            preferences={"work_types": ["remote"], "desired_locations": ["Remote"]},
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile
    finally:
        db.close()


# 1. Unauthenticated save / unsave / list rejected (401)
def test_unauthenticated_requests_rejected(client: TestClient):
    """Verify that unauthenticated requests to all saved-internships endpoints return 401."""
    internship = create_test_internship()

    # Save
    resp = client.post(f"/api/v1/saved-internships/{internship.id}")
    assert resp.status_code == 401

    # Unsave
    resp = client.delete(f"/api/v1/saved-internships/{internship.id}")
    assert resp.status_code == 401

    # List
    resp = client.get("/api/v1/saved-internships")
    assert resp.status_code == 401


# 2. Authenticated candidate can save an internship
def test_authenticated_candidate_can_save_internship(client: TestClient):
    """Verify authenticated candidate can successfully bookmark an internship."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    profile = create_test_profile(user_id=user_id)
    internship = create_test_internship()

    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(f"/api/v1/saved-internships/{internship.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["internship_id"] == str(internship.id)
    assert data["is_saved"] is True
    assert data["message"] == "Internship saved successfully."
    assert "saved_at" in data
    assert "id" in data

    # 3. Verify saved row in DB belongs to authenticated candidate
    db = TestingSessionLocal()
    try:
        saved_row = db.query(SavedInternship).filter_by(
            student_id=profile.id, internship_id=internship.id
        ).first()
        assert saved_row is not None
        assert saved_row.student_id == profile.id
        assert saved_row.internship_id == internship.id
    finally:
        db.close()


# 4. Duplicate save does not create duplicate (idempotency)
def test_duplicate_save_is_idempotent(client: TestClient):
    """Verify calling save multiple times does not create duplicates and returns success."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    profile = create_test_profile(user_id=user_id)
    internship = create_test_internship()

    headers = {"Authorization": f"Bearer {token}"}
    resp1 = client.post(f"/api/v1/saved-internships/{internship.id}", headers=headers)
    assert resp1.status_code == 200

    resp2 = client.post(f"/api/v1/saved-internships/{internship.id}", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["is_saved"] is True
    assert resp2.json()["id"] == resp1.json()["id"]

    db = TestingSessionLocal()
    try:
        count = db.query(SavedInternship).filter_by(
            student_id=profile.id, internship_id=internship.id
        ).count()
        assert count == 1
    finally:
        db.close()


# 5. Nonexistent internship rejected (404)
def test_save_nonexistent_internship_returns_404(client: TestClient):
    """Verify saving a non-existent internship ID returns 404."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    create_test_profile(user_id=user_id)

    nonexistent_id = uuid4()
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(f"/api/v1/saved-internships/{nonexistent_id}", headers=headers)
    assert response.status_code == 404
    assert "not found" in response.json()["error"]["message"].lower()


# 6. Candidate without profile rejected on save (404)
def test_save_without_profile_returns_404(client: TestClient):
    """Verify saving when candidate profile does not exist returns 404."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    internship = create_test_internship()

    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(f"/api/v1/saved-internships/{internship.id}", headers=headers)
    assert response.status_code == 404
    assert "profile not found" in response.json()["error"]["message"].lower()


# 7. Candidate can list own saved internships & no cross-user exposure
def test_list_saved_internships_and_user_isolation(client: TestClient):
    """Verify listing saved internships returns candidate's bookmarks only and isolates users."""
    user_a = uuid4()
    token_a = f"valid-user-{user_a}"
    create_test_profile(user_id=user_a, full_name="User A")

    user_b = uuid4()
    token_b = f"valid-user-{user_b}"
    create_test_profile(user_id=user_b, full_name="User B")

    internship1 = create_test_internship(title="Internship 1")
    internship2 = create_test_internship(title="Internship 2")
    internship3 = create_test_internship(title="Internship 3")

    # User A saves internship 1 and 2
    headers_a = {"Authorization": f"Bearer {token_a}"}
    client.post(f"/api/v1/saved-internships/{internship1.id}", headers=headers_a)
    client.post(f"/api/v1/saved-internships/{internship2.id}", headers=headers_a)

    # User B saves internship 3
    headers_b = {"Authorization": f"Bearer {token_b}"}
    client.post(f"/api/v1/saved-internships/{internship3.id}", headers=headers_b)

    # User A lists saved
    resp_a = client.get("/api/v1/saved-internships", headers=headers_a)
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["total"] == 2
    assert len(data_a["items"]) == 2
    user_a_saved_ids = {item["internship_id"] for item in data_a["items"]}
    assert user_a_saved_ids == {str(internship1.id), str(internship2.id)}
    assert str(internship3.id) not in user_a_saved_ids

    # User B lists saved
    resp_b = client.get("/api/v1/saved-internships", headers=headers_b)
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["total"] == 1
    assert len(data_b["items"]) == 1
    assert data_b["items"][0]["internship_id"] == str(internship3.id)


# 8. Ordering is newest saved first with deterministic secondary ordering
def test_list_saved_internships_ordering(client: TestClient):
    """Verify saved internships are ordered by created_at desc, id desc."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    profile = create_test_profile(user_id=user_id)

    db = TestingSessionLocal()
    try:
        listings = []
        for i in range(3):
            listing = InternshipListing(
                listing_source="curated",
                id=uuid4(),
                title=f"Role {i}",
                company="TechCorp",
                location="Remote",
                work_type="remote",
                description=f"Desc {i}",
                required_skills=["Python"],
                preferred_skills=[],
                created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            )
            db.add(listing)
            listings.append(listing)
        db.commit()

        # Insert bookmarks with specific timestamps
        for i, listing in enumerate(listings):
            saved = SavedInternship(
                id=uuid4(),
                student_id=profile.id,
                internship_id=listing.id,
                created_at=datetime(2026, 8, 10 + i, tzinfo=timezone.utc),
            )
            db.add(saved)
        db.commit()
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/saved-internships", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 3
    # Role 2 (Aug 12) must be first, then Role 1 (Aug 11), then Role 0 (Aug 10)
    assert items[0]["internship"]["title"] == "Role 2"
    assert items[1]["internship"]["title"] == "Role 1"
    assert items[2]["internship"]["title"] == "Role 0"


# 9. Pagination contract works
def test_list_saved_internships_pagination(client: TestClient):
    """Verify pagination limit and offset parameters."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    profile = create_test_profile(user_id=user_id)

    db = TestingSessionLocal()
    try:
        for i in range(5):
            listing = InternshipListing(
                listing_source="curated",
                id=uuid4(),
                title=f"Internship {i}",
                company="Company",
                location="Remote",
                work_type="remote",
                description="Desc",
                required_skills=["Python"],
                created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            )
            db.add(listing)
            db.flush()
            saved = SavedInternship(
                id=uuid4(),
                student_id=profile.id,
                internship_id=listing.id,
                created_at=datetime(2026, 8, i + 1, tzinfo=timezone.utc),
            )
            db.add(saved)
        db.commit()
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {token}"}
    # Limit 2, Offset 1
    resp = client.get("/api/v1/saved-internships?limit=2&offset=1", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 1
    assert len(data["items"]) == 2
    assert data["items"][0]["internship"]["title"] == "Internship 3"
    assert data["items"][1]["internship"]["title"] == "Internship 2"


# 10. Candidate can unsave
def test_candidate_can_unsave_internship(client: TestClient):
    """Verify candidate can remove a saved bookmark."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    profile = create_test_profile(user_id=user_id)
    internship = create_test_internship()

    headers = {"Authorization": f"Bearer {token}"}
    # Save
    client.post(f"/api/v1/saved-internships/{internship.id}", headers=headers)

    # Unsave
    resp = client.delete(f"/api/v1/saved-internships/{internship.id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["internship_id"] == str(internship.id)
    assert data["is_saved"] is False
    assert data["message"] == "Internship unsaved successfully."

    # Verify DB row is gone
    db = TestingSessionLocal()
    try:
        saved_row = db.query(SavedInternship).filter_by(
            student_id=profile.id, internship_id=internship.id
        ).first()
        assert saved_row is None
        # Internship listing itself MUST NOT be deleted
        listing = db.query(InternshipListing).filter_by(id=internship.id).first()
        assert listing is not None
    finally:
        db.close()


# 11. Unsave cannot affect another user's bookmark
def test_unsave_cannot_affect_another_user_bookmark(client: TestClient):
    """Verify candidate A unsaving an internship does not delete candidate B's bookmark."""
    user_a = uuid4()
    token_a = f"valid-user-{user_a}"
    profile_a = create_test_profile(user_id=user_a, full_name="User A")

    user_b = uuid4()
    token_b = f"valid-user-{user_b}"
    profile_b = create_test_profile(user_id=user_b, full_name="User B")

    internship = create_test_internship()

    # Both save the same internship
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}
    client.post(f"/api/v1/saved-internships/{internship.id}", headers=headers_a)
    client.post(f"/api/v1/saved-internships/{internship.id}", headers=headers_b)

    # User A unsaves
    resp_unsave = client.delete(f"/api/v1/saved-internships/{internship.id}", headers=headers_a)
    assert resp_unsave.status_code == 200

    # User B's bookmark MUST still exist
    db = TestingSessionLocal()
    try:
        saved_a = db.query(SavedInternship).filter_by(
            student_id=profile_a.id, internship_id=internship.id
        ).first()
        assert saved_a is None

        saved_b = db.query(SavedInternship).filter_by(
            student_id=profile_b.id, internship_id=internship.id
        ).first()
        assert saved_b is not None
    finally:
        db.close()


# 12. Repeated / absent unsave has deterministic behavior
def test_absent_unsave_is_idempotent(client: TestClient):
    """Verify unsaving an internship that was not saved returns 200 OK without errors."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    create_test_profile(user_id=user_id)
    internship = create_test_internship()

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.delete(f"/api/v1/saved-internships/{internship.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_saved"] is False


# 13. Saving does NOT create an Application
def test_save_does_not_create_application(client: TestClient):
    """Verify bookmarking an internship creates ZERO rows in the applications table."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    profile = create_test_profile(user_id=user_id)
    internship = create_test_internship()

    headers = {"Authorization": f"Bearer {token}"}
    client.post(f"/api/v1/saved-internships/{internship.id}", headers=headers)

    db = TestingSessionLocal()
    try:
        apps = db.query(Application).filter_by(student_id=profile.id).all()
        assert len(apps) == 0
    finally:
        db.close()


# 14. Saving does NOT modify existing Application
def test_save_does_not_modify_existing_application(client: TestClient):
    """Verify saving an internship does not mutate an existing Application status or fields."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    profile = create_test_profile(user_id=user_id)
    internship = create_test_internship()

    # Pre-create an application with status 'interviewing'
    db = TestingSessionLocal()
    try:
        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=internship.id,
            status="interviewing",
            notes="Initial phone screen scheduled.",
        )
        db.add(app)
        db.commit()
    finally:
        db.close()

    # Bookmark the internship
    headers = {"Authorization": f"Bearer {token}"}
    client.post(f"/api/v1/saved-internships/{internship.id}", headers=headers)

    # Verify Application is untouched
    db = TestingSessionLocal()
    try:
        app_after = db.query(Application).filter_by(
            student_id=profile.id, internship_id=internship.id
        ).first()
        assert app_after is not None
        assert app_after.status == "interviewing"
        assert app_after.notes == "Initial phone screen scheduled."
    finally:
        db.close()


# 15. Unsaving does NOT delete Application
def test_unsave_does_not_delete_application(client: TestClient):
    """Verify unsaving a bookmark does not delete or change an existing Application."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    profile = create_test_profile(user_id=user_id)
    internship = create_test_internship()

    # Save bookmark
    headers = {"Authorization": f"Bearer {token}"}
    client.post(f"/api/v1/saved-internships/{internship.id}", headers=headers)

    # Pre-create application
    db = TestingSessionLocal()
    try:
        app = Application(
            id=uuid4(),
            student_id=profile.id,
            internship_id=internship.id,
            status="applied",
            generated_cover_letter="Cover letter text",
        )
        db.add(app)
        db.commit()
    finally:
        db.close()

    # Unsave bookmark
    client.delete(f"/api/v1/saved-internships/{internship.id}", headers=headers)

    # Verify Application is still in database and unchanged
    db = TestingSessionLocal()
    try:
        app_check = db.query(Application).filter_by(
            student_id=profile.id, internship_id=internship.id
        ).first()
        assert app_check is not None
        assert app_check.status == "applied"
        assert app_check.generated_cover_letter == "Cover letter text"
    finally:
        db.close()


# 16. Saved internship response contains expected real internship data
def test_saved_internship_response_contains_real_internship_data(client: TestClient):
    """Verify list response includes real internship domain details for mobile."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"
    create_test_profile(user_id=user_id)
    internship = create_test_internship(
        title="AI Research Intern",
        company="DeepMind Partner",
        location="London, UK",
        work_type="hybrid",
    )

    headers = {"Authorization": f"Bearer {token}"}
    client.post(f"/api/v1/saved-internships/{internship.id}", headers=headers)

    resp = client.get("/api/v1/saved-internships", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    item = data["items"][0]
    assert item["internship_id"] == str(internship.id)
    assert "saved_at" in item

    # Verify embedded internship summary
    internship_data = item["internship"]
    assert internship_data["id"] == str(internship.id)
    assert internship_data["title"] == "AI Research Intern"
    assert internship_data["company"] == "DeepMind Partner"
    assert internship_data["location"] == "London, UK"
    assert internship_data["work_type"] == "hybrid"
    assert internship_data["required_skills"] == ["Python", "FastAPI"]
    assert internship_data["preferred_skills"] == ["Docker", "PostgreSQL"]
    assert "posted_at" in internship_data


# 17. Database uniqueness constraint is enforced
def test_database_uniqueness_constraint_enforced():
    """Verify unique constraint on (student_id, internship_id) raises IntegrityError at DB level."""
    profile = create_test_profile()
    internship = create_test_internship()

    db = TestingSessionLocal()
    try:
        saved1 = SavedInternship(
            student_id=profile.id,
            internship_id=internship.id,
        )
        db.add(saved1)
        db.commit()

        saved2 = SavedInternship(
            student_id=profile.id,
            internship_id=internship.id,
        )
        db.add(saved2)
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.close()


# 18. Cascade delete on internship and profile foreign keys
def test_cascade_delete_foreign_key_configuration():
    """Verify ForeignKey configurations for student_id and internship_id are CASCADE."""
    fk_student = list(SavedInternship.__table__.c.student_id.foreign_keys)[0]
    assert fk_student.ondelete == "CASCADE"
    assert fk_student.target_fullname == "student_profiles.id"

    fk_internship = list(SavedInternship.__table__.c.internship_id.foreign_keys)[0]
    assert fk_internship.ondelete == "CASCADE"
    assert fk_internship.target_fullname == "internship_listings.id"


# 19. Existing internship listing/detail behavior does not regress
def test_existing_internship_catalog_endpoints_no_regression(client: TestClient):
    """Verify public catalog /api/v1/internships and /api/v1/internships/{id} remain unchanged."""
    internship = create_test_internship(title="Catalog Intern")

    # Catalog listing
    resp_list = client.get("/api/v1/internships")
    assert resp_list.status_code == 200
    assert resp_list.json()["total"] == 1
    assert resp_list.json()["items"][0]["title"] == "Catalog Intern"

    # Catalog detail
    resp_detail = client.get(f"/api/v1/internships/{internship.id}")
    assert resp_detail.status_code == 200
    assert resp_detail.json()["title"] == "Catalog Intern"
