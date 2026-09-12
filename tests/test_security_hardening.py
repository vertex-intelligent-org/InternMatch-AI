"""
Security Boundary Hardening & Validation Tests (Gate 2.30A).
Covers production fail-fast configuration validation, safe client-visible
error persistence across all async enqueue & worker execution paths,
and worker Redis logging credential protection.
"""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

# Ensure worker is on sys.path for worker-level testing
worker_dir = Path(__file__).parent.parent / "worker"
if str(worker_dir) not in sys.path:
    sys.path.insert(0, str(worker_dir))

from app.core.config import (  # noqa: E402
    Settings,
    validate_production_config,
)
from app.db.models import (  # noqa: E402
    InternshipListing,
    Match,
    ProcessingJob,
    StudentProfile,
)
from app.repositories.processing_job import (  # noqa: E402
    ProcessingJobRepository,
)
from tasks.application_generation import (  # noqa: E402
    run_application_generation,
)
from tasks.cv_extraction import (  # noqa: E402
    run_cv_extraction,
)
from tasks.match_calculation import (  # noqa: E402
    run_match_calculation,
)

from tests.db import TestingSessionLocal  # noqa: E402
from worker import run_worker  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    """Ensure all related tables are cleared before and after each test."""
    db = TestingSessionLocal()
    try:
        db.query(Match).delete()
        db.query(ProcessingJob).delete()
        db.query(StudentProfile).delete()
        db.query(InternshipListing).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = TestingSessionLocal()
    try:
        db.query(Match).delete()
        db.query(ProcessingJob).delete()
        db.query(StudentProfile).delete()
        db.query(InternshipListing).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def override_worker_sessionlocal(monkeypatch):
    """Ensure worker tasks use test SQLite engine instead of production SessionLocal."""
    monkeypatch.setattr("tasks.match_calculation.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("tasks.cv_extraction.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("tasks.application_generation.SessionLocal", TestingSessionLocal)


# ---------------------------------------------------------------------------
# A. PRODUCTION CONFIGURATION FAIL-FAST TESTS (1 - 11)
# ---------------------------------------------------------------------------


def test_development_config_validation_is_noop():
    """Test 1: validate_production_config is a no-op when ENVIRONMENT != production."""
    dev_cfg = Settings(
        ENVIRONMENT="development",
        SUPABASE_URL="https://placeholder.supabase.co",
        SUPABASE_SERVICE_ROLE_KEY="",
        SUPABASE_JWT_SECRET="short",
        DATABASE_URL="postgresql://placeholder",
        REDIS_URL="redis://placeholder",
        GEMINI_API_KEY="",
        CV_STORAGE_BUCKET="",
        ALLOWED_ORIGINS="*",
    )
    # Must not raise in development
    validate_production_config(dev_cfg)


def test_production_config_with_placeholder_supabase_url_fails():
    """Test 2: Production config with placeholder SUPABASE_URL fails."""
    cfg = Settings(
        ENVIRONMENT="production",
        SUPABASE_URL="https://placeholder-project.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="valid_pub_key_for_prod",
        SUPABASE_SERVICE_ROLE_KEY="valid_serv_role_secret_for_prod",
        DATABASE_URL="postgresql://user:pass@db.real.co:5432/db",
        REDIS_URL="redis://default:pass@redis.real.co:6379/0",
        GEMINI_API_KEY="gemini-real-secret-key-for-prod",
        CV_STORAGE_BUCKET="cvs",
        ALLOWED_ORIGINS="https://app.internmatch.ai",
    )
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        validate_production_config(cfg)


def test_production_config_with_missing_service_role_fails():
    """Test 3: Production config with missing/placeholder SERVICE_ROLE fails."""
    cfg = Settings(
        ENVIRONMENT="production",
        SUPABASE_URL="https://real-project.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="valid_pub_key_for_prod",
        SUPABASE_SERVICE_ROLE_KEY="sb_serv_placeholder_key_server_only",
        DATABASE_URL="postgresql://user:pass@db.real.co:5432/db",
        REDIS_URL="redis://default:pass@redis.real.co:6379/0",
        GEMINI_API_KEY="gemini-real-secret-key-for-prod",
        CV_STORAGE_BUCKET="cvs",
        ALLOWED_ORIGINS="https://app.internmatch.ai",
    )
    with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_ROLE_KEY"):
        validate_production_config(cfg)


def test_production_config_with_missing_publishable_key_fails():
    """Test 4: Production config with missing/placeholder SUPABASE_PUBLISHABLE_KEY fails."""
    cfg_empty = Settings(
        ENVIRONMENT="production",
        SUPABASE_URL="https://real-project.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="",
        SUPABASE_SERVICE_ROLE_KEY="valid_serv_role_secret_for_prod",
        DATABASE_URL="postgresql://user:pass@db.real.co:5432/db",
        REDIS_URL="redis://default:pass@redis.real.co:6379/0",
        GEMINI_API_KEY="gemini-real-secret-key-for-prod",
        CV_STORAGE_BUCKET="cvs",
        ALLOWED_ORIGINS="https://app.internmatch.ai",
    )
    with pytest.raises(RuntimeError, match="SUPABASE_PUBLISHABLE_KEY"):
        validate_production_config(cfg_empty)

    cfg_placeholder = Settings(
        ENVIRONMENT="production",
        SUPABASE_URL="https://real-project.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_pub_placeholder_key_for_client_side",
        SUPABASE_SERVICE_ROLE_KEY="valid_serv_role_secret_for_prod",
        DATABASE_URL="postgresql://user:pass@db.real.co:5432/db",
        REDIS_URL="redis://default:pass@redis.real.co:6379/0",
        GEMINI_API_KEY="gemini-real-secret-key-for-prod",
        CV_STORAGE_BUCKET="cvs",
        ALLOWED_ORIGINS="https://app.internmatch.ai",
    )
    with pytest.raises(RuntimeError, match="SUPABASE_PUBLISHABLE_KEY"):
        validate_production_config(cfg_placeholder)


def test_production_config_with_placeholder_database_url_fails():
    """Test 5: Production config with placeholder DATABASE_URL fails."""
    cfg = Settings(
        ENVIRONMENT="production",
        SUPABASE_URL="https://real-project.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="valid_pub_key_for_prod",
        SUPABASE_SERVICE_ROLE_KEY="valid_serv_role_secret_for_prod",
        DATABASE_URL=(
            "postgresql://postgres:placeholder_password@"
            "placeholder_project.supabase.co:5432/postgres"
        ),
        REDIS_URL="redis://default:pass@redis.real.co:6379/0",
        GEMINI_API_KEY="gemini-real-secret-key-for-prod",
        CV_STORAGE_BUCKET="cvs",
        ALLOWED_ORIGINS="https://app.internmatch.ai",
    )
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        validate_production_config(cfg)


def test_production_config_with_placeholder_redis_url_fails():
    """Test 6: Production config with placeholder REDIS_URL fails."""
    cfg = Settings(
        ENVIRONMENT="production",
        SUPABASE_URL="https://real-project.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="valid_pub_key_for_prod",
        SUPABASE_SERVICE_ROLE_KEY="valid_serv_role_secret_for_prod",
        DATABASE_URL="postgresql://user:pass@db.real.co:5432/db",
        REDIS_URL="redis://placeholder-redis:6379/0",
        GEMINI_API_KEY="gemini-real-secret-key-for-prod",
        CV_STORAGE_BUCKET="cvs",
        ALLOWED_ORIGINS="https://app.internmatch.ai",
    )
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        validate_production_config(cfg)


def test_production_config_with_missing_gemini_key_fails():
    """Test 7: Production config with missing/placeholder GEMINI_API_KEY fails."""
    cfg = Settings(
        ENVIRONMENT="production",
        SUPABASE_URL="https://real-project.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="valid_pub_key_for_prod",
        SUPABASE_SERVICE_ROLE_KEY="valid_serv_role_secret_for_prod",
        DATABASE_URL="postgresql://user:pass@db.real.co:5432/db",
        REDIS_URL="redis://default:pass@redis.real.co:6379/0",
        GEMINI_API_KEY="gemini-placeholder-key-server-only",
        CV_STORAGE_BUCKET="cvs",
        ALLOWED_ORIGINS="https://app.internmatch.ai",
    )
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        validate_production_config(cfg)


def test_production_config_with_empty_cv_bucket_fails():
    """Test 8: Production config with empty CV_STORAGE_BUCKET fails."""
    cfg = Settings(
        ENVIRONMENT="production",
        SUPABASE_URL="https://real-project.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="valid_pub_key_for_prod",
        SUPABASE_SERVICE_ROLE_KEY="valid_serv_role_secret_for_prod",
        DATABASE_URL="postgresql://user:pass@db.real.co:5432/db",
        REDIS_URL="redis://default:pass@redis.real.co:6379/0",
        GEMINI_API_KEY="gemini-real-secret-key-for-prod",
        CV_STORAGE_BUCKET="",
        ALLOWED_ORIGINS="https://app.internmatch.ai",
    )
    with pytest.raises(RuntimeError, match="CV_STORAGE_BUCKET"):
        validate_production_config(cfg)


@pytest.mark.parametrize(
    "invalid_origin",
    [
        "*",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://insecure.app.com",
    ],
)
def test_production_config_with_insecure_origins_fails(invalid_origin):
    """Test 9: Production config with wildcard, localhost, or non-HTTPS origins fails."""
    cfg = Settings(
        ENVIRONMENT="production",
        SUPABASE_URL="https://real-project.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="valid_pub_key_for_prod",
        SUPABASE_SERVICE_ROLE_KEY="valid_serv_role_secret_for_prod",
        DATABASE_URL="postgresql://user:pass@db.real.co:5432/db",
        REDIS_URL="redis://default:pass@redis.real.co:6379/0",
        GEMINI_API_KEY="gemini-real-secret-key-for-prod",
        CV_STORAGE_BUCKET="cvs",
        ALLOWED_ORIGINS=invalid_origin,
    )
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        validate_production_config(cfg)


def test_valid_production_config_passes():
    """Test 10: Valid production configuration passes validation without error."""
    valid_cfg = Settings(
        ENVIRONMENT="production",
        SUPABASE_URL="https://myprodapp.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="super_secure_publishable_key_value",
        SUPABASE_SERVICE_ROLE_KEY="super_secure_service_role_key_value",
        DATABASE_URL=(
            "postgresql://postgres:prodpass123@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
        ),
        REDIS_URL="rediss://default:prodredispass@eu-redis.upstash.io:6379",
        GEMINI_API_KEY="gemini-prod-key-1234567890abcdef",
        CV_STORAGE_BUCKET="internmatch-cv-production",
        ALLOWED_ORIGINS="https://internmatch.ai,https://admin.internmatch.ai",
    )
    validate_production_config(valid_cfg)


def test_production_validation_error_never_contains_secrets():
    """Test 11: Validation error message never leaks secret values or config dictionary."""
    super_secret_db = "postgresql://user:SUPER_SECRET_VALUE_999@placeholder.co:5432/db"
    cfg = Settings(
        ENVIRONMENT="production",
        SUPABASE_URL="https://placeholder.supabase.co",
        DATABASE_URL=super_secret_db,
    )
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_config(cfg)

    err_str = str(exc_info.value)
    assert "SUPER_SECRET_VALUE_999" not in err_str
    assert "DATABASE_URL" in err_str


# ---------------------------------------------------------------------------
# B. ENQUEUE FAILURE PUBLIC ERRORS TESTS (12 - 14)
# ---------------------------------------------------------------------------


def test_match_enqueue_failure_persists_exact_generic_error(
    client: TestClient, monkeypatch, mock_supabase_auth
):
    """Test 12: Match enqueue failure persists safe generic error and not raw exception."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    sensitive_error = "Connection lost to redis://default:REDIS_SECRET_123@redis:6379/0"

    def failing_enqueue(*args, **kwargs):
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(
        "app.api.v1.endpoints.matches.enqueue_match_calculation",
        failing_enqueue,
    )

    response = client.post(
        "/api/v1/matches/calculate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503

    db = TestingSessionLocal()
    try:
        job = (
            db.query(ProcessingJob).filter_by(user_id=user_id, job_type="match_calculation").first()
        )
        assert job is not None
        assert job.status == "failed"
        assert job.progress_percent == 100
        assert job.result is None
        assert job.error == "Failed to enqueue match calculation job."
        assert "REDIS_SECRET_123" not in (job.error or "")
    finally:
        db.close()


def test_cv_enqueue_failure_persists_exact_generic_error(
    client: TestClient, monkeypatch, mock_supabase_auth
):
    """Test 13: CV enqueue failure persists safe generic error and not raw exception."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    sensitive_error = "S3 / GCS secret key invalid: AWS_SECRET_KEY_XYZ987"

    def failing_enqueue(*args, **kwargs):
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(
        "app.api.v1.endpoints.profile.enqueue_cv_extraction",
        failing_enqueue,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.profile.store_candidate_cv",
        lambda *args, **kwargs: MagicMock(storage_path="user/cv.pdf"),
    )

    response = client.post(
        "/api/v1/profile/cv",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("resume.pdf", b"%PDF-1.4 dummy", "application/pdf")},
    )
    assert response.status_code == 503

    db = TestingSessionLocal()
    try:
        job = db.query(ProcessingJob).filter_by(user_id=user_id, job_type="cv_extraction").first()
        assert job is not None
        assert job.status == "failed"
        assert job.progress_percent == 100
        assert job.result is None
        assert job.error == "Failed to enqueue CV extraction job."
        assert "AWS_SECRET_KEY_XYZ987" not in (job.error or "")
    finally:
        db.close()


