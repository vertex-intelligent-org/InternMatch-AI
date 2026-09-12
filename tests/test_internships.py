"""
Unit and Integration Tests for Internship Catalog Endpoints
Validates GET /api/v1/internships and GET /api/v1/internships/{id}.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.db.models import InternshipListing
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal


@pytest.fixture(autouse=True)
def clean_internships_table():
    """Ensure internship_listings table is cleared before and after each test."""
    db = TestingSessionLocal()
    try:
        db.query(InternshipListing).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = TestingSessionLocal()
    try:
        db.query(InternshipListing).delete()
        db.commit()
    finally:
        db.close()


def test_list_internships_empty_catalog(client: TestClient):
    """Verify GET /api/v1/internships returns empty catalog contract response
    when table is empty."""
    response = client.get("/api/v1/internships")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["limit"] == 20
    assert data["offset"] == 0


def test_list_internships_pagination_and_sorting(client: TestClient):
    """Verify pagination limit, offset, total count, and sorting by posted_at desc."""
    db = TestingSessionLocal()
    try:
        for i in range(5):
            listing = InternshipListing(
                publication_status="published",
                is_active=True,
                listing_source="curated",
                id=uuid4(),
                title=f"Engineer Intern {i}",
                company="TechCorp",
                location="Remote",
                work_type="remote",
                description=f"Description {i}",
                required_skills=["Python"],
                preferred_skills=["Docker"],
                created_at=datetime(2026, 8, i + 1, tzinfo=timezone.utc),
            )
            db.add(listing)
        db.commit()
    finally:
        db.close()

    # Default pagination: limit=20, offset=0
    response = client.get("/api/v1/internships")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5
    # First item should be the newest (created_at Aug 5)
    assert data["items"][0]["title"] == "Engineer Intern 4"

    # Custom limit and offset
    response_paged = client.get("/api/v1/internships?limit=2&offset=1")
    assert response_paged.status_code == 200
    data_paged = response_paged.json()
    assert data_paged["total"] == 5
    assert len(data_paged["items"]) == 2
    assert data_paged["limit"] == 2
    assert data_paged["offset"] == 1
    assert data_paged["items"][0]["title"] == "Engineer Intern 3"


def test_list_internships_filters(client: TestClient):
    """Verify filtering by work_type, location, and skill."""
    db = TestingSessionLocal()
    try:
        listing1 = InternshipListing(
            publication_status="published",
            is_active=True,
            listing_source="curated",
            id=uuid4(),
            title="Backend Intern",
            company="CloudCorp",
            location="San Francisco, CA",
            work_type="remote",
            description="Backend python development",
            required_skills=["Python", "FastAPI"],
            preferred_skills=["Redis"],
        )
        listing2 = InternshipListing(
            publication_status="published",
            is_active=True,
            listing_source="curated",
            id=uuid4(),
            title="Frontend Intern",
            company="Web Corp",
            location="New York, NY",
            work_type="hybrid",
            description="Frontend React development",
            required_skills=["TypeScript", "React"],
            preferred_skills=["CSS"],
        )
        listing3 = InternshipListing(
            publication_status="published",
            is_active=True,
            listing_source="curated",
            id=uuid4(),
            title="DevOps Intern",
            company="Ops Solutions",
            location="Austin, TX",
            work_type="onsite",
            description="Infrastructure operations",
            required_skills=["Docker", "AWS"],
            preferred_skills=["Python"],
        )
        db.add_all([listing1, listing2, listing3])
        db.commit()
    finally:
        db.close()

    # Filter by work_type
    res_work = client.get("/api/v1/internships?work_type=remote")
    assert res_work.status_code == 200
    data_work = res_work.json()
    assert data_work["total"] == 1
    assert data_work["items"][0]["title"] == "Backend Intern"

    # Filter by location substring
    res_loc = client.get("/api/v1/internships?location=york")
    assert res_loc.status_code == 200
    data_loc = res_loc.json()
    assert data_loc["total"] == 1
    assert data_loc["items"][0]["title"] == "Frontend Intern"

    # Filter by skill (required or preferred skill)
    res_skill = client.get("/api/v1/internships?skill=python")
    assert res_skill.status_code == 200
    data_skill = res_skill.json()
    assert data_skill["total"] == 2
    titles = [item["title"] for item in data_skill["items"]]
    assert "Backend Intern" in titles
    assert "DevOps Intern" in titles


def test_get_internship_by_id_success_and_boundary_mapping(client: TestClient):
    """
    Verify detail boundary mapping:
    created_at->posted_at, language->languages,
    education_requirements->min_education.
    """
    listing_id = uuid4()
    created_time = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)

    db = TestingSessionLocal()
    try:
        listing = InternshipListing(
            publication_status="published",
            is_active=True,
            listing_source="curated",
            id=listing_id,
            title="AI Engineer Intern",
            company="NexaAI",
            location="Remote",
            work_type="remote",
            description="Build modern LLM RAG pipelines.",
            required_skills=["Python", "PyTorch"],
            preferred_skills=["Docker"],
            language="English",
            education_requirements="Bachelor Student in Computer Science",
            experience_requirements="Python experience",
            created_at=created_time,
        )
        db.add(listing)
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/v1/internships/{listing_id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(listing_id)
    assert data["title"] == "AI Engineer Intern"
    assert data["company"] == "NexaAI"
    assert data["location"] == "Remote"
    assert data["work_type"] == "remote"
    assert data["description"] == "Build modern LLM RAG pipelines."
    assert data["required_skills"] == ["Python", "PyTorch"]
    assert data["preferred_skills"] == ["Docker"]

    assert data["languages"] == ["English"]
    assert data["min_education"] == "Bachelor Student in Computer Science"
    assert "posted_at" in data
    assert data["posted_at"].startswith("2026-08-10T12:00:00")


def test_get_internship_by_id_not_found(client: TestClient):
    """
    Verify detail endpoint returns machine-readable 404
    error payload for an unknown UUID.
    """
    unknown_id = uuid4()

    response = client.get(f"/api/v1/internships/{unknown_id}")

    assert response.status_code == 404
    data = response.json()

    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "message" in data["error"]
    assert "timestamp" in data["error"]


def test_get_internship_by_id_locale_defaults_and_en(client: TestClient):
    """Verify default query and explicit locale=en return canonical content."""
    listing_id = uuid4()
    db = TestingSessionLocal()
    try:
        listing = InternshipListing(
            publication_status="published",
            is_active=True,
            listing_source="curated",
            id=listing_id,
            title="Backend Engineering Intern",
            company="DataScale Inc",
            location="Remote",
            work_type="remote",
            description="Build scalable distributed services.",
            required_skills=["Python", "FastAPI"],
            preferred_skills=["Redis"],
            language="English",
            education_requirements="Computer Science Major",
            created_at=datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc),
        )
        db.add(listing)
        db.commit()
    finally:
        db.close()

    # 1. No locale query parameter
    res_default = client.get(f"/api/v1/internships/{listing_id}")
    assert res_default.status_code == 200
    data_default = res_default.json()
    assert data_default["description"] == "Build scalable distributed services."
    assert data_default["min_education"] == "Computer Science Major"

    # 2. Explicit locale=en
    res_en = client.get(f"/api/v1/internships/{listing_id}?locale=en")
    assert res_en.status_code == 200
    data_en = res_en.json()
    assert data_en["description"] == "Build scalable distributed services."
    assert data_en["min_education"] == "Computer Science Major"


def test_get_internship_by_id_locale_tr_translated_with_canonical_invariants(
    client: TestClient, monkeypatch
):
    """
    Verify locale=tr returns translated description and min_education while strictly
    preserving title, company, location, work_type, skills, and languages canonical.
    """
    listing_id = uuid4()
    db = TestingSessionLocal()
    try:
        listing = InternshipListing(
            publication_status="published",
            is_active=True,
            listing_source="curated",
            id=listing_id,
            title="AI Engineer Intern",
            company="NexaAI",
            location="Istanbul, Turkey",
            work_type="hybrid",
            description="Build modern LLM RAG pipelines.",
            required_skills=["Python", "PyTorch"],
            preferred_skills=["Docker"],
            language="English",
            education_requirements="Bachelor Student in Computer Science",
            created_at=datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        db.add(listing)
        db.commit()
    finally:
        db.close()

    # Mock service layer to return translated content
    def mock_translate(*args, **kwargs):
        return (
            "Modern LLM RAG boru hatlari gelistirin.",
            "Bilgisayar Muhendisligi Lisans Ogrencisi",
        )

    monkeypatch.setattr(
        "app.api.v1.endpoints.internships.translate_internship_content",
        mock_translate,
    )

    response = client.get(f"/api/v1/internships/{listing_id}?locale=tr")
    assert response.status_code == 200
    data = response.json()

    # Translated fields
    assert data["description"] == "Modern LLM RAG boru hatlari gelistirin."
    assert data["min_education"] == "Bilgisayar Muhendisligi Lisans Ogrencisi"

    # Canonical invariant fields MUST NOT CHANGE
    assert data["id"] == str(listing_id)
    assert data["title"] == "AI Engineer Intern"
    assert data["company"] == "NexaAI"
    assert data["location"] == "Istanbul, Turkey"
    assert data["work_type"] == "hybrid"
    assert data["required_skills"] == ["Python", "PyTorch"]
    assert data["preferred_skills"] == ["Docker"]
    assert data["languages"] == ["English"]


def test_get_internship_by_id_locale_ar_translated_with_canonical_invariants(
    client: TestClient, monkeypatch
):
    """
    Verify locale=ar returns translated description and min_education while strictly
    preserving canonical metadata fields.
    """
    listing_id = uuid4()
    db = TestingSessionLocal()
    try:
        listing = InternshipListing(
            publication_status="published",
            is_active=True,
            listing_source="curated",
            id=listing_id,
            title="Fullstack Developer Intern",
            company="AppWorks",
            location="Dubai, UAE",
            work_type="onsite",
            description="Develop interactive web and mobile applications.",
            required_skills=["React", "Node.js"],
            preferred_skills=["GraphQL"],
            language="English",
            education_requirements="Computer Engineering Degree",
            created_at=datetime(2026, 8, 16, 14, 0, 0, tzinfo=timezone.utc),
        )
        db.add(listing)
        db.commit()
    finally:
        db.close()

    def mock_translate(*args, **kwargs):
        return (
            "تطوير تطبيقات الويب والهاتف التفاعلية.",
            "شهادة في هندسة الحاسوب",
        )

    monkeypatch.setattr(
        "app.api.v1.endpoints.internships.translate_internship_content",
        mock_translate,
    )

    response = client.get(f"/api/v1/internships/{listing_id}?locale=ar")
    assert response.status_code == 200
    data = response.json()

    assert data["description"] == "تطوير تطبيقات الويب والهاتف التفاعلية."
    assert data["min_education"] == "شهادة في هندسة الحاسوب"
    assert data["title"] == "Fullstack Developer Intern"
    assert data["company"] == "AppWorks"


def test_get_internship_by_id_invalid_locale_rejected(client: TestClient):
    """Verify framework validation rejects invalid locale values with HTTP 422."""
    listing_id = uuid4()
    db = TestingSessionLocal()
    try:
        listing = InternshipListing(
            publication_status="published",
            is_active=True,
            listing_source="curated",
            id=listing_id,
            title="Intern",
            company="Company",
            location="Remote",
            work_type="remote",
            description="Description",
            created_at=datetime.now(timezone.utc),
        )
        db.add(listing)
        db.commit()
    finally:
        db.close()

    res_invalid = client.get(f"/api/v1/internships/{listing_id}?locale=fr")
    assert res_invalid.status_code == 422

    res_malformed = client.get(f"/api/v1/internships/{listing_id}?locale=xyz123")
    assert res_malformed.status_code == 422


def test_get_internship_by_id_translation_fallback_on_service_failure(
    client: TestClient, monkeypatch
):
    """
    Verify that when translation service returns canonical (due to provider or redis failure),
    the endpoint returns HTTP 200 with canonical content and zero provider error leakage.
    """
    listing_id = uuid4()
    db = TestingSessionLocal()
    try:
        listing = InternshipListing(
            publication_status="published",
            is_active=True,
            listing_source="curated",
            id=listing_id,
            title="Data Science Intern",
            company="AnalyticsLab",
            location="Remote",
            work_type="remote",
            description="Canonical original English description.",
            education_requirements="Canonical English Education",
            created_at=datetime.now(timezone.utc),
        )
        db.add(listing)
        db.commit()
    finally:
        db.close()

    # Simulate translation service failure returning canonical fallback
    def mock_translate_fallback(internship_id, description, min_education, target_locale):
        return description, min_education

    monkeypatch.setattr(
        "app.api.v1.endpoints.internships.translate_internship_content",
        mock_translate_fallback,
    )

    response = client.get(f"/api/v1/internships/{listing_id}?locale=tr")
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "Canonical original English description."
    assert data["min_education"] == "Canonical English Education"
