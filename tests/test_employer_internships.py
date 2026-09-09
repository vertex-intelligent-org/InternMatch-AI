"""
Unit and Integration Tests for Employer Opportunity Creation, My Opportunities,
and Applicant Retrieval Endpoints (Gate EMP-MVP1 / EMP-MVP1B).
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from app.core.config import settings
from app.db.models import (
    Application,
    InternshipListing,
    Match,
    Skill,
    StudentProfile,
    StudentSkill,
)
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal

pytestmark = pytest.mark.usefixtures("mock_supabase_auth")


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure relevant tables are cleared before and after each test."""
    db = TestingSessionLocal()
    try:
        db.query(Match).delete()
        db.query(Application).delete()
        db.query(StudentSkill).delete()
        db.query(Skill).delete()
        db.query(InternshipListing).delete()
        db.query(StudentProfile).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = TestingSessionLocal()
    try:
        db.query(Match).delete()
        db.query(Application).delete()
        db.query(StudentSkill).delete()
        db.query(Skill).delete()
        db.query(InternshipListing).delete()
        db.query(StudentProfile).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def default_mock_embedding(monkeypatch):
    """Provide default valid embedding vector for employer listing creation tests."""
    monkeypatch.setattr(
        "app.api.v1.endpoints.internships.generate_embedding",
        lambda text: [0.1] * settings.EMBEDDING_DIMENSION,
    )


def _create_profile(user_id, full_name, account_type="employer", preferences=None):
    """Helper to create a StudentProfile in test database."""
    prefs = preferences or {}
    prefs["account_type"] = account_type
    db = TestingSessionLocal()
    try:
        profile = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name=full_name,
            headline="Sample Headline",
            preferences=prefs,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile
    finally:
        db.close()


# ==============================================================================
# 1. AUTHENTICATION & ROLE LAW TESTS
# ==============================================================================


def test_create_internship_unauthenticated(client: TestClient):
    """Verify POST /api/v1/internships without auth header returns 401."""
    payload = {
        "title": "Software Engineer Intern",
        "company": "Acme Corp",
        "location": "Istanbul, Turkiye",
        "work_type": "hybrid",
        "description": "Develop high-scale backend services.",
        "required_skills": ["Python", "FastAPI"],
    }
    response = client.post("/api/v1/internships", json=payload)
    assert response.status_code == 401


def test_create_internship_forbidden_for_intern_account(client: TestClient):
    """Verify POST /api/v1/internships returns 403 when user is an intern (candidate)."""
    candidate_user_id = uuid4()
    _create_profile(candidate_user_id, "Candidate User", account_type="intern")

    payload = {
        "title": "Software Engineer Intern",
        "company": "Acme Corp",
        "location": "Remote",
        "work_type": "remote",
        "description": "Develop high-scale backend services.",
        "required_skills": ["Python"],
    }
    response = client.post(
        "/api/v1/internships",
        json=payload,
        headers={"Authorization": f"Bearer valid-user-{candidate_user_id}"},
    )
    assert response.status_code == 403
    assert "Forbidden" in response.json()["detail"]["error"]["code"] or response.status_code == 403


def test_create_internship_forbidden_when_no_profile_exists(client: TestClient):
    """Verify POST /api/v1/internships returns 403 when authenticated user has no profile."""
    unknown_user_id = uuid4()
    payload = {
        "title": "Software Engineer Intern",
        "company": "Acme Corp",
        "location": "Remote",
        "work_type": "remote",
        "description": "Develop high-scale backend services.",
    }
    response = client.post(
        "/api/v1/internships",
        json=payload,
        headers={"Authorization": f"Bearer valid-user-{unknown_user_id}"},
    )
    assert response.status_code == 403


# ==============================================================================
# 2. OPPORTUNITY CREATION & PRIVACY / IMMEDIATE PUBLICATION
# ==============================================================================


def test_create_internship_success_and_immediate_publication(client: TestClient):
    """
    Verify employer can create an opportunity:
    - Returns 201 Created
    - Sets employer_user_id server-side in DB (not exposed in public responses)
    - Immediately visible in public GET /api/v1/internships
    - Detail accessible via GET /api/v1/internships/{id}
    - Privacy: employer_user_id is NOT exposed in POST, catalog GET, or detail GET
    """
    employer_user_id = uuid4()
    _create_profile(employer_user_id, "Acme Recruiter", account_type="employer")

    payload = {
        "title": "Cloud Backend Intern",
        "company": "Acme Corp",
        "location": "Istanbul, Turkiye",
        "work_type": "hybrid",
        "description": "Join our platform team to build scalable microservices.",
        "required_skills": ["Python", "PostgreSQL", "Docker"],
        "preferred_skills": ["Kubernetes", "Redis"],
        "language": "English",
        "education_requirements": "Computer Science student",
        "experience_requirements": "1+ projects with Python",
    }

    # 1. Create opportunity
    res_create = client.post(
        "/api/v1/internships",
        json=payload,
        headers={"Authorization": f"Bearer valid-user-{employer_user_id}"},
    )
    assert res_create.status_code == 201
    created_data = res_create.json()

    assert created_data["title"] == "Cloud Backend Intern"
    assert created_data["company"] == "Acme Corp"
    assert created_data["location"] == "Istanbul, Turkiye"
    assert created_data["work_type"] == "hybrid"
    assert created_data["description"] == "Join our platform team to build scalable microservices."
    assert created_data["required_skills"] == ["Python", "PostgreSQL", "Docker"]
    assert created_data["preferred_skills"] == ["Kubernetes", "Redis"]
    assert created_data["languages"] == ["English"]
    assert created_data["min_education"] == "Computer Science student"

    # Privacy check on POST response
    assert "employer_user_id" not in created_data
    listing_id = UUID(created_data["id"])

    # 2. Verify DB-level internal persistence
    db = TestingSessionLocal()
    try:
        persisted_listing = db.get(InternshipListing, listing_id)
        assert persisted_listing is not None
        assert persisted_listing.employer_user_id == employer_user_id
        assert persisted_listing.description_embedding is not None
        assert len(persisted_listing.description_embedding) == settings.EMBEDDING_DIMENSION
    finally:
        db.close()

    # 3. Immediately visible in public catalog without exposing employer_user_id
    res_list = client.get("/api/v1/internships")
    assert res_list.status_code == 200
    catalog = res_list.json()
    assert catalog["total"] == 1
    assert catalog["items"][0]["id"] == str(listing_id)
    assert catalog["items"][0]["title"] == "Cloud Backend Intern"
    assert "employer_user_id" not in catalog["items"][0]

    # 4. Accessible in public detail without exposing employer_user_id
    res_detail = client.get(f"/api/v1/internships/{listing_id}")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["id"] == str(listing_id)
    assert detail["company"] == "Acme Corp"
    assert "employer_user_id" not in detail


