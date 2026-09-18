"""
SQLAlchemy ORM Models for Database Tables
Maps public schema tables defined by database/migrations/001_initial_schema.sql.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
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
    Numeric,
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
    cv_evidenced: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )
    self_declared: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )
    cv_provenance_known: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
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


class EmployerOrganization(Base):
    """
    Canonical employer organization identity and verification state.

    Employer account role and organization verification are deliberately
    separate authorities. Public signup can create an employer account, but
    only this server-controlled lifecycle may establish verified company trust.
    """

    __tablename__ = "employer_organizations"

    __table_args__ = (
        CheckConstraint(
            "verification_status IN "
            "('unverified', 'pending', 'verified', 'rejected', 'suspended')",
            name="ck_employer_organizations_verification_status",
        ),
        CheckConstraint(
            "organization_type IN "
            "('company', 'university_lab', 'research_center')",
            name="ck_employer_organizations_organization_type",
        ),
        CheckConstraint(
            "verification_method IS NULL OR "
            "verification_method IN "
            "('standard_company', 'manual_admin')",
            name="ck_employer_organizations_verification_method",
        ),
        CheckConstraint(
            "("
            "verification_status IN ('verified', 'suspended') "
            "AND verification_method IS NOT NULL"
            ") OR ("
            "verification_status IN "
            "('unverified', 'pending', 'rejected') "
            "AND verification_method IS NULL"
            ")",
            name=(
                "ck_employer_organizations_"
                "verification_method_status"
            ),
        ),
        CheckConstraint(
            "organization_type = 'company' "
            "OR verification_method IS NULL "
            "OR verification_method = 'manual_admin'",
            name=(
                "ck_employer_organizations_"
                "non_company_manual_verification"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )
    legal_name: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    website_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_domain: Mapped[str] = mapped_column(String, nullable=False)
    business_email: Mapped[str] = mapped_column(String, nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    registration_number: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )
    tax_number: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )
    representative_name: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    representative_role: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    verification_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="unverified",
        index=True,
    )
    organization_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="company",
    )
    verification_method: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
    )
    reviewed_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    rejection_reason_code: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class EmployerVerificationEvent(Base):
    """
    Append-only audit history for employer verification lifecycle actions.

    Reviewer UUID and private internal notes are administrative data and are
    never intended for public company responses.
    """

    __tablename__ = "employer_verification_events"

    __table_args__ = (
        CheckConstraint(
            "action IN "
            "('created', 'submitted', 'resubmitted', "
            "'approved', 'rejected', 'suspended')",
            name="ck_employer_verification_events_action",
        ),
        CheckConstraint(
            "verification_method IS NULL OR "
            "verification_method IN "
            "('standard_company', 'manual_admin')",
            name=(
                "ck_employer_verification_events_"
                "verification_method"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("employer_organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    previous_status: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )
    new_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    verification_method: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )
    reason_code: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )
    internal_note: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )




class EmployerComplianceClaim(Base):
    """
    Jurisdiction-scoped employer compliance assertion.

    This model is deliberately independent from EmployerOrganization
    verification. An approved claim means only that its specific supporting
    evidence was reviewed for the recorded jurisdiction and scope.
    """

    __tablename__ = "employer_compliance_claims"

    __table_args__ = (
        CheckConstraint(
            "claim_type IN "
            "('insurance_arrangement', "
            "'completion_certificate', "
            "'university_agreement', "
            "'legal_internship_eligibility')",
            name="ck_employer_compliance_claim_type",
        ),
        CheckConstraint(
            "status IN "
            "('draft', 'pending', 'approved', "
            "'rejected', 'revoked', 'expired')",
            name="ck_employer_compliance_claim_status",
        ),
        CheckConstraint(
            "length(jurisdiction_country_code) = 2",
            name="ck_employer_compliance_country_code",
        ),
        CheckConstraint(
            "length(trim(scope_key)) > 0",
            name="ck_employer_compliance_scope_key",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_employer_compliance_version",
        ),
        CheckConstraint(
            "valid_from IS NULL OR "
            "valid_until IS NULL OR "
            "valid_until >= valid_from",
            name="ck_employer_compliance_validity",
        ),
        UniqueConstraint(
            "organization_id",
            "claim_type",
            "jurisdiction_country_code",
            "scope_key",
            name="uq_employer_compliance_claim_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "employer_organizations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    claim_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    jurisdiction_country_code: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
    )

    scope_key: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="organization",
    )

    scope_label: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )

    statement: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="draft",
        index=True,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
    )

    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
    )

    reviewed_by: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    rejection_reason_code: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )

    valid_from: Mapped[Optional[date]] = mapped_column(
        nullable=True,
    )

    valid_until: Mapped[Optional[date]] = mapped_column(
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class EmployerComplianceEvidence(Base):
    """
    Metadata for one private document supporting a compliance claim.

    Organization ownership is authoritative through claim_id. It is not
    duplicated here, preventing claim/organization mismatch states.
    """

    __tablename__ = "employer_compliance_evidence"

    __table_args__ = (
        UniqueConstraint(
            "storage_path",
            name=(
                "uq_employer_compliance_"
                "evidence_storage_path"
            ),
        ),
        CheckConstraint(
            "content_type = 'application/pdf'",
            name=(
                "ck_employer_compliance_"
                "evidence_content_type"
            ),
        ),
        CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 10485760",
            name="ck_employer_compliance_evidence_size",
        ),
        CheckConstraint(
            "length(sha256_hex) = 64",
            name="ck_employer_compliance_evidence_sha256",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "employer_compliance_claims.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    storage_path: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    original_filename: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    content_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    sha256_hex: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    uploaded_by_user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class EmployerComplianceEvent(Base):
    """
    Append-only audit history for employer compliance claim actions.

    Organization ownership is authoritative through claim_id.
    """

    __tablename__ = "employer_compliance_events"

    __table_args__ = (
        CheckConstraint(
            "actor_role IN ('employer', 'admin', 'system')",
            name="ck_employer_compliance_event_actor_role",
        ),
        CheckConstraint(
            "action IN "
            "('created', 'updated', 'evidence_attached', "
            "'submitted', 'approved', 'rejected', "
            "'revoked', 'expired')",
            name="ck_employer_compliance_event_action",
        ),
        CheckConstraint(
            "new_status IN "
            "('draft', 'pending', 'approved', "
            "'rejected', 'revoked', 'expired')",
            name="ck_employer_compliance_event_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    claim_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "employer_compliance_claims.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    actor_user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    actor_role: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    action: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    previous_status: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )

    new_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    reason_code: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
    )

    internal_note: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class InternshipListing(Base):
    """ORM Model mapping public.internship_listings table."""

    __tablename__ = "internship_listings"

    __table_args__ = (
        CheckConstraint(
            "listing_source IN "
            "('curated', 'employer', 'legacy_unknown')",
            name="ck_internship_listings_listing_source",
        ),
        CheckConstraint(
            "publication_status IN "
            "('draft', 'under_review', 'published', 'closed')",
            name="ck_internship_listings_publication_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    employer_user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    employer_organization_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("employer_organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    listing_source: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="legacy_unknown",
    )
    publication_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="draft",
        index=True,
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
    # Compatibility mirror only. publication_status is authoritative.
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), nullable=False
    )


class ProcessingJob(Base):
    """ORM Model mapping public.processing_jobs table."""

    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint(
            (
                "job_type IN ('cv_extraction', 'match_calculation', "
                "'application_generation', 'match_explanation', 'interview_prep')"
            ),
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



class PromoCampaign(Base):
    """Admin-managed one-time promotional campaign."""

    __tablename__ = "promo_campaigns"

    __table_args__ = (
        CheckConstraint(
            "audience IN ('student', 'employer')",
            name="ck_promo_campaigns_audience",
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'retired')",
            name="ck_promo_campaigns_status",
        ),
        CheckConstraint(
            "duration_days = 7",
            name="ck_promo_campaigns_duration",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    audience: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Only an HMAC digest and a masked display hint are persisted.
    # The plaintext code never enters the database.
    code_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )

    code_hint: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
    )

    duration_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=7,
    )

    created_by_admin_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )

    retired_by_admin_user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    retired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class PromoRedemption(Base):
    """
    Durable one-time redemption ledger.

    user_id + audience is unique forever. Rotating the campaign therefore
    never allows the same account to claim another promotional week.
    """

    __tablename__ = "promo_redemptions"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "audience",
            name="uq_promo_redemptions_user_audience",
        ),
        CheckConstraint(
            "audience IN ('student', 'employer')",
            name="ck_promo_redemptions_audience",
        ),
        CheckConstraint(
            "status IN ('pending', 'redeemed', 'failed')",
            name="ck_promo_redemptions_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    campaign_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "promo_campaigns.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )

    audience: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    access_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    access_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    provider_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    last_error_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


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
            "'interview_prep', "
            "'employer_candidate_insight', "
            "'employer_interview_kit', "
            "'employer_shortlist_comparison', "
            "'employer_internship_description'"
            ")",
            name="ck_ai_quota_periods_feature_key",
        ),
        CheckConstraint(
            "plan_key IN ('free', 'pro_student', 'employer_pro')",
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


class AIQuotaOperation(Base):
    """Durable lifecycle ledger for one quota-controlled AI operation."""

    __tablename__ = "ai_quota_operations"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "feature_key",
            "period_start",
            "idempotency_key",
            name="uq_ai_quota_operations_idempotency",
        ),
        CheckConstraint(
            "feature_key IN ("
            "'cv_analysis', "
            "'match_explanation', "
            "'application_support', "
            "'interview_prep', "
            "'employer_candidate_insight', "
            "'employer_interview_kit', "
            "'employer_shortlist_comparison', "
            "'employer_internship_description'"
            ")",
            name="ck_ai_quota_operations_feature_key",
        ),
        CheckConstraint(
            "plan_key IN ('free', 'pro_student', 'employer_pro')",
            name="ck_ai_quota_operations_plan_key",
        ),
        CheckConstraint(
            "status IN ('reserved', 'settled', 'released')",
            name="ck_ai_quota_operations_status",
        ),
        CheckConstraint(
            "period_end > period_start",
            name="ck_ai_quota_operations_period",
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
    idempotency_key: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    request_fingerprint: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="reserved",
    )
    processing_job_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "processing_jobs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    settled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    release_reason: Mapped[Optional[str]] = mapped_column(
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



class AIUsageEvent(Base):
    """Internal server-side telemetry for one AI provider invocation."""

    __tablename__ = "ai_usage_events"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('gemini', 'openai')",
            name="ck_ai_usage_events_provider",
        ),
        CheckConstraint(
            "status IN ('success', 'error')",
            name="ck_ai_usage_events_status",
        ),
        CheckConstraint(
            "latency_ms >= 0",
            name="ck_ai_usage_events_latency_nonnegative",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_ai_usage_events_input_tokens_nonnegative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_ai_usage_events_output_tokens_nonnegative",
        ),
        CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name="ck_ai_usage_events_total_tokens_nonnegative",
        ),
        CheckConstraint(
            "candidate_tokens IS NULL OR candidate_tokens >= 0",
            name="ck_ai_usage_events_candidate_tokens_nonnegative",
        ),
        CheckConstraint(
            "thought_tokens IS NULL OR thought_tokens >= 0",
            name="ck_ai_usage_events_thought_tokens_nonnegative",
        ),
        CheckConstraint(
            "cached_input_tokens IS NULL OR cached_input_tokens >= 0",
            name="ck_ai_usage_events_cached_tokens_nonnegative",
        ),
        CheckConstraint(
            "estimated_cost_usd IS NULL OR estimated_cost_usd >= 0",
            name="ck_ai_usage_events_cost_nonnegative",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    processing_job_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "processing_jobs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    quota_operation_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "ai_quota_operations.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="gemini",
    )
    operation: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    input_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    output_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    total_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    candidate_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    thought_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    cached_input_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    estimated_cost_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 10),
        nullable=True,
    )
    pricing_version: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    error_type: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
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


class UserNotification(Base):
    """
    Durable user-facing event notification.

    The backend owns event identity/read state. Clients localize presentation
    from event_type + data_json and may not select another recipient.
    """

    __tablename__ = "user_notifications"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    recipient_user_id: Mapped[UUID] = mapped_column(
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        nullable=False,
        index=True,
    )
    entity_type: Mapped[Optional[str]] = mapped_column(
        nullable=True,
    )
    entity_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        index=True,
    )
    data_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    dedupe_key: Mapped[Optional[str]] = mapped_column(
        nullable=True,
        unique=True,
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class PushDevice(Base):
    """
    Authenticated Expo push-device registration.

    Tokens belong only to the JWT user that registered them. Delivery is added
    in Gate 6B; this table establishes the durable device/locale boundary now.
    """

    __tablename__ = "push_devices"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        nullable=False,
        index=True,
    )
    expo_push_token: Mapped[str] = mapped_column(
        nullable=False,
        unique=True,
    )
    platform: Mapped[str] = mapped_column(
        nullable=False,
    )
    locale: Mapped[str] = mapped_column(
        nullable=False,
        default="en",
    )
    enabled: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
