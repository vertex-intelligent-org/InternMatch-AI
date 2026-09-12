"""
Employer organization verification workflow.

Employer account role is not company verification.
Employers control company identity details only.
Verification lifecycle and reviewer authority are server/admin controlled.
"""

from datetime import datetime, timezone
from typing import Literal, Optional
from urllib.parse import urlparse
from uuid import UUID

from app.core.security import (
    AuthenticatedUser,
    require_admin_user,
    require_employer_user,
)
from app.db.models import EmployerOrganization, InternshipListing
from app.db.session import get_db
from app.repositories.employer_organization import (
    EmployerOrganizationRepository,
)
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


employer_router = APIRouter()
admin_router = APIRouter()


VerificationStatus = Literal[
    "unverified",
    "pending",
    "verified",
    "rejected",
    "suspended",
]

RejectionReasonCode = Literal[
    "company_not_found",
    "registration_mismatch",
    "domain_mismatch",
    "email_not_professional",
    "insufficient_evidence",
    "suspected_impersonation",
    "other",
]


class EmployerOrganizationWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_name: str
    display_name: str
    website_url: str
    business_email: str
    country_code: str
    registration_number: Optional[str] = None
    tax_number: Optional[str] = None
    representative_name: str
    representative_role: str


class EmployerOrganizationResponse(BaseModel):
    id: UUID
    owner_user_id: UUID
    legal_name: str
    display_name: str
    website_url: str
    normalized_domain: str
    business_email: str
    email_domain_matches_website: bool
    country_code: str
    registration_number: Optional[str]
    tax_number: Optional[str]
    representative_name: str
    representative_role: str
    verification_status: VerificationStatus
    submitted_at: Optional[datetime]
    reviewed_at: Optional[datetime]
    rejection_reason_code: Optional[str]
    created_at: datetime
    updated_at: datetime


class AdminApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internal_note: Optional[str] = None


class AdminRejectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: RejectionReasonCode
    internal_note: Optional[str] = None


class AdminSuspensionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: str
    internal_note: Optional[str] = None


def _clean_required(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} is required.",
        )
    return cleaned


def _clean_optional(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    return cleaned or None


def _normalize_email(value: str) -> str:
    email = value.strip().lower()

    if (
        not email
        or " " in email
        or email.count("@") != 1
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Business email is invalid.",
        )

    local_part, domain = email.rsplit("@", 1)

    if (
        not local_part
        or not domain
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Business email is invalid.",
        )

    return email


def _normalize_website(
    value: str,
) -> tuple[str, str]:
    website_url = value.strip()
    parsed = urlparse(website_url)

    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Website must be a valid http:// or https:// URL."
            ),
        )

    domain = parsed.hostname.lower().rstrip(".")

    if domain.startswith("www."):
        domain = domain[4:]

    if "." not in domain:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Website domain is invalid.",
        )

    return website_url, domain


def _normalize_country_code(value: str) -> str:
    country_code = value.strip().upper()

    if (
        len(country_code) != 2
        or not country_code.isalpha()
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="country_code must be a two-letter country code.",
        )

    return country_code


def _normalize_write_payload(
    payload: EmployerOrganizationWriteRequest,
    current_user: AuthenticatedUser,
) -> dict:
    business_email = _normalize_email(
        payload.business_email
    )

    authenticated_email = (
        current_user.email or ""
    ).strip().lower()

    if not authenticated_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Authenticated email is required for employer "
                "verification."
            ),
        )

    if business_email != authenticated_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Business email must match the authenticated "
                "account email."
            ),
        )

    website_url, normalized_domain = _normalize_website(
        payload.website_url
    )

    return {
        "legal_name": _clean_required(
            payload.legal_name,
            "legal_name",
        ),
        "display_name": _clean_required(
            payload.display_name,
            "display_name",
        ),
        "website_url": website_url,
        "normalized_domain": normalized_domain,
        "business_email": business_email,
        "country_code": _normalize_country_code(
            payload.country_code
        ),
        "registration_number": _clean_optional(
            payload.registration_number
        ),
        "tax_number": _clean_optional(
            payload.tax_number
        ),
        "representative_name": _clean_required(
            payload.representative_name,
            "representative_name",
        ),
        "representative_role": _clean_required(
            payload.representative_role,
            "representative_role",
        ),
    }


def _email_domain_matches_website(
    organization: EmployerOrganization,
) -> bool:
    try:
        email_domain = (
            organization.business_email
            .rsplit("@", 1)[1]
            .lower()
            .rstrip(".")
        )
    except (IndexError, AttributeError):
        return False

    website_domain = (
        organization.normalized_domain
        .lower()
        .rstrip(".")
    )

    return (
        email_domain == website_domain
        or email_domain.endswith(
            f".{website_domain}"
        )
    )


