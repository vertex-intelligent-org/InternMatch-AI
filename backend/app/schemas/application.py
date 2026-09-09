"""
Application API Response and Request Schemas
Provides Pydantic schemas for personalized application cover-letter generation
and application tracker management.
"""

from datetime import date, datetime
from typing import Any, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ApplicationStatus = Literal[
    "saved",
    "applied",
    "interviewing",
    "rejected",
    "accepted",
]


class ApplicationGenerateRequest(BaseModel):
    """Request schema for POST /api/v1/applications/generate."""

    match_id: UUID
    tone: str = Field(
        ...,
        min_length=1,
        description="Tone for the generated cover letter",
    )
    content_locale: Literal["en", "tr", "ar"] = Field(
        default="en",
        description="Target content locale for the generated cover letter",
    )

    @field_validator("tone")
    @classmethod
    def validate_tone(cls, v: str) -> str:
        """Validate and normalize tone string ensuring non-empty content."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Tone must not be empty or whitespace only")
        return stripped


class ApplicationGenerateAcceptedResponse(BaseModel):
    """Response schema for POST /api/v1/applications/generate (HTTP 202)."""

    job_id: UUID
    status: Literal["queued"] = "queued"
    message: str = "Personalized application generation enqueued."

    model_config = ConfigDict(from_attributes=True)


class ApplicationTrackerResponse(BaseModel):
    """Schema representing an application record in the Application Tracker."""

    id: UUID
    internship_id: Optional[UUID]
    company_name: Optional[str]
    job_title: Optional[str]
    status: ApplicationStatus
    generated_cover_letter: Optional[str]
    applied_date: Optional[date]
    notes: Optional[str]

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_tuple(
        cls, application: Any, internship: Optional[Any]
    ) -> "ApplicationTrackerResponse":
        """Factory mapping (Application, Optional[InternshipListing]) tuple."""
        return cls(
            id=application.id,
            internship_id=application.internship_id,
            company_name=internship.company if internship is not None else None,
            job_title=internship.title if internship is not None else None,
            status=application.status,
            generated_cover_letter=application.generated_cover_letter,
            applied_date=application.applied_date,
            notes=application.notes,
        )


class ApplicationListResponse(BaseModel):
    """Response schema for GET /api/v1/applications."""

    applications: List[ApplicationTrackerResponse]


class ApplicationStatusUpdateRequest(BaseModel):
    """Request schema for PATCH /api/v1/applications/{id}/status."""

    status: ApplicationStatus
    notes: Optional[str] = None


class ApplicationSubmitRequest(BaseModel):
    """Request schema for POST /api/v1/applications/{id}/submit (Candidate explicit submit)."""

    cover_letter: Optional[str] = Field(
        default=None, description="Optional edited cover letter content"
    )
    notes: Optional[str] = Field(
        default=None, description="Optional candidate notes"
    )


class EmployerInterviewScheduleRequest(BaseModel):
    scheduled_at: datetime = Field(
        ...,
        description="Interview start time as an ISO-8601 timestamp",
    )
    mode: Literal["online", "onsite"] = Field(
        ...,
        description="Interview mode",
    )
    location: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Meeting URL or physical interview location",
    )
    message: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Optional message from the employer to the candidate",
    )


class EmployerApplicantStatusUpdateRequest(BaseModel):
    """Request schema for employer transitioning applicant status."""

    status: Literal["interviewing", "accepted", "rejected"] = Field(
        ..., description="Target applicant status (interviewing, accepted, rejected)"
    )
    notes: Optional[str] = Field(
        default=None, description="Optional employer notes"
    )


class ApplicationStatusEventResponse(BaseModel):
    """Schema representing an individual status transition in an application's timeline."""

    status: ApplicationStatus
    occurred_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationDetailResponse(BaseModel):
    """Schema representing full application detail with chronological timeline."""

    id: UUID
    internship_id: Optional[UUID]
    company_name: Optional[str]
    job_title: Optional[str]
    status: ApplicationStatus
    generated_cover_letter: Optional[str]
    applied_date: Optional[date]
    notes: Optional[str]
    interview_scheduled_at: Optional[datetime] = None
    interview_mode: Optional[Literal["online", "onsite"]] = None
    interview_location: Optional[str] = None
    interview_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    timeline: List[ApplicationStatusEventResponse]

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_data(
        cls,
        application: Any,
        internship: Optional[Any],
        events: List[Any],
    ) -> "ApplicationDetailResponse":
        """
        Factory mapping (Application, Optional[InternshipListing], List[ApplicationStatusEvent]).
        """
        return cls(
            id=application.id,
            internship_id=application.internship_id,
            company_name=internship.company if internship is not None else None,
            job_title=internship.title if internship is not None else None,
            status=application.status,
            generated_cover_letter=application.generated_cover_letter,
            applied_date=application.applied_date,
            notes=application.notes,
            interview_scheduled_at=application.interview_scheduled_at,
            interview_mode=application.interview_mode,
            interview_location=application.interview_location,
            interview_message=application.interview_message,
            created_at=application.created_at,
            updated_at=application.updated_at,
            timeline=[
                ApplicationStatusEventResponse(
                    status=event.status,
                    occurred_at=event.occurred_at,
                )
                for event in events
            ],
        )


