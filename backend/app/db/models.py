"""
SQLAlchemy ORM Models for Database Tables
Maps public schema tables defined by database/migrations/001_initial_schema.sql.
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from app.core.config import settings
from app.db.session import Base
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    ARRAY,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class StudentProfile(Base):
    """ORM Model mapping public.student_profiles table."""

    __tablename__ = "student_profiles"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), unique=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    headline: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cv_storage_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    avatar_storage_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    preferences: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True, default=dict
    )
    summary_embedding: Mapped[Optional[List[float]]] = mapped_column(
        VECTOR(settings.EMBEDDING_DIMENSION).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Skill(Base):
    """ORM Model mapping public.skills master taxonomy table."""

    __tablename__ = "skills"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class StudentSkill(Base):
    """ORM Model mapping public.student_skills junction table."""

    __tablename__ = "student_skills"

    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    proficiency_level: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, default="intermediate"
    )

    skill: Mapped["Skill"] = relationship("Skill")


class EducationEntry(Base):
    """ORM Model mapping public.education_entries table."""

    __tablename__ = "education_entries"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    institution: Mapped[str] = mapped_column(Text, nullable=False)
    degree: Mapped[str] = mapped_column(Text, nullable=False)
    start_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class ExperienceEntry(Base):
    """ORM Model mapping public.experience_entries table."""

    __tablename__ = "experience_entries"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    company: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class ProjectEntry(Base):
    """ORM Model mapping public.project_entries table."""

    __tablename__ = "project_entries"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    tech_stack: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String).with_variant(JSON, "sqlite"), nullable=True, default=list
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class InternshipListing(Base):
    """ORM Model mapping public.internship_listings table."""

    __tablename__ = "internship_listings"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    employer_user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    company: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(String, nullable=False)
    work_type: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    required_skills: Mapped[List[str]] = mapped_column(
        ARRAY(String).with_variant(JSON, "sqlite"), nullable=False, default=list
    )
    preferred_skills: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String).with_variant(JSON, "sqlite"), nullable=True, default=list
    )
    language: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, default="English"
    )
    education_requirements: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    experience_requirements: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSON, nullable=True, default=dict
    )
    description_embedding: Mapped[Optional[List[float]]] = mapped_column(
        VECTOR(settings.EMBEDDING_DIMENSION).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), nullable=False
    )


class ProcessingJob(Base):
    """ORM Model mapping public.processing_jobs table."""

    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('cv_extraction', 'match_calculation', 'application_generation')",
            name="ck_processing_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_processing_jobs_status",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_processing_jobs_progress_percent",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    progress_percent: Mapped[int] = mapped_column(
        nullable=False, default=0
    )
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Match(Base):
    """ORM Model mapping public.matches table."""

    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "internship_id", name="uq_matches_student_internship"
        ),
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_matches_overall_score",
        ),
        CheckConstraint(
            "skill_score >= 0 AND skill_score <= 100",
            name="ck_matches_skill_score",
        ),
        CheckConstraint(
            "vector_score >= 0 AND vector_score <= 100",
            name="ck_matches_vector_score",
        ),
        CheckConstraint(
            "attribute_score >= 0 AND attribute_score <= 100",
            name="ck_matches_attribute_score",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    internship_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("internship_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    overall_score: Mapped[int] = mapped_column(nullable=False)
    skill_score: Mapped[int] = mapped_column(nullable=False)
    vector_score: Mapped[int] = mapped_column(nullable=False)
    attribute_score: Mapped[int] = mapped_column(nullable=False)
    why_you_match: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    skill_gap_analysis: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    student_profile: Mapped["StudentProfile"] = relationship("StudentProfile")
    internship: Mapped["InternshipListing"] = relationship("InternshipListing")


class Application(Base):
    """ORM Model mapping public.applications table (Application Tracker)."""

    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "internship_id",
            name="uq_applications_student_internship",
        ),
        CheckConstraint(
            "status IN ('saved', 'applied', 'interviewing', 'rejected', 'accepted')",
            name="ck_applications_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    internship_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("internship_listings.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="saved"
    )
    generated_cover_letter: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    applied_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Employer-owned canonical interview schedule.
    # These fields are meaningful when the application is in the
    # interviewing stage, but remain nullable for historical records.
    interview_scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    interview_mode: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    interview_location: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    interview_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    student_profile: Mapped["StudentProfile"] = relationship("StudentProfile")
    internship: Mapped[Optional["InternshipListing"]] = relationship(
        "InternshipListing"
    )
    status_events: Mapped[List["ApplicationStatusEvent"]] = relationship(
        "ApplicationStatusEvent",
        back_populates="application",
        passive_deletes="all",
        order_by="ApplicationStatusEvent.occurred_at.asc(), ApplicationStatusEvent.id.asc()",
    )


class ApplicationStatusEvent(Base):
    """ORM Model mapping public.application_status_events table (Application Status History)."""

    __tablename__ = "application_status_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('saved', 'applied', 'interviewing', 'rejected', 'accepted')",
            name="ck_application_status_events_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    application_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    application: Mapped["Application"] = relationship(
        "Application", back_populates="status_events"
    )


class SavedInternship(Base):
    """ORM Model mapping public.saved_internships table (Candidate Bookmarks)."""

    __tablename__ = "saved_internships"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "internship_id",
            name="uq_saved_internships_student_internship",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    internship_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("internship_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    student_profile: Mapped["StudentProfile"] = relationship("StudentProfile")
    internship: Mapped["InternshipListing"] = relationship("InternshipListing")

class SubscriptionEntitlement(Base):
    """Server-authoritative RevenueCat entitlement state for an authenticated user."""

    __tablename__ = "subscription_entitlements"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "entitlement_id",
            name="uq_subscription_entitlements_user_entitlement",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )
    entitlement_id: Mapped[str] = mapped_column(String, nullable=False)
    product_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="inactive")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    will_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_period_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    environment: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    store: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    original_transaction_id: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    expiration_reason: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    last_event_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_event_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_event_timestamp_ms: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class AIQuotaPeriod(Base):
    """Server-owned aggregate quota counters for one user feature period."""

    __tablename__ = "ai_quota_periods"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "feature_key",
            name="uq_ai_quota_periods_user_feature",
        ),
        CheckConstraint(
            "feature_key IN ("
            "'cv_analysis', "
            "'match_explanation', "
            "'application_support', "
            "'interview_prep'"
            ")",
            name="ck_ai_quota_periods_feature_key",
        ),
        CheckConstraint(
            "plan_key IN ('free', 'pro_student')",
            name="ck_ai_quota_periods_plan_key",
        ),
        CheckConstraint(
            "used_count >= 0",
            name="ck_ai_quota_periods_used_count",
        ),
        CheckConstraint(
            "reserved_count >= 0",
            name="ck_ai_quota_periods_reserved_count",
        ),
        CheckConstraint(
            "period_end > period_start",
            name="ck_ai_quota_periods_period",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    feature_key: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    plan_key: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    used_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    reserved_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class RevenueCatWebhookEvent(Base):
    """Minimal RevenueCat event ledger used for idempotent webhook processing."""

    __tablename__ = "revenuecat_webhook_events"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outcome: Mapped[str] = mapped_column(
        String, nullable=False, default="received"
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