def _organization_response(
    organization: EmployerOrganization,
) -> EmployerOrganizationResponse:
    return EmployerOrganizationResponse(
        id=organization.id,
        owner_user_id=organization.owner_user_id,
        legal_name=organization.legal_name,
        display_name=organization.display_name,
        website_url=organization.website_url,
        normalized_domain=organization.normalized_domain,
        business_email=organization.business_email,
        email_domain_matches_website=(
            _email_domain_matches_website(
                organization
            )
        ),
        country_code=organization.country_code,
        registration_number=organization.registration_number,
        tax_number=organization.tax_number,
        representative_name=organization.representative_name,
        representative_role=organization.representative_role,
        verification_status=organization.verification_status,
        submitted_at=organization.submitted_at,
        reviewed_at=organization.reviewed_at,
        rejection_reason_code=(
            organization.rejection_reason_code
        ),
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


@employer_router.get(
    "",
    response_model=EmployerOrganizationResponse,
)
def get_my_organization(
    current_user: AuthenticatedUser = Depends(
        require_employer_user
    ),
    db: Session = Depends(get_db),
):
    organization = (
        EmployerOrganizationRepository.get_by_owner_user_id(
            db,
            current_user.user_id,
        )
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer organization profile not found.",
        )

    return _organization_response(organization)


@employer_router.post(
    "",
    response_model=EmployerOrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_my_organization(
    payload: EmployerOrganizationWriteRequest,
    current_user: AuthenticatedUser = Depends(
        require_employer_user
    ),
    db: Session = Depends(get_db),
):
    normalized = _normalize_write_payload(
        payload,
        current_user,
    )

    if (
        EmployerOrganizationRepository
        .get_by_owner_user_id(
            db,
            current_user.user_id,
        )
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employer organization profile already exists.",
        )

    try:
        organization = EmployerOrganizationRepository.create(
            db,
            owner_user_id=current_user.user_id,
            **normalized,
        )

        EmployerOrganizationRepository.record_event(
            db,
            organization_id=organization.id,
            action="created",
            previous_status=None,
            new_status="unverified",
        )

        db.commit()
        db.refresh(organization)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employer organization profile already exists.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    return _organization_response(organization)


@employer_router.put(
    "",
    response_model=EmployerOrganizationResponse,
)
def update_my_organization(
    payload: EmployerOrganizationWriteRequest,
    current_user: AuthenticatedUser = Depends(
        require_employer_user
    ),
    db: Session = Depends(get_db),
):
    normalized = _normalize_write_payload(
        payload,
        current_user,
    )

    organization = (
        EmployerOrganizationRepository
        .get_by_owner_user_id_for_update(
            db,
            current_user.user_id,
        )
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer organization profile not found.",
        )

    if organization.verification_status not in {
        "unverified",
        "rejected",
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Organization details cannot be changed while "
                "verification is pending, verified, or suspended."
            ),
        )

    try:
        EmployerOrganizationRepository.update_details(
            db,
            organization,
            **normalized,
        )
        db.commit()
        db.refresh(organization)
    except Exception:
        db.rollback()
        raise

    return _organization_response(organization)


@employer_router.post(
    "/submit",
    response_model=EmployerOrganizationResponse,
)
def submit_my_organization_for_review(
    current_user: AuthenticatedUser = Depends(
        require_employer_user
    ),
    db: Session = Depends(get_db),
):
    organization = (
        EmployerOrganizationRepository
        .get_by_owner_user_id_for_update(
            db,
            current_user.user_id,
        )
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer organization profile not found.",
        )

    previous_status = organization.verification_status

    if previous_status not in {
        "unverified",
        "rejected",
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only unverified or rejected organizations "
                "may be submitted for review."
            ),
        )

    now = datetime.now(timezone.utc)
    action = (
        "resubmitted"
        if previous_status == "rejected"
        else "submitted"
    )

    try:
        EmployerOrganizationRepository.transition_status(
            db,
            organization,
            new_status="pending",
            reviewer_user_id=None,
            rejection_reason_code=None,
            submitted_at=now,
            clear_reviewed_at=True,
        )

        EmployerOrganizationRepository.record_event(
            db,
            organization_id=organization.id,
            action=action,
            previous_status=previous_status,
            new_status="pending",
        )

        db.commit()
        db.refresh(organization)
    except Exception:
        db.rollback()
        raise

    return _organization_response(organization)