def test_application_enqueue_failure_persists_exact_generic_error(
    client: TestClient, monkeypatch, mock_supabase_auth
):
    """
    Test 14: Application enqueue failure persists safe generic error
    and not raw exception.
    """
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
            is_active=True,
            title="Dev",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=80,
            skill_score=80,
            vector_score=80,
            attribute_score=80,
        )
        db.add(match)
        db.commit()
        match_id = match.id
    finally:
        db.close()

    sensitive_error = "Redis broker error: redis://:SECRET_CLUSTER_PASS@redis:6379"

    def failing_enqueue(*args, **kwargs):
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(
        "app.api.v1.endpoints.applications.enqueue_application_generation",
        failing_enqueue,
    )

    response = client.post(
        "/api/v1/applications/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "match_id": str(match_id),
            "tone": "professional",
            "content_locale": "en",
        },
    )
    assert response.status_code == 503

    db = TestingSessionLocal()
    try:
        job = (
            db.query(ProcessingJob)
            .filter_by(user_id=user_id, job_type="application_generation")
            .first()
        )
        assert job is not None
        assert job.status == "failed"
        assert job.progress_percent == 100
        assert job.result is None
        assert job.error == "Failed to enqueue application generation job."
        assert "SECRET_CLUSTER_PASS" not in (job.error or "")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# C. WORKER FAILURE PUBLIC ERRORS TESTS (15 - 17)