def test_create_internship_input_validation(client: TestClient):
    """Verify validation rejects empty strings, invalid work_types, etc."""
    employer_user_id = uuid4()
    _create_profile(employer_user_id, "Acme Recruiter", account_type="employer")

    headers = {"Authorization": f"Bearer valid-user-{employer_user_id}"}

    # Empty title
    res_empty_title = client.post(
        "/api/v1/internships",
        json={
            "title": "   ",
            "company": "Acme",
            "location": "Remote",
            "work_type": "remote",
            "description": "Desc",
        },
        headers=headers,
    )
    assert res_empty_title.status_code == 422

    # Invalid work_type
    res_invalid_work_type = client.post(
        "/api/v1/internships",
        json={
            "title": "Engineer",
            "company": "Acme",
            "location": "Remote",
            "work_type": "invalid_mode",
            "description": "Desc",
        },
        headers=headers,
    )
    assert res_invalid_work_type.status_code == 422


# ==============================================================================
# 3. EMPLOYER MY OPPORTUNITIES (/api/v1/internships/mine)
# ==============================================================================


def test_list_my_internships_tenant_isolation_and_ordering(client: TestClient):
    """
    Verify GET /api/v1/internships/mine:
    - Returns only opportunities owned by the authenticated employer
    - Strict cross-employer isolation
    - Ordered newest first
    - Static route not swallowed by /{id}
    - Privacy: employer_user_id not exposed in response items
    """
    employer_a = uuid4()
    employer_b = uuid4()
    _create_profile(employer_a, "Employer A", account_type="employer")
    _create_profile(employer_b, "Employer B", account_type="employer")

    headers_a = {"Authorization": f"Bearer valid-user-{employer_a}"}
    headers_b = {"Authorization": f"Bearer valid-user-{employer_b}"}

    # Employer A creates 2 listings
    client.post(
        "/api/v1/internships",
        json={
            "title": "Listing A1",
            "company": "Company A",
            "location": "Remote",
            "work_type": "remote",
            "description": "Desc A1",
        },
        headers=headers_a,
    )
    client.post(
        "/api/v1/internships",
        json={
            "title": "Listing A2",
            "company": "Company A",
            "location": "Remote",
            "work_type": "remote",
            "description": "Desc A2",
        },
        headers=headers_a,
    )

    # Employer B creates 1 listing
    client.post(
        "/api/v1/internships",
        json={
            "title": "Listing B1",
            "company": "Company B",
            "location": "Remote",
            "work_type": "remote",
            "description": "Desc B1",
        },
        headers=headers_b,
    )

    # Employer A requests /mine -> sees 2 listings (A2 newest first, then A1)
    res_a = client.get("/api/v1/internships/mine", headers=headers_a)
    assert res_a.status_code == 200
    data_a = res_a.json()
    assert data_a["total"] == 2
    assert data_a["items"][0]["title"] == "Listing A2"
    assert data_a["items"][1]["title"] == "Listing A1"
    assert "employer_user_id" not in data_a["items"][0]

    # Employer B requests /mine -> sees 1 listing (B1)
    res_b = client.get("/api/v1/internships/mine", headers=headers_b)
    assert res_b.status_code == 200
    data_b = res_b.json()
    assert data_b["total"] == 1
    assert data_b["items"][0]["title"] == "Listing B1"
    assert "employer_user_id" not in data_b["items"][0]


# ==============================================================================
# 4. APPLICANT RETRIEVAL & FILTERING (STATUS != 'SAVED')
# ==============================================================================