class CandidateApplicantSummary(BaseModel):
    """Candidate profile summary nested inside an EmployerApplicantResponse."""

    student_id: UUID
    full_name: str
    headline: Optional[str] = None
    department: Optional[str] = None
    skills: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class EmployerApplicantResponse(BaseModel):
    """Schema representing an applicant in an employer's internship applicant list/detail."""

    application_id: UUID
    internship_id: UUID
    status: ApplicationStatus
    applied_date: Optional[date] = None
    generated_cover_letter: Optional[str] = None
    match_score: Optional[int] = None
    skill_score: Optional[int] = None
    vector_score: Optional[int] = None
    attribute_score: Optional[int] = None
    ai_rank: Optional[int] = None
    matching_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    interview_scheduled_at: Optional[datetime] = None
    interview_mode: Optional[Literal["online", "onsite"]] = None
    interview_location: Optional[str] = None
    interview_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    candidate: CandidateApplicantSummary

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_data(
        cls,
        application: Any,
        profile: Any,
        match: Optional[Any],
        skills: Optional[List[str]] = None,
        ai_rank: Optional[int] = None,
    ) -> "EmployerApplicantResponse":
        """Factory mapping Application, StudentProfile, and optional Match."""
        dept = (profile.preferences or {}).get("department") if profile.preferences else None

        raw_gap = (
            match.skill_gap_analysis
            if match is not None and isinstance(match.skill_gap_analysis, dict)
            else {}
        )

        matching_skills = raw_gap.get("matching_skills", [])
        if not isinstance(matching_skills, list):
            matching_skills = []

        missing_skills = raw_gap.get("missing_skills", [])
        if not isinstance(missing_skills, list):
            missing_skills = []

        return cls(
            application_id=application.id,
            internship_id=application.internship_id,
            status=application.status,
            applied_date=application.applied_date,
            generated_cover_letter=application.generated_cover_letter,
            match_score=match.overall_score if match is not None else None,
            skill_score=match.skill_score if match is not None else None,
            vector_score=match.vector_score if match is not None else None,
            attribute_score=match.attribute_score if match is not None else None,
            ai_rank=ai_rank,
            matching_skills=matching_skills,
            missing_skills=missing_skills,
            interview_scheduled_at=application.interview_scheduled_at,
            interview_mode=application.interview_mode,
            interview_location=application.interview_location,
            interview_message=application.interview_message,
            created_at=application.created_at,
            updated_at=application.updated_at,
            candidate=CandidateApplicantSummary(
                student_id=profile.id,
                full_name=profile.full_name,
                headline=profile.headline,
                department=dept,
                skills=skills or [],
            ),
        )


class EmployerApplicantListResponse(BaseModel):
    """Schema representing the list of applicants for an employer's internship."""

    items: List[EmployerApplicantResponse]
    total: int
    internship_id: UUID