# ---------------------------------------------------------------------------


def test_match_worker_failure_persists_safe_error(monkeypatch):
    """Test 15: Match worker failure persists 'Match calculation failed.'"""
    user_id = uuid4()
    job_id = uuid4()

    db = TestingSessionLocal()
    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="match_calculation",
            status="queued",
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    sensitive_error = "Postgres query crash: postgresql://admin:SECRET_PASS@db"

    def failing_calc(*args, **kwargs):
        raise RuntimeError(sensitive_error)

    monkeypatch.setattr(
        "tasks.match_calculation.calculate_and_persist_matches",
        failing_calc,
    )

    with pytest.raises(RuntimeError):
        run_match_calculation(job_id=job_id, user_id=user_id)

    db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(db=db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.error == "Match calculation failed."
        assert "SECRET_PASS" not in (persisted.error or "")
    finally:
        db.close()


def test_cv_worker_failure_persists_safe_error(monkeypatch):
    """Test 16: CV worker failure persists 'CV processing failed.'"""
    user_id = uuid4()
    job_id = uuid4()

    db = TestingSessionLocal()
    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="cv_extraction",
            status="queued",
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    sensitive_error = "OpenAI parse failure with api_key sk-SECRET_AI_KEY_99"

    monkeypatch.setattr("tasks.cv_extraction.download_candidate_cv", lambda **kwargs: b"pdf")
    monkeypatch.setattr("tasks.cv_extraction.extract_cv_text", lambda **kwargs: "text")
    monkeypatch.setattr("tasks.cv_extraction.validate_cv_document", lambda **kwargs: None)
    monkeypatch.setattr(
        "tasks.cv_extraction.extract_structured_candidate_profile",
        MagicMock(side_effect=RuntimeError(sensitive_error)),
    )

    with pytest.raises(RuntimeError):
        run_cv_extraction(job_id=job_id, user_id=user_id, storage_path="user/cv.pdf")

    db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(db=db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.error == "CV processing failed."
        assert "SECRET_AI_KEY" not in (persisted.error or "")
    finally:
        db.close()


def test_application_worker_failure_persists_safe_error(monkeypatch):
    """Test 17: Application worker failure persists 'Application generation failed.'"""
    user_id = uuid4()
    job_id = uuid4()

    db = TestingSessionLocal()
    try:
        job = ProcessingJob(
            id=job_id,
            user_id=user_id,
            job_type="application_generation",
            status="queued",
        )
        db.add(job)

        profile = StudentProfile(id=uuid4(), user_id=user_id, full_name="Candidate")
        db.add(profile)
        db.flush()

        listing = InternshipListing(
            id=uuid4(),
            listing_source="curated",
            publication_status="published",
            is_active=True,
            title="Dev",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Dev.",
        )
        db.add(listing)
        db.flush()

        match = Match(
            id=uuid4(),
            student_id=profile.id,
            internship_id=listing.id,
            overall_score=80,
            skill_score=80,
            vector_score=80,
            attribute_score=80,
        )
        db.add(match)
        db.commit()
        match_id = match.id
    finally:
        db.close()

    sensitive_error = "OpenAI rate limit with token sk-SECRET_TOKEN_444"

    monkeypatch.setattr(
        "tasks.application_generation.generate_grounded_cover_letter",
        MagicMock(side_effect=RuntimeError(sensitive_error)),
    )

    with pytest.raises(RuntimeError):
        run_application_generation(
            job_id=job_id,
            user_id=user_id,
            match_id=match_id,
            tone="professional",
        )

    db = TestingSessionLocal()
    try:
        persisted = ProcessingJobRepository.get_by_id(db=db, job_id=job_id)
        assert persisted is not None
        assert persisted.status == "failed"
        assert persisted.error == "Application generation failed."
        assert "SECRET_TOKEN" not in (persisted.error or "")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# D. JOB API REGRESSION (18 - 20)
# ---------------------------------------------------------------------------


def test_get_job_status_returns_error_field(client: TestClient, mock_supabase_auth):
    """Test 18: GET /jobs/{id} returns the error field in public contract."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        job = ProcessingJob(
            id=uuid4(),
            user_id=user_id,
            job_type="match_calculation",
            status="completed",
            progress_percent=100,
            result={"match_count": 5},
            error=None,
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    response = client.get(
        f"/api/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    assert data["error"] is None
    assert data["status"] == "completed"


def test_failed_job_returns_safe_persisted_generic_error(client: TestClient, mock_supabase_auth):
    """Test 19: A failed job returns the safe persisted generic error."""
    user_id = uuid4()
    token = f"valid-user-{user_id}"

    db = TestingSessionLocal()
    try:
        job = ProcessingJob(
            id=uuid4(),
            user_id=user_id,
            job_type="match_calculation",
            status="failed",
            progress_percent=100,
            result=None,
            error="Match calculation failed.",
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    response = client.get(
        f"/api/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["error"] == "Match calculation failed."


def test_cross_tenant_job_access_remains_404(client: TestClient, mock_supabase_auth):
    """Test 20: Cross-tenant job access returns 404 Not Found."""
    user_a = uuid4()
    user_b = uuid4()
    token_b = f"valid-user-{user_b}"

    db = TestingSessionLocal()
    try:
        job_a = ProcessingJob(
            id=uuid4(),
            user_id=user_a,
            job_type="match_calculation",
            status="queued",
        )
        db.add(job_a)
        db.commit()
        job_a_id = job_a.id
    finally:
        db.close()

    response = client.get(
        f"/api/v1/jobs/{job_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# E. WORKER REDIS LOGGING (21 - 23)
# ---------------------------------------------------------------------------


def test_worker_redis_connection_failure_exits_and_protects_credentials(monkeypatch, caplog):
    """
    Tests 21, 22, 23: Worker logs generic Redis failure message,
    exits with status 1, and never prints credentials or raw exception.
    """
    sensitive_pass = "SUPER_SECRET_REDIS_PASSWORD_999"
    sensitive_url = f"redis://default:{sensitive_pass}@internal-redis:6379/0"
    sensitive_exc = f"Authentication failure for password '{sensitive_pass}'"

    monkeypatch.setattr(
        "worker.worker_settings.REDIS_URL",
        sensitive_url,
    )

    def failing_from_url(*args, **kwargs):
        raise ConnectionError(sensitive_exc)

    monkeypatch.setattr("worker.Redis.from_url", failing_from_url)

    with caplog.at_level(logging.ERROR, logger="internmatch_worker"):
        with pytest.raises(SystemExit) as exc_info:
            run_worker()

    assert exc_info.value.code == 1

    # Check captured log messages
    log_text = caplog.text
    assert "Failed to connect to Redis." in log_text
    assert sensitive_pass not in log_text
    assert "SUPER_SECRET_REDIS_PASSWORD" not in log_text
    assert sensitive_exc not in log_text