def test_employer_applicant_retrieval_and_filtering(client: TestClient):
    """
    Verify employer applicant retrieval:
    - Excludes 'saved' applications (draft cover letters)
    - Includes submitted applications ('applied', 'interviewing', 'accepted', 'rejected')
    - Tenant isolation: Employer B cannot access Employer A's listing applicants (404)
    """
    employer_user_id = uuid4()
    other_employer_id = uuid4()
    candidate_1_user_id = uuid4()
    candidate_2_user_id = uuid4()

    _create_profile(employer_user_id, "Tech Employer", account_type="employer")
    _create_profile(other_employer_id, "Other Employer", account_type="employer")
    prof1 = _create_profile(
        candidate_1_user_id,
        "Alice Candidate",
        account_type="intern",
        preferences={"department": "Computer Science"},
    )
    prof2 = _create_profile(
        candidate_2_user_id,
        "Bob Candidate",
        account_type="intern",
        preferences={"department": "Software Engineering"},
    )

    headers_employer = {"Authorization": f"Bearer valid-user-{employer_user_id}"}
    headers_other = {"Authorization": f"Bearer valid-user-{other_employer_id}"}

    # 1. Employer creates opportunity
    res_create = client.post(
        "/api/v1/internships",
        json={
            "title": "Fullstack Developer Intern",
            "company": "Tech Employer Inc",
            "location": "Istanbul",
            "work_type": "hybrid",
            "description": "Fullstack web app development.",
            "required_skills": ["React", "Python"],
        },
        headers=headers_employer,
    )
    assert res_create.status_code == 201
    listing_id = UUID(res_create.json()["id"])

    # 2. Candidate 1 generates a cover letter -> creates Application with status='saved'
    db = TestingSessionLocal()
    try:
        app_saved = Application(
            id=uuid4(),
            student_id=prof1.id,
            internship_id=listing_id,
            status="saved",
            generated_cover_letter="Draft cover letter...",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(app_saved)
        db.commit()
    finally:
        db.close()

    # Employer checks applicants -> should be 0 (because status is 'saved')
    res_applicants_0 = client.get(
        f"/api/v1/internships/{listing_id}/applicants",
        headers=headers_employer,
    )
    assert res_applicants_0.status_code == 200
    assert res_applicants_0.json()["total"] == 0
    assert res_applicants_0.json()["items"] == []

    # 3. Candidate 1 applies -> status='applied'
    db = TestingSessionLocal()
    try:
        app_1 = db.query(Application).filter(Application.student_id == prof1.id).first()
        app_1.status = "applied"
        app_1.applied_date = datetime.now(timezone.utc).date()

        # Add match score for Candidate 1
        match_1 = Match(
            student_id=prof1.id,
            internship_id=listing_id,
            overall_score=88,
            skill_score=90,
            vector_score=85,
            attribute_score=90,
        )
        db.add(match_1)

        # Candidate 2 applies directly -> status='interviewing'
        app_2 = Application(
            id=uuid4(),
            student_id=prof2.id,
            internship_id=listing_id,
            status="interviewing",
            generated_cover_letter="Bob's cover letter...",
            applied_date=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(app_2)
        db.commit()
    finally:
        db.close()

    # Employer checks applicants -> sees 2 applicants
    res_applicants_2 = client.get(
        f"/api/v1/internships/{listing_id}/applicants",
        headers=headers_employer,
    )
    assert res_applicants_2.status_code == 200
    data_app = res_applicants_2.json()
    assert data_app["total"] == 2

    # Check applicant fields
    applicant_names = [item["candidate"]["full_name"] for item in data_app["items"]]
    assert "Alice Candidate" in applicant_names
    assert "Bob Candidate" in applicant_names

    # Check match score on Alice
    alice_item = next(
        i for i in data_app["items"] if i["candidate"]["full_name"] == "Alice Candidate"
    )
    assert alice_item["match_score"] == 88
    assert alice_item["status"] == "applied"
    assert alice_item["candidate"]["department"] == "Computer Science"

    # 4. Detail endpoint for Alice
    alice_app_id = alice_item["application_id"]
    res_detail = client.get(
        f"/api/v1/internships/{listing_id}/applicants/{alice_app_id}",
        headers=headers_employer,
    )
    assert res_detail.status_code == 200
    alice_detail = res_detail.json()
    assert alice_detail["application_id"] == alice_app_id
    assert alice_detail["candidate"]["full_name"] == "Alice Candidate"

    # 5. Cross-employer isolation: Other employer attempts to access applicants
    res_other = client.get(
        f"/api/v1/internships/{listing_id}/applicants",
        headers=headers_other,
    )
    assert res_other.status_code == 404

    res_other_detail = client.get(
        f"/api/v1/internships/{listing_id}/applicants/{alice_app_id}",
        headers=headers_other,
    )
    assert res_other_detail.status_code == 404


# ==============================================================================
# 5. EMBEDDING HARDENING TESTS (SUCCESS & CONTROLLED FAILURE PATHS)
# ==============================================================================


def test_create_internship_with_embedding_generation(client: TestClient, monkeypatch):
    """
    Verify that when embedding provider succeeds, description embedding
    is generated and persisted upon opportunity creation.
    """
    employer_user_id = uuid4()
    _create_profile(employer_user_id, "AI Employer", account_type="employer")

    fake_vector = [0.1] * settings.EMBEDDING_DIMENSION

    def mock_generate_embedding(text: str):
        return fake_vector

    monkeypatch.setattr(
        "app.api.v1.endpoints.internships.generate_embedding",
        mock_generate_embedding,
    )

    headers = {"Authorization": f"Bearer valid-user-{employer_user_id}"}
    res = client.post(
        "/api/v1/internships",
        json={
            "title": "ML Engineer Intern",
            "company": "AI Labs",
            "location": "Remote",
            "work_type": "remote",
            "description": "Train diffusion models and optimize inference pipelines.",
            "required_skills": ["PyTorch", "Python"],
        },
        headers=headers,
    )
    assert res.status_code == 201
    listing_id = UUID(res.json()["id"])

    db = TestingSessionLocal()
    try:
        listing = db.get(InternshipListing, listing_id)
        assert listing is not None
        assert listing.description_embedding == fake_vector
    finally:
        db.close()


def test_create_internship_embedding_failure_does_not_publish(
    client: TestClient, monkeypatch
):
    """
    Verify that if embedding generation fails:
    - Returns 503 Service Unavailable with generic safe message
    - Zero rows persisted to database (no partial or orphan listings)
    - Public catalog remains unchanged
    - Error response does not leak provider exception or details
    """
    employer_user_id = uuid4()
    _create_profile(employer_user_id, "AI Employer", account_type="employer")

    def mock_failing_embedder(text: str):
        raise RuntimeError(
            "Simulated upstream Google Gemini API outage: connection reset by peer"
        )

    monkeypatch.setattr(
        "app.api.v1.endpoints.internships.generate_embedding",
        mock_failing_embedder,
    )

    headers = {"Authorization": f"Bearer valid-user-{employer_user_id}"}
    payload = {
        "title": "Quantum ML Intern",
        "company": "QuantumAI Corp",
        "location": "Remote",
        "work_type": "remote",
        "description": "Design variational quantum circuits for chemistry simulation.",
        "required_skills": ["Qiskit", "Python"],
    }

    # 1. Attempt creation
    res = client.post("/api/v1/internships", json=payload, headers=headers)
    assert res.status_code == 503
    err_body = res.json()
    assert err_body["detail"] == "Opportunity publishing is temporarily unavailable."
    # Prove zero provider leakage
    assert "Simulated upstream" not in str(err_body)
    assert "Gemini" not in str(err_body)
    assert "connection reset" not in str(err_body)

    # 2. Prove zero listings persisted at DB level
    db = TestingSessionLocal()
    try:
        count = db.query(InternshipListing).count()
        assert count == 0
    finally:
        db.close()

    # 3. Prove public catalog is empty
    res_catalog = client.get("/api/v1/internships")
    assert res_catalog.status_code == 200
    assert res_catalog.json()["total"] == 0
    assert res_catalog.json()["items"] == []


# ==============================================================================
# 6. GATE EMP-MVP3: OPPORTUNITY LIFECYCLE & APPLICANT STATUS STATE MACHINE
# ==============================================================================


def test_employer_close_opportunity_success_and_catalog_exclusion(client: TestClient):
    """
    Verify employer can close an active opportunity:
    - POST /api/v1/internships/{id}/close returns 200 and is_active: False
    - Disappears from public candidate catalog GET /api/v1/internships
    - Remains visible in employer's GET /api/v1/internships/mine with is_active: False
    - Historical applications remain intact
    """
    employer_id = uuid4()
    _create_profile(employer_id, "Recruiter", account_type="employer")
    headers = {"Authorization": f"Bearer valid-user-{employer_id}"}

    # 1. Create opportunity
    create_res = client.post(
        "/api/v1/internships",
        json={
            "title": "Backend Intern",
            "company": "Tech Corp",
            "location": "Remote",
            "work_type": "remote",
            "description": "Backend API development.",
            "required_skills": ["Python"],
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    listing_id = create_res.json()["id"]

    # Verify present in public catalog
    cat_res = client.get("/api/v1/internships")
    assert cat_res.status_code == 200
    assert any(item["id"] == listing_id for item in cat_res.json()["items"])

    # 2. Close opportunity
    close_res = client.post(f"/api/v1/internships/{listing_id}/close", headers=headers)
    assert close_res.status_code == 200
    assert close_res.json()["is_active"] is False

    # 3. Verify excluded from public candidate catalog
    cat_res2 = client.get("/api/v1/internships")
    assert cat_res2.status_code == 200
    assert not any(item["id"] == listing_id for item in cat_res2.json()["items"])

    # 4. Verify present in employer /mine list as closed
    mine_res = client.get("/api/v1/internships/mine", headers=headers)
    assert mine_res.status_code == 200
    mine_items = mine_res.json()["items"]
    assert len(mine_items) == 1
    assert mine_items[0]["id"] == listing_id
    assert mine_items[0]["is_active"] is False


def test_employer_close_opportunity_isolation_and_permissions(client: TestClient):
    """
    Verify security for closing opportunities:
    - Candidate receives 403 Forbidden
    - Non-owner employer receives 404 Not Found
    """
    owner_id = uuid4()
    _create_profile(owner_id, "Owner", account_type="employer")
    owner_headers = {"Authorization": f"Bearer valid-user-{owner_id}"}

    create_res = client.post(
        "/api/v1/internships",
        json={
            "title": "DevOps Intern",
            "company": "Cloud Inc",
            "location": "Remote",
            "work_type": "remote",
            "description": "CI/CD pipelines.",
        },
        headers=owner_headers,
    )
    listing_id = create_res.json()["id"]

    # Candidate attempt -> 403
    candidate_id = uuid4()
    _create_profile(candidate_id, "Candidate", account_type="intern")
    candidate_headers = {"Authorization": f"Bearer valid-user-{candidate_id}"}
    res_cand = client.post(
        f"/api/v1/internships/{listing_id}/close", headers=candidate_headers
    )
    assert res_cand.status_code == 403

    # Other employer attempt -> 404 (ownership isolation)
    other_emp_id = uuid4()
    _create_profile(other_emp_id, "Other Employer", account_type="employer")
    other_headers = {"Authorization": f"Bearer valid-user-{other_emp_id}"}
    res_other = client.post(
        f"/api/v1/internships/{listing_id}/close", headers=other_headers
    )
    assert res_other.status_code == 404


def test_candidate_submit_application_endpoint(client: TestClient):
    """
    Verify candidate submission endpoint POST /api/v1/applications/{id}/submit:
    - Moves application from 'saved' to 'applied'
    - Sets applied_date
    - Creates exactly one ApplicationStatusEvent with status 'applied'
    - Returns 400 if opportunity is closed
    """
    employer_id = uuid4()
    _create_profile(employer_id, "Employer", account_type="employer")
    emp_headers = {"Authorization": f"Bearer valid-user-{employer_id}"}

    # Create listing
    create_res = client.post(
        "/api/v1/internships",
        json={
            "title": "Data Science Intern",
            "company": "DataCorp",
            "location": "Remote",
            "work_type": "remote",
            "description": "Data analytics.",
        },
        headers=emp_headers,
    )
    listing_id = UUID(create_res.json()["id"])

    # Candidate profile
    candidate_id = uuid4()
    cand_profile = _create_profile(candidate_id, "Data Candidate", account_type="intern")
    cand_headers = {"Authorization": f"Bearer valid-user-{candidate_id}"}

    # Create saved draft application
    db = TestingSessionLocal()
    try:
        app = Application(
            id=uuid4(),
            student_id=cand_profile.id,
            internship_id=listing_id,
            status="saved",
            generated_cover_letter="Draft cover letter for review.",
        )
        db.add(app)
        db.commit()
        app_id = app.id
    finally:
        db.close()

    # Candidate submits application with edited cover letter
    submit_res = client.post(
        f"/api/v1/applications/{app_id}/submit",
        json={
            "cover_letter": "Reviewed and polished final cover letter.",
            "notes": "Submitted after human review.",
        },
        headers=cand_headers,
    )
    assert submit_res.status_code == 200
    app_data = submit_res.json()
    assert app_data["status"] == "applied"
    assert app_data["applied_date"] is not None
    assert app_data["generated_cover_letter"] == "Reviewed and polished final cover letter."
    assert app_data["notes"] == "Submitted after human review."

    # Verify timeline event
    detail_res = client.get(f"/api/v1/applications/{app_id}", headers=cand_headers)
    assert detail_res.status_code == 200
    timeline = detail_res.json()["timeline"]
    assert len(timeline) == 1
    assert timeline[0]["status"] == "applied"

    # Close opportunity
    client.post(f"/api/v1/internships/{listing_id}/close", headers=emp_headers)

    # Candidate 2 attempts to submit application to closed opportunity
    candidate2_id = uuid4()
    cand2_profile = _create_profile(candidate2_id, "Candidate 2", account_type="intern")
    cand2_headers = {"Authorization": f"Bearer valid-user-{candidate2_id}"}

    db = TestingSessionLocal()
    try:
        app2 = Application(
            id=uuid4(),
            student_id=cand2_profile.id,
            internship_id=listing_id,
            status="saved",
        )
        db.add(app2)
        db.commit()
        app2_id = app2.id
    finally:
        db.close()

    submit_closed_res = client.post(
        f"/api/v1/applications/{app2_id}/submit",
        headers=cand2_headers,
    )
    assert submit_closed_res.status_code == 400
    assert "closed" in submit_closed_res.json()["detail"].lower()


def test_employer_applicant_status_lifecycle_and_terminal_states(client: TestClient):
    """
    Verify employer applicant status state machine:
    - applied -> interviewing -> accepted (200 OK)
    - Terminal accepted cannot be changed (400 Bad Request)
    - applied -> rejected (200 OK)
    - Terminal rejected cannot be changed (400 Bad Request)
    - Cannot transition 'saved' applications (400 Bad Request)
    """
    employer_id = uuid4()
    _create_profile(employer_id, "Hiring Manager", account_type="employer")
    emp_headers = {"Authorization": f"Bearer valid-user-{employer_id}"}

    create_res = client.post(
        "/api/v1/internships",
        json={
            "title": "Security Intern",
            "company": "SecureNet",
            "location": "Remote",
            "work_type": "remote",
            "description": "AppSec testing.",
        },
        headers=emp_headers,
    )
    listing_id = create_res.json()["id"]

    cand_id = uuid4()
    cand_profile = _create_profile(cand_id, "Sec Candidate", account_type="intern")
    cand_headers = {"Authorization": f"Bearer valid-user-{cand_id}"}

    # Create applied application
    db = TestingSessionLocal()
    try:
        app = Application(
            id=uuid4(),
            student_id=cand_profile.id,
            internship_id=UUID(listing_id),
            status="applied",
            applied_date=datetime.now(timezone.utc).date(),
        )
        db.add(app)
        db.commit()
        app_id = str(app.id)
    finally:
        db.close()

    # 1. Employer moves to 'interviewing'
    res1 = client.patch(
        f"/api/v1/internships/{listing_id}/applicants/{app_id}/status",
        json={"status": "interviewing", "notes": "Candidate invited for round 1 interview"},
        headers=emp_headers,
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "interviewing"

    # Candidate view reflects interviewing status
    cand_detail = client.get(f"/api/v1/applications/{app_id}", headers=cand_headers).json()
    assert cand_detail["status"] == "interviewing"
    assert len(cand_detail["timeline"]) == 1
    assert cand_detail["timeline"][0]["status"] == "interviewing"

    # 2. Employer moves to 'accepted'
    res2 = client.patch(
        f"/api/v1/internships/{listing_id}/applicants/{app_id}/status",
        json={"status": "accepted", "notes": "Offer extended and accepted"},
        headers=emp_headers,
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "accepted"

    # 3. Attempt to change from terminal accepted state -> 400
    res3 = client.patch(
        f"/api/v1/internships/{listing_id}/applicants/{app_id}/status",
        json={"status": "interviewing"},
        headers=emp_headers,
    )
    assert res3.status_code == 400
    err_detail = res3.json()["detail"].lower()
    assert "terminal" in err_detail or "cannot transition" in err_detail

    # 4. Test terminal 'rejected' state on another application with a distinct candidate
    cand2_id = uuid4()
    cand2_profile = _create_profile(cand2_id, "Sec Candidate 2", account_type="intern")

    db = TestingSessionLocal()
    try:
        app_rej = Application(
            id=uuid4(),
            student_id=cand2_profile.id,
            internship_id=UUID(listing_id),
            status="applied",
            applied_date=datetime.now(timezone.utc).date(),
        )
        db.add(app_rej)
        db.commit()
        rej_app_id = str(app_rej.id)
    finally:
        db.close()

    res_rej = client.patch(
        f"/api/v1/internships/{listing_id}/applicants/{rej_app_id}/status",
        json={"status": "rejected", "notes": "Position filled"},
        headers=emp_headers,
    )
    assert res_rej.status_code == 200
    assert res_rej.json()["status"] == "rejected"

    # Cannot transition terminal rejected -> 400
    res_rej_after = client.patch(
        f"/api/v1/internships/{listing_id}/applicants/{rej_app_id}/status",
        json={"status": "accepted"},
        headers=emp_headers,
    )
    assert res_rej_after.status_code == 400



def test_employer_interview_schedule_and_reschedule_is_canonical(
    client: TestClient,
):
    """Interview scheduling is canonical, isolated, reschedulable, and timeline-safe."""
    from datetime import timedelta

    employer_id = uuid4()
    other_employer_id = uuid4()
    candidate_id = uuid4()

    _create_profile(
        employer_id,
        "Interview Employer",
        account_type="employer",
    )
    _create_profile(
        other_employer_id,
        "Other Interview Employer",
        account_type="employer",
    )
    candidate_profile = _create_profile(
        candidate_id,
        "Interview Candidate",
        account_type="intern",
    )

    employer_headers = {
        "Authorization": f"Bearer valid-user-{employer_id}"
    }
    other_employer_headers = {
        "Authorization": f"Bearer valid-user-{other_employer_id}"
    }
    candidate_headers = {
        "Authorization": f"Bearer valid-user-{candidate_id}"
    }

    create_response = client.post(
        "/api/v1/internships",
        json={
            "title": "Interview Workflow Intern",
            "company": "Workflow Labs",
            "location": "Istanbul",
            "work_type": "hybrid",
            "description": "Test canonical interview scheduling.",
            "required_skills": ["Python"],
        },
        headers=employer_headers,
    )

    assert create_response.status_code == 201

    listing_id = UUID(create_response.json()["id"])

    db = TestingSessionLocal()
    try:
        application = Application(
            id=uuid4(),
            student_id=candidate_profile.id,
            internship_id=listing_id,
            status="applied",
            applied_date=datetime.now(timezone.utc).date(),
        )
        db.add(application)
        db.commit()
        application_id = str(application.id)
    finally:
        db.close()

    first_time = (
        datetime.now(timezone.utc)
        + timedelta(days=2)
    ).replace(microsecond=0)

    first_response = client.post(
        (
            f"/api/v1/internships/{listing_id}"
            f"/applicants/{application_id}/interview"
        ),
        json={
            "scheduled_at": first_time.isoformat(),
            "mode": "online",
            "location": "  https://meet.example.com/round-one  ",
            "message": "  Please prepare your portfolio.  ",
        },
        headers=employer_headers,
    )

    assert first_response.status_code == 200

    first_data = first_response.json()

    assert first_data["status"] == "interviewing"
    assert first_data["interview_mode"] == "online"
    assert (
        first_data["interview_location"]
        == "https://meet.example.com/round-one"
    )
    assert (
        first_data["interview_message"]
        == "Please prepare your portfolio."
    )
    assert first_data["interview_scheduled_at"] is not None

    candidate_response = client.get(
        f"/api/v1/applications/{application_id}",
        headers=candidate_headers,
    )

    assert candidate_response.status_code == 200

    candidate_data = candidate_response.json()

    assert candidate_data["status"] == "interviewing"
    assert candidate_data["interview_mode"] == "online"
    assert (
        candidate_data["interview_location"]
        == "https://meet.example.com/round-one"
    )
    assert (
        candidate_data["interview_message"]
        == "Please prepare your portfolio."
    )
    assert len(candidate_data["timeline"]) == 1
    assert candidate_data["timeline"][0]["status"] == "interviewing"

    isolated_response = client.post(
        (
            f"/api/v1/internships/{listing_id}"
            f"/applicants/{application_id}/interview"
        ),
        json={
            "scheduled_at": first_time.isoformat(),
            "mode": "online",
            "location": "https://example.com/not-allowed",
        },
        headers=other_employer_headers,
    )

    assert isolated_response.status_code == 404

    second_time = (
        datetime.now(timezone.utc)
        + timedelta(days=4)
    ).replace(microsecond=0)

    reschedule_response = client.post(
        (
            f"/api/v1/internships/{listing_id}"
            f"/applicants/{application_id}/interview"
        ),
        json={
            "scheduled_at": second_time.isoformat(),
            "mode": "onsite",
            "location": "  Workflow Labs, Istanbul  ",
            "message": "  Bring a photo ID.  ",
        },
        headers=employer_headers,
    )

    assert reschedule_response.status_code == 200

    rescheduled = reschedule_response.json()

    assert rescheduled["status"] == "interviewing"
    assert rescheduled["interview_mode"] == "onsite"
    assert (
        rescheduled["interview_location"]
        == "Workflow Labs, Istanbul"
    )
    assert (
        rescheduled["interview_message"]
        == "Bring a photo ID."
    )

    candidate_rescheduled_response = client.get(
        f"/api/v1/applications/{application_id}",
        headers=candidate_headers,
    )

    assert candidate_rescheduled_response.status_code == 200

    candidate_rescheduled = candidate_rescheduled_response.json()

    assert candidate_rescheduled["status"] == "interviewing"
    assert candidate_rescheduled["interview_mode"] == "onsite"
    assert (
        candidate_rescheduled["interview_location"]
        == "Workflow Labs, Istanbul"
    )
    assert (
        candidate_rescheduled["interview_message"]
        == "Bring a photo ID."
    )

    # Rescheduling must not append another interviewing event.
    assert len(candidate_rescheduled["timeline"]) == 1
    assert (
        candidate_rescheduled["timeline"][0]["status"]
        == "interviewing"
    )

    accept_response = client.patch(
        (
            f"/api/v1/internships/{listing_id}"
            f"/applicants/{application_id}/status"
        ),
        json={"status": "accepted"},
        headers=employer_headers,
    )

    assert accept_response.status_code == 200
    assert accept_response.json()["status"] == "accepted"

    terminal_response = client.post(
        (
            f"/api/v1/internships/{listing_id}"
            f"/applicants/{application_id}/interview"
        ),
        json={
            "scheduled_at": second_time.isoformat(),
            "mode": "online",
            "location": "https://example.com/should-fail",
        },
        headers=employer_headers,
    )

    assert terminal_response.status_code == 400
    assert "terminal" in terminal_response.json()["detail"].lower()



def test_employer_applicants_are_ranked_by_canonical_match_score(
    client: TestClient,
):
    """
    Employer applicant list is ranked by persisted canonical Match.overall_score,
    independent of application submission order.

    Also exposes authoritative matching/missing skill evidence.
    """
    employer_user_id = uuid4()

    _create_profile(
        employer_user_id,
        "Ranking Employer",
        account_type="employer",
    )

    headers = {
        "Authorization": f"Bearer valid-user-{employer_user_id}"
    }

    create_response = client.post(
        "/api/v1/internships",
        json={
            "title": "AI Ranking Intern",
            "company": "Ranking Labs",
            "location": "Istanbul",
            "work_type": "hybrid",
            "description": "Canonical candidate ranking test role.",
            "required_skills": ["Python", "FastAPI", "Docker"],
        },
        headers=headers,
    )

    assert create_response.status_code == 201

    listing_id = UUID(create_response.json()["id"])

    # Deliberately create applications in an order that does NOT match scores.
    candidate_specs = [
        (
            "Low Score Candidate",
            48,
            ["Python"],
            ["FastAPI", "Docker"],
        ),
        (
            "Top Score Candidate",
            91,
            ["Python", "FastAPI", "Docker"],
            [],
        ),
        (
            "Middle Score Candidate",
            74,
            ["Python", "FastAPI"],
            ["Docker"],
        ),
    ]

    db = TestingSessionLocal()

    try:
        for index, (
            name,
            score,
            matching_skills,
            missing_skills,
        ) in enumerate(candidate_specs):
            candidate_user_id = uuid4()

            profile = StudentProfile(
                id=uuid4(),
                user_id=candidate_user_id,
                full_name=name,
                headline="Ranking Candidate",
                preferences={
                    "account_type": "intern",
                    "department": "Computer Science",
                },
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            db.add(profile)
            db.flush()

            application = Application(
                id=uuid4(),
                student_id=profile.id,
                internship_id=listing_id,
                status="applied",
                applied_date=datetime.now(timezone.utc).date(),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            db.add(application)
            db.flush()

            match = Match(
                id=uuid4(),
                student_id=profile.id,
                internship_id=listing_id,
                overall_score=score,
                skill_score=score,
                vector_score=score,
                attribute_score=score,
                skill_gap_analysis={
                    "matching_skills": matching_skills,
                    "missing_skills": missing_skills,
                    "summary": "",
                    "recommendations": [],
                },
                created_at=datetime.now(timezone.utc),
            )

            db.add(match)

        db.commit()

    finally:
        db.close()

    response = client.get(
        f"/api/v1/internships/{listing_id}/applicants",
        headers=headers,
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["total"] == 3

    items = payload["items"]

    assert [item["match_score"] for item in items] == [
        91,
        74,
        48,
    ]

    assert [item["ai_rank"] for item in items] == [
        1,
        2,
        3,
    ]

    assert [
        item["candidate"]["full_name"]
        for item in items
    ] == [
        "Top Score Candidate",
        "Middle Score Candidate",
        "Low Score Candidate",
    ]

    assert items[0]["matching_skills"] == [
        "Python",
        "FastAPI",
        "Docker",
    ]
    assert items[0]["missing_skills"] == []

    # The employer explanation must expose the exact persisted Match
    # components used by the canonical ranking. No mobile-side recomputation
    # and no LLM-generated values are allowed here.
    assert items[0]["match_score"] == 91
    assert items[0]["skill_score"] == 91
    assert items[0]["vector_score"] == 91
    assert items[0]["attribute_score"] == 91

    assert items[1]["match_score"] == 74
    assert items[1]["skill_score"] == 74
    assert items[1]["vector_score"] == 74
    assert items[1]["attribute_score"] == 74

    assert items[2]["match_score"] == 48
    assert items[2]["skill_score"] == 48
    assert items[2]["vector_score"] == 48
    assert items[2]["attribute_score"] == 48


    assert items[1]["matching_skills"] == [
        "Python",
        "FastAPI",
    ]
    assert items[1]["missing_skills"] == [
        "Docker",
    ]

    assert items[2]["matching_skills"] == [
        "Python",
    ]
    assert items[2]["missing_skills"] == [
        "FastAPI",
        "Docker",
    ]

def test_employer_can_update_owned_opportunity_without_changing_ownership(client):
    from app.db.models import InternshipListing

    employer_id = uuid4()
    _create_profile(
        employer_id,
        "Update Employer",
        account_type="employer",
    )

    headers = {
        "Authorization": f"Bearer valid-user-{employer_id}"
    }

    create_response = client.post(
        "/api/v1/internships",
        json={
            "title": "Backend Intern",
            "company": "InternMatch Labs",
            "location": "Istanbul",
            "work_type": "hybrid",
            "description": "Build reliable backend services.",
            "required_skills": ["Python"],
            "preferred_skills": ["FastAPI"],
            "language": "English",
            "education_requirements": "Computer Engineering student",
            "experience_requirements": "Entry level",
        },
        headers=headers,
    )

    assert create_response.status_code == 201

    created = create_response.json()
    listing_id = created["id"]

    update_response = client.patch(
        f"/api/v1/internships/{listing_id}",
        json={
            "title": "Platform Engineering Intern",
            "company": "InternMatch Labs",
            "location": "Remote",
            "work_type": "remote",
            # Keep description unchanged so this ownership-focused test does
            # not depend on an additional embedding provider call.
            "description": "Build reliable backend services.",
            "required_skills": ["Python", "PostgreSQL"],
            "preferred_skills": ["FastAPI", "Docker"],
            "language": "English",
            "education_requirements": "Engineering student",
            "experience_requirements": "No prior professional experience required",
        },
        headers=headers,
    )

    assert update_response.status_code == 200

    updated = update_response.json()

    assert updated["id"] == listing_id
    assert updated["title"] == "Platform Engineering Intern"
    assert updated["company"] == "InternMatch Labs"
    assert updated["location"] == "Remote"
    assert updated["work_type"] == "remote"
    assert updated["description"] == "Build reliable backend services."
    assert updated["required_skills"] == ["Python", "PostgreSQL"]
    assert updated["preferred_skills"] == ["FastAPI", "Docker"]
    assert updated["languages"] == ["English"]
    assert updated["min_education"] == "Engineering student"
    assert (
        updated["experience_requirements"]
        == "No prior professional experience required"
    )
    assert updated["is_active"] is True

    with TestingSessionLocal() as db:
        listing = db.get(InternshipListing, UUID(listing_id))

        assert listing is not None
        assert listing.employer_user_id == employer_id
        assert listing.is_active is True


def test_employer_cannot_update_another_employers_opportunity(client):
    from app.db.models import InternshipListing

    owner_id = uuid4()
    attacker_id = uuid4()

    _create_profile(
        owner_id,
        "Owner Employer",
        account_type="employer",
    )
    _create_profile(
        attacker_id,
        "Other Employer",
        account_type="employer",
    )

    owner_headers = {
        "Authorization": f"Bearer valid-user-{owner_id}"
    }
    attacker_headers = {
        "Authorization": f"Bearer valid-user-{attacker_id}"
    }

    create_response = client.post(
        "/api/v1/internships",
        json={
            "title": "Protected Internship",
            "company": "Owner Company",
            "location": "Istanbul",
            "work_type": "hybrid",
            "description": "Ownership isolation test opportunity.",
            "required_skills": ["Python"],
            "preferred_skills": [],
            "language": "English",
            "education_requirements": None,
            "experience_requirements": None,
        },
        headers=owner_headers,
    )

    assert create_response.status_code == 201

    listing_id = create_response.json()["id"]

    forbidden_update = client.patch(
        f"/api/v1/internships/{listing_id}",
        json={
            "title": "Hijacked Internship",
            "company": "Other Company",
            "location": "Remote",
            "work_type": "remote",
            "description": "Ownership isolation test opportunity.",
            "required_skills": ["Go"],
            "preferred_skills": [],
            "language": "English",
            "education_requirements": None,
            "experience_requirements": None,
        },
        headers=attacker_headers,
    )

    # Deliberately return not-found semantics so listing ownership is not
    # disclosed to another employer.
    assert forbidden_update.status_code == 404

    with TestingSessionLocal() as db:
        listing = db.get(InternshipListing, UUID(listing_id))

        assert listing is not None
        assert listing.employer_user_id == owner_id
        assert listing.title == "Protected Internship"
        assert listing.company == "Owner Company"
        assert listing.location == "Istanbul"
        assert listing.work_type == "hybrid"
        assert listing.required_skills == ["Python"]
        assert listing.is_active is True

def test_update_opportunity_requires_authentication_and_employer_role(client):
    owner_id = uuid4()
    candidate_id = uuid4()

    _create_profile(
        owner_id,
        "Security Owner",
        account_type="employer",
    )
    _create_profile(
        candidate_id,
        "Security Candidate",
        account_type="intern",
    )

    owner_headers = {
        "Authorization": f"Bearer valid-user-{owner_id}"
    }
    candidate_headers = {
        "Authorization": f"Bearer valid-user-{candidate_id}"
    }

    create_response = client.post(
        "/api/v1/internships",
        json={
            "title": "Security Internship",
            "company": "Secure Company",
            "location": "Istanbul",
            "work_type": "hybrid",
            "description": "Security authorization test opportunity.",
            "required_skills": ["Python"],
            "preferred_skills": [],
            "language": "English",
            "education_requirements": None,
            "experience_requirements": None,
        },
        headers=owner_headers,
    )

    assert create_response.status_code == 201

    listing_id = create_response.json()["id"]

    update_payload = {
        "title": "Unauthorized Mutation Attempt",
        "company": "Secure Company",
        "location": "Remote",
        "work_type": "remote",
        "description": "Security authorization test opportunity.",
        "required_skills": ["Python"],
        "preferred_skills": [],
        "language": "English",
        "education_requirements": None,
        "experience_requirements": None,
    }

    unauthenticated = client.patch(
        f"/api/v1/internships/{listing_id}",
        json=update_payload,
    )

    assert unauthenticated.status_code == 401

    candidate_attempt = client.patch(
        f"/api/v1/internships/{listing_id}",
        json=update_payload,
        headers=candidate_headers,
    )

    assert candidate_attempt.status_code == 403

    db = TestingSessionLocal()
    try:
        listing = db.get(InternshipListing, UUID(listing_id))

        assert listing is not None
        assert listing.employer_user_id == owner_id
        assert listing.title == "Security Internship"
        assert listing.company == "Secure Company"
        assert listing.location == "Istanbul"
        assert listing.work_type == "hybrid"
        assert listing.is_active is True
    finally:
        db.close()

def test_employer_applicant_detail_uses_same_canonical_match_components(client):
    employer_id = uuid4()
    candidate_id = uuid4()

    _create_profile(
        employer_id,
        "Detail Explainability Employer",
        account_type="employer",
    )

    candidate_profile = _create_profile(
        candidate_id,
        "Grounded Detail Candidate",
        account_type="intern",
        preferences={"department": "Computer Engineering"},
    )

    headers = {
        "Authorization": f"Bearer valid-user-{employer_id}"
    }

    create_response = client.post(
        "/api/v1/internships",
        json={
            "title": "Grounded Ranking Intern",
            "company": "Grounded Labs",
            "location": "Remote",
            "work_type": "remote",
            "description": "Grounded employer explanation detail test.",
            "required_skills": ["Python", "FastAPI"],
            "preferred_skills": ["Docker"],
        },
        headers=headers,
    )

    assert create_response.status_code == 201
    listing_id = UUID(create_response.json()["id"])

    db = TestingSessionLocal()
    try:
        application = Application(
            id=uuid4(),
            student_id=candidate_profile.id,
            internship_id=listing_id,
            status="applied",
            applied_date=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(application)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=candidate_profile.id,
            internship_id=listing_id,
            overall_score=82,
            skill_score=90,
            vector_score=76,
            attribute_score=70,
            skill_gap_analysis={
                "matching_skills": ["Python", "FastAPI"],
                "missing_skills": ["Docker"],
                "summary": "",
                "recommendations": [],
            },
            created_at=datetime.now(timezone.utc),
        )
        db.add(match)
        db.commit()

        application_id = application.id
    finally:
        db.close()

    detail_response = client.get(
        f"/api/v1/internships/{listing_id}/applicants/{application_id}",
        headers=headers,
    )

    assert detail_response.status_code == 200

    detail = detail_response.json()

    assert detail["match_score"] == 82
    assert detail["skill_score"] == 90
    assert detail["vector_score"] == 76
    assert detail["attribute_score"] == 70

    assert detail["matching_skills"] == [
        "Python",
        "FastAPI",
    ]
    assert detail["missing_skills"] == [
        "Docker",
    ]

    # Employer-facing explanation must not expose internal ownership identifiers
    # outside the intentional candidate summary contract.
    assert "employer_user_id" not in detail


def test_employer_unscored_applicant_has_no_fabricated_score_breakdown(client):
    employer_id = uuid4()
    candidate_id = uuid4()

    _create_profile(
        employer_id,
        "Unscored Explainability Employer",
        account_type="employer",
    )

    candidate_profile = _create_profile(
        candidate_id,
        "Unscored Candidate",
        account_type="intern",
    )

    headers = {
        "Authorization": f"Bearer valid-user-{employer_id}"
    }

    create_response = client.post(
        "/api/v1/internships",
        json={
            "title": "Unscored Candidate Intern",
            "company": "Explainability Labs",
            "location": "Remote",
            "work_type": "remote",
            "description": "Verify that employer explanations never fabricate scores.",
            "required_skills": ["Python"],
            "preferred_skills": ["Docker"],
        },
        headers=headers,
    )

    assert create_response.status_code == 201
    listing_id = UUID(create_response.json()["id"])

    db = TestingSessionLocal()
    try:
        application = Application(
            id=uuid4(),
            student_id=candidate_profile.id,
            internship_id=listing_id,
            status="applied",
            applied_date=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(application)
        db.commit()

        application_id = application.id
    finally:
        db.close()

    list_response = client.get(
        f"/api/v1/internships/{listing_id}/applicants",
        headers=headers,
    )

    assert list_response.status_code == 200

    items = list_response.json()["items"]
    assert len(items) == 1

    applicant = items[0]

    assert applicant["match_score"] is None
    assert applicant["skill_score"] is None
    assert applicant["vector_score"] is None
    assert applicant["attribute_score"] is None
    assert applicant["ai_rank"] is None
    assert applicant["matching_skills"] == []
    assert applicant["missing_skills"] == []

    detail_response = client.get(
        f"/api/v1/internships/{listing_id}/applicants/{application_id}",
        headers=headers,
    )

    assert detail_response.status_code == 200

    detail = detail_response.json()

    assert detail["match_score"] is None
    assert detail["skill_score"] is None
    assert detail["vector_score"] is None
    assert detail["attribute_score"] is None
    assert detail["matching_skills"] == []
    assert detail["missing_skills"] == []