@admin_router.get(
    "",
    response_model=list[EmployerOrganizationResponse],
)
def list_organizations_for_review(
    verification_status: VerificationStatus = Query(
        "pending",
        alias="status",
    ),
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    organizations = (
        EmployerOrganizationRepository.list_by_status(
            db,
            verification_status,
        )
    )

    return [
        _organization_response(organization)
        for organization in organizations
    ]


@admin_router.get(
    "/{organization_id}",
    response_model=EmployerOrganizationResponse,
)
def get_organization_for_review(
    organization_id: UUID,
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    organization = EmployerOrganizationRepository.get_by_id(
        db,
        organization_id,
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer organization not found.",
        )

    return _organization_response(organization)


@admin_router.post(
    "/{organization_id}/approve",
    response_model=EmployerOrganizationResponse,
)
def approve_organization(
    organization_id: UUID,
    payload: AdminApprovalRequest,
    admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    organization = (
        EmployerOrganizationRepository.get_by_id_for_update(
            db,
            organization_id,
        )
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer organization not found.",
        )

    if organization.verification_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending organizations may be approved.",
        )

    now = datetime.now(timezone.utc)

    try:
        EmployerOrganizationRepository.transition_status(
            db,
            organization,
            new_status="verified",
            reviewer_user_id=admin_user.user_id,
            rejection_reason_code=None,
            reviewed_at=now,
        )

        EmployerOrganizationRepository.record_event(
            db,
            organization_id=organization.id,
            reviewer_user_id=admin_user.user_id,
            action="approved",
            previous_status="pending",
            new_status="verified",
            internal_note=_clean_optional(
                payload.internal_note
            ),
        )

        (
            db.query(InternshipListing)
            .filter(
                InternshipListing.employer_user_id
                == organization.owner_user_id
            )
            .update(
                {
                    InternshipListing.company:
                    organization.display_name,
                    InternshipListing.employer_organization_id:
                    organization.id,
                    InternshipListing.listing_source:
                    "employer",
                },
                synchronize_session=False,
            )
        )

        db.commit()
        db.refresh(organization)
    except Exception:
        db.rollback()
        raise

    return _organization_response(organization)


@admin_router.post(
    "/{organization_id}/reject",
    response_model=EmployerOrganizationResponse,
)
def reject_organization(
    organization_id: UUID,
    payload: AdminRejectionRequest,
    admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    organization = (
        EmployerOrganizationRepository.get_by_id_for_update(
            db,
            organization_id,
        )
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer organization not found.",
        )

    if organization.verification_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending organizations may be rejected.",
        )

    now = datetime.now(timezone.utc)

    try:
        EmployerOrganizationRepository.transition_status(
            db,
            organization,
            new_status="rejected",
            reviewer_user_id=admin_user.user_id,
            rejection_reason_code=payload.reason_code,
            reviewed_at=now,
        )

        EmployerOrganizationRepository.record_event(
            db,
            organization_id=organization.id,
            reviewer_user_id=admin_user.user_id,
            action="rejected",
            previous_status="pending",
            new_status="rejected",
            reason_code=payload.reason_code,
            internal_note=_clean_optional(
                payload.internal_note
            ),
        )

        db.commit()
        db.refresh(organization)
    except Exception:
        db.rollback()
        raise

    return _organization_response(organization)


@admin_router.post(
    "/{organization_id}/suspend",
    response_model=EmployerOrganizationResponse,
)
def suspend_organization(
    organization_id: UUID,
    payload: AdminSuspensionRequest,
    admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    organization = (
        EmployerOrganizationRepository.get_by_id_for_update(
            db,
            organization_id,
        )
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employer organization not found.",
        )

    if organization.verification_status != "verified":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only verified organizations may be suspended.",
        )

    reason_code = _clean_required(
        payload.reason_code,
        "reason_code",
    )
    now = datetime.now(timezone.utc)

    try:
        EmployerOrganizationRepository.transition_status(
            db,
            organization,
            new_status="suspended",
            reviewer_user_id=admin_user.user_id,
            rejection_reason_code=None,
            reviewed_at=now,
        )

        EmployerOrganizationRepository.record_event(
            db,
            organization_id=organization.id,
            reviewer_user_id=admin_user.user_id,
            action="suspended",
            previous_status="verified",
            new_status="suspended",
            reason_code=reason_code,
            internal_note=_clean_optional(
                payload.internal_note
            ),
        )

        # Suspension must immediately stop current employer-owned
        # opportunities from remaining active.
        (
            db.query(InternshipListing)
            .filter(
                (
                    InternshipListing.employer_organization_id
                    == organization.id
                )
                |
                (
                    InternshipListing.employer_organization_id.is_(None)
                    &
                    (
                        InternshipListing.employer_user_id
                        == organization.owner_user_id
                    )
                )
            )
            .update(
                {
                    InternshipListing.is_active: False,
                },
                synchronize_session=False,
            )
        )

        db.commit()
        db.refresh(organization)
    except Exception:
        db.rollback()
        raise

    return _organization_response(organization)
