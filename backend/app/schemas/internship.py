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



class AdminInternshipChangesRequest(BaseModel):
    """
    Employer-visible correction feedback supplied by an administrator.

    This contract is intentionally public-facing. Internal moderation notes,
    credentials, private evidence, and administrative-only context must never
    be placed in this field.
    """

    employer_visible_feedback: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description=(
            "Plain-text correction guidance visible to the employer."
        ),
    )

    @field_validator(
        "employer_visible_feedback",
        mode="before",
    )
    @classmethod
    def validate_employer_visible_feedback(
        cls,
        value: Any,
    ) -> str:
        if not isinstance(value, str):
            raise ValueError(
                "Employer-visible feedback must be text."
            )

        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                "Employer-visible feedback cannot be empty."
            )

        if any(
            ord(char) < 32
            and char not in "\n\t"
            for char in cleaned
        ):
            raise ValueError(
                "Employer-visible feedback contains unsupported control characters."
            )

        return cleaned


class AdminInternshipCreateRequest(InternshipCreateRequest):
    """
    Server-authorized curated opportunity creation payload.

    Admin-created opportunities intentionally remain distinct from
    employer-owned listings. The company label is explicit and defaults
    to the InternMatch AI team identity for first-party opportunities.
    """

    company: str = Field(
        default="InternMatch AI Team",
        min_length=1,
        max_length=200,
        description="Public company or organization display name",
    )
    publication_status: Literal["draft", "published"] = Field(
        default="published",
        description="Create hidden draft or publish immediately",
    )

    @field_validator("company", mode="before")
    @classmethod
    def validate_admin_company(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Company must be a non-empty string.")
        return v.strip()


class InternshipSummaryResponse(BaseModel):
    """Schema for individual internship item in catalog listing endpoint."""

    id: UUID
    title: str
    company: str
    location: str
    work_type: str
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    publication_status: Literal[
        "draft", "under_review", "published", "closed"
    ]
    is_active: bool
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
            publication_status=getattr(
                model,
                "publication_status",
                "draft",
            ),
            is_active=(
                getattr(model, "publication_status", "draft")
                == "published"
            ),
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
    publication_status: Literal[
        "draft", "under_review", "published", "closed"
    ]
    is_active: bool
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
            publication_status=getattr(
                model,
                "publication_status",
                "draft",
            ),
            is_active=(
                getattr(model, "publication_status", "draft")
                == "published"
            ),
            posted_at=model.created_at,
        )

class AdminInternshipDetailResponse(
    InternshipDetailResponse
):
    """
    Admin-only listing detail with recruiter ownership boundary.

    admin_managed=True means the opportunity was created by the
    InternMatch admin console and has no employer ownership.
    """

    admin_managed: bool

    @classmethod
    def from_orm_model(
        cls,
        model: Any,
    ) -> "AdminInternshipDetailResponse":
        base = (
            InternshipDetailResponse
            .from_orm_model(model)
        )

        metadata = (
            model.metadata_json
            if isinstance(
                model.metadata_json,
                dict,
            )
            else {}
        )

        admin_managed = (
            model.listing_source
            == "curated"
            and model.employer_user_id
            is None
            and model.employer_organization_id
            is None
            and metadata.get("created_via")
            == "admin_console"
        )

        return cls(
            **base.model_dump(),
            admin_managed=admin_managed,
        )
