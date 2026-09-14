"""
Pytest Test Suite Configuration & Fixtures
Provides shared test fixtures, app TestClient, and test database config.
"""

import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is in Python path for test execution
backend_dir = Path(__file__).parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings  # noqa: E402
from app.db.models import (  # noqa: E402,F401
    Application,
    ApplicationStatusEvent,
    EducationEntry,
    EmployerOrganization,
    EmployerVerificationEvent,
    ExperienceEntry,
    InternshipListing,
    Match,
    ProcessingJob,
    ProjectEntry,
    RevenueCatWebhookEvent,
    SavedInternship,
    Skill,
    StudentProfile,
    StudentSkill,
    SubscriptionEntitlement,
)
from app.db.session import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

from tests.db import TestingSessionLocal, test_engine  # noqa: E402

TEST_SUPABASE_URL = "https://legitimate-project.supabase.co"
TEST_SUPABASE_PUBLISHABLE_KEY = "test_supabase_publishable_key_for_testing"


def override_get_db():
    """Override get_db dependency to use the shared SQLite test database."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def route_ai_telemetry_to_test_database(monkeypatch):
    """Route best-effort AI telemetry writes to shared SQLite tests."""

    monkeypatch.setattr(
        "app.services.ai_telemetry.SessionLocal",
        TestingSessionLocal,
    )


@pytest.fixture(autouse=True)
def configure_test_jwt_settings():
    """Configure shared test Supabase URL and publishable key for all test modules."""
    original_url = settings.SUPABASE_URL
    original_pub_key = settings.SUPABASE_PUBLISHABLE_KEY

    settings.SUPABASE_URL = TEST_SUPABASE_URL
    settings.SUPABASE_PUBLISHABLE_KEY = TEST_SUPABASE_PUBLISHABLE_KEY

    yield

    settings.SUPABASE_URL = original_url
    settings.SUPABASE_PUBLISHABLE_KEY = original_pub_key


@pytest.fixture
def mock_supabase_auth(monkeypatch):
    """
    Explicit fixture to mock Supabase verified claims for authenticated endpoint testing.
    Maps bearer token strings to verified claims payloads.
    """
    claims_registry = {}

    def register_token(
        token: str,
        claims: Optional[dict] = None,
        exc: Optional[Exception] = None,
    ):
        claims_registry[token] = (claims, exc)

    mock_client = MagicMock()

    def get_claims(jwt=None, jwks=None):
        token = jwt
        if not token:
            raise RuntimeError("Missing token")

        if token in claims_registry:
            claims, exc = claims_registry[token]
            if exc is not None:
                raise exc
            if claims is None:
                return None
            return {
                "claims": claims,
                "headers": {"alg": "ES256", "typ": "JWT"},
                "signature": b"mock_signature",
            }

        if token.startswith("valid-user-"):
            user_id_str = token[len("valid-user-") :]
            return {
                "claims": {
                    "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
                    "aud": "authenticated",
                    "sub": user_id_str,
                    "email": "student@example.com",
                    "role": "authenticated",
                },
                "headers": {"alg": "ES256", "typ": "JWT"},
                "signature": b"mock_signature",
            }

        raise RuntimeError("Invalid or unverified authentication token.")

    mock_client.auth.get_claims.side_effect = get_claims
    monkeypatch.setattr(
        "app.core.security.create_client",
        lambda url, key: mock_client,
    )
    return register_token


@pytest.fixture(autouse=True)
def setup_test_database():
    """Create all registered SQLAlchemy tables and configure the DB override."""
    required_tables = [
        "student_profiles",
        "skills",
        "student_skills",
        "education_entries",
        "experience_entries",
        "project_entries",
        "employer_organizations",
        "employer_verification_events",
        "internship_listings",
        "processing_jobs",
        "subscription_entitlements",
        "revenuecat_webhook_events",
        "matches",
        "applications",
        "application_status_events",
        "saved_internships",
    ]
    for table_name in required_tables:
        if table_name not in Base.metadata.tables:
            raise RuntimeError(
                f"Required table {table_name} is not registered in Base.metadata before test setup."
            )

    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db

    yield

    app.dependency_overrides.pop(get_db, None)


def _clear_shared_test_database() -> None:
    """Delete all test rows in foreign-key-safe dependency order."""
    with test_engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture(autouse=True)
def isolate_shared_test_database(setup_test_database):
    """Prevent committed rows from leaking between tests in the shared SQLite database."""
    _clear_shared_test_database()
    try:
        yield
    finally:
        _clear_shared_test_database()


@pytest.fixture
def client() -> TestClient:
    """Fixture providing FastAPI TestClient instance."""
    return TestClient(app)
