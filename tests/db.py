"""Shared SQLite test database infrastructure."""
from app.db.models import (  # noqa: F401
    AIQuotaOperation,
    AIQuotaPeriod,
    AIUsageEvent,
    Application,
    ApplicationStatusEvent,
    EducationEntry,
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
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

@event.listens_for(test_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)
