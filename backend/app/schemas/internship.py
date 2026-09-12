"""
Internship Catalog API Response and Request Schemas
Provides Pydantic schemas for public internship catalog listing, detail,
and employer opportunity creation responses.
Handles explicit API boundary translations required by docs/API_CONTRACT.md.
"""

from datetime import datetime
from typing import Any, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InternshipCreateRequest(BaseModel):
    """Schema for POST /api/v1/internships (Employer Opportunity Creation)."""

    title: str = Field(
        ..., min_length=1, max_length=200, description="Job / internship title"
    )
    company: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
        description=(
            "Deprecated compatibility field. Ignored by the server; "
            "company identity is derived from the verified organization."
        ),
    )
    location: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Location (e.g. 'Istanbul, Turkiye' or 'Remote')",
    )
    work_type: Literal["remote", "onsite", "hybrid"] = Field(
        ..., description="Work modality ('remote', 'onsite', 'hybrid')"
    )
    description: str = Field(
        ..., min_length=1, description="Internship description"
    )
    required_skills: List[str] = Field(
        default_factory=list, description="List of required skills"
    )
    preferred_skills: List[str] = Field(
        default_factory=list, description="List of preferred skills"
    )
    language: Optional[str] = Field(
        default="English", description="Primary working language"
    )
    education_requirements: Optional[str] = Field(
        default=None, description="Minimum education requirements"
    )
    experience_requirements: Optional[str] = Field(
        default=None, description="Experience requirements"
    )

    @field_validator("title", "location", "description", mode="before")
    @classmethod
    def validate_non_empty_trimmed(cls, v: Any) -> str:
        """Validate and trim required string fields."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Field must be a non-empty string.")
        return v.strip()

    @field_validator("required_skills", "preferred_skills", mode="before")
    @classmethod
    def validate_skills_list(cls, v: Any) -> List[str]:
        """Normalize and filter string skills list."""
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("Skills must be a list of strings.")
        cleaned = []
        for item in v:
            if isinstance(item, str) and item.strip():
                cleaned.append(item.strip())
        return cleaned


class InternshipUpdateRequest(InternshipCreateRequest):
    """
    Full employer-owned opportunity update payload.

    Uses the same validated canonical fields as creation. The authenticated
    employer must own the listing being updated.
    """



class InternshipSummaryResponse(BaseModel):
    """Schema for individual internship item in catalog listing endpoint."""

    id: UUID
    title: str
    company: str
    location: str
    work_type: str
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    is_active: bool = True
    posted_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, model: Any) -> "InternshipSummaryResponse":
        """Explicit mapping boundary for summary response."""
        return cls(
            id=model.id,
            title=model.title,
            company=model.company,
            location=model.location,
            work_type=model.work_type,
            required_skills=model.required_skills or [],
            preferred_skills=model.preferred_skills or [],
            is_active=getattr(model, "is_active", True),
            posted_at=model.created_at,
        )


class InternshipListResponse(BaseModel):
    """Schema for paginated catalog list endpoint response."""

    items: List[InternshipSummaryResponse]
    total: int
    limit: int
    offset: int


class InternshipDetailResponse(BaseModel):
    """Schema for complete internship listing detail endpoint response."""

    id: UUID
    title: str
    company: str
    location: str
    work_type: str
    description: str
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    min_education: Optional[str] = None
    experience_requirements: Optional[str] = None
    is_active: bool = True
    posted_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, model: Any) -> "InternshipDetailResponse":
        """Explicit mapping boundary for detail response."""
        lang_str = model.language
        languages_list = [lang_str] if lang_str else ["English"]
        return cls(
            id=model.id,
            title=model.title,
            company=model.company,
            location=model.location,
            work_type=model.work_type,
            description=model.description,
            required_skills=model.required_skills or [],
            preferred_skills=model.preferred_skills or [],
            languages=languages_list,
            min_education=model.education_requirements,
            experience_requirements=model.experience_requirements,
            is_active=getattr(model, "is_active", True),
            posted_at=model.created_at,
        )
