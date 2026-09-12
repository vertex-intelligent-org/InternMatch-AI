"""
Public Read-Only and Authenticated Employer Internship Catalog Endpoints
Provides endpoints for browsing, fetching, creating, and retrieving
employer-owned internship listings and applicants.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import AuthenticatedUser, require_employer_user
from app.db.session import get_db
from app.repositories.application import ApplicationRepository
from app.repositories.employer_organization import EmployerOrganizationRepository
from app.repositories.internship import InternshipRepository
from app.repositories.matching_data import MatchingDataRepository
from app.schemas.application import (
    EmployerCVAccessResponse,
    EmployerApplicantListResponse,
    EmployerApplicantResponse,
    EmployerApplicantStatusUpdateRequest,
    EmployerInterviewScheduleRequest,
)
from app.schemas.internship import (
    InternshipCreateRequest,
    InternshipDetailResponse,
    InternshipListResponse,
    InternshipSummaryResponse,
    InternshipUpdateRequest,
)
from app.services.content_translation import translate_internship_content
from app.services.embeddings import generate_embedding
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

logger = get_logger(__name__)
from app.services.cv_storage import (
    CV_SIGNED_URL_EXPIRY_SECONDS,
    CVStorageValidationError,
    generate_candidate_cv_signed_url,
)

router = APIRouter()


def format_not_found_error(message: str) -> Dict[str, Any]:
    """Format standard machine-readable 404 error payload."""
    return {
        "error": {
            "code": "NOT_FOUND",
            "message": message,
            "details": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }


def require_verified_employer_organization(
    db: Session,
    employer_user_id: UUID,
    *,
    lock_for_update: bool,
):
    """
    Require a currently verified employer organization.

    The initial non-locking check rejects ineligible employers before any
    external embedding work. The final FOR UPDATE check runs immediately
    before mutation and serializes publication against admin suspension.
    """
    if lock_for_update:
        organization = (
            EmployerOrganizationRepository
            .get_by_owner_user_id_for_update(
                db,
                employer_user_id,
            )
        )
    else:
        organization = (
            EmployerOrganizationRepository
            .get_by_owner_user_id(
                db,
                employer_user_id,
            )
        )

    if (
        organization is None
        or organization.verification_status != "verified"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "A verified company profile is required to "
                "publish internship opportunities."
            ),
        )

    return organization


@router.post(
    "",
    response_model=InternshipDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_internship(
    payload: InternshipCreateRequest,
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
):
    """
    Create and immediately publish a new employer internship opportunity.
    Requires valid Bearer JWT and verified employer account.
    Generates description embedding synchronously and requires valid embedding
    before persisting the opportunity.
    """
    require_verified_employer_organization(
        db,
        current_user.user_id,
        lock_for_update=False,
    )

    try:
        embedding = generate_embedding(payload.description)
    except Exception as exc:
        logger.warning(
            "Embedding generation failed for employer opportunity creation: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Opportunity publishing is temporarily unavailable.",
        ) from exc

    if (
        not embedding
        or not isinstance(embedding, (list, tuple))
        or len(embedding) != settings.EMBEDDING_DIMENSION
    ):
        logger.warning("Embedding service returned invalid embedding vector.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Opportunity publishing is temporarily unavailable.",
        )

    try:
        organization = require_verified_employer_organization(
            db,
            current_user.user_id,
            lock_for_update=True,
        )

        listing = InternshipRepository.create_employer_listing(
            db=db,
            employer_user_id=current_user.user_id,
            title=payload.title,
            company=organization.display_name,
            location=payload.location,
            work_type=payload.work_type,
            description=payload.description,
            required_skills=payload.required_skills,
            preferred_skills=payload.preferred_skills,
            language=payload.language,
            education_requirements=payload.education_requirements,
            experience_requirements=payload.experience_requirements,
            description_embedding=list(embedding),
        )
        db.commit()
        db.refresh(listing)
    except Exception:
        db.rollback()
        raise

    return InternshipDetailResponse.from_orm_model(listing)



@router.get("", response_model=InternshipListResponse)
def list_internships(
    work_type: Optional[str] = Query(
        None, description="Filter by work type ('remote', 'onsite', 'hybrid')"
    ),
    location: Optional[str] = Query(None, description="Filter by location substring"),
    skill: Optional[str] = Query(
        None, description="Filter by required or preferred skill substring"
    ),
    limit: int = Query(20, ge=1, le=50, description="Pagination limit (default 20, max 50)"),
    offset: int = Query(0, ge=0, description="Pagination offset (default 0)"),
    db: Session = Depends(get_db),
):
    """
    Retrieve the list of curated and employer-published internships with optional filtering.
    Public read-only endpoint.
    """
    items, total = InternshipRepository.list_internships(
        db=db,
        work_type=work_type,
        location=location,
        skill=skill,
        limit=limit,
        offset=offset,
    )
    return InternshipListResponse(
        items=[InternshipSummaryResponse.from_orm_model(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/mine", response_model=InternshipListResponse)
def list_my_internships(
    limit: int = Query(20, ge=1, le=50, description="Pagination limit (default 20, max 50)"),
    offset: int = Query(0, ge=0, description="Pagination offset (default 0)"),
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve internship opportunities created and owned by the authenticated employer.
    Requires authenticated employer account.
    Returns newest-first paginated list.
    """
    items, total = InternshipRepository.list_by_employer(
        db=db,
        employer_user_id=current_user.user_id,
        limit=limit,
        offset=offset,
    )
    return InternshipListResponse(
        items=[InternshipSummaryResponse.from_orm_model(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/{id}", response_model=InternshipDetailResponse)
def update_internship_opportunity(
    id: UUID,
    payload: InternshipUpdateRequest,
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
):
    """
    Update an employer-owned internship opportunity.

    Requires verified employer ownership. Ownership and publication state are
    immutable through this endpoint. Description embeddings are regenerated
    only when the canonical description changes.
    """

    listing = InternshipRepository.get_by_id_and_owner(
        db=db,
        internship_id=id,
        employer_user_id=current_user.user_id,
    )

    if not listing:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error(
                "Internship opportunity not found or not owned by current user."
            ),
        )

    require_verified_employer_organization(
        db,
        current_user.user_id,
        lock_for_update=False,
    )

    description_embedding = None

    if payload.description != listing.description:
        try:
            description_embedding = list(
                generate_embedding(payload.description)
            )
        except Exception as exc:
            logger.warning(
                "Embedding generation failed for employer opportunity update: %s",
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Opportunity updating is temporarily unavailable.",
            ) from exc

    try:
        organization = require_verified_employer_organization(
            db,
            current_user.user_id,
            lock_for_update=True,
        )

        updated_listing = InternshipRepository.update_employer_listing(
            db=db,
            listing=listing,
            title=payload.title,
            company=organization.display_name,
            location=payload.location,
            work_type=payload.work_type,
            description=payload.description,
            required_skills=payload.required_skills,
            preferred_skills=payload.preferred_skills,
            language=payload.language,
            education_requirements=payload.education_requirements,
            experience_requirements=payload.experience_requirements,
            description_embedding=description_embedding,
        )
        db.commit()
        db.refresh(updated_listing)
    except Exception:
        db.rollback()
        raise

    return InternshipDetailResponse.from_orm_model(updated_listing)


@router.get("/{id}/applicants", response_model=EmployerApplicantListResponse)
def list_internship_applicants(
    id: UUID,
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve all submitted applicants (status != 'saved') for an employer's opportunity.
    Requires authenticated employer account and listing ownership.
    Returns 404 if the opportunity is not found or owned by another employer.
    """
    listing = InternshipRepository.get_by_id_and_owner(
        db=db,
        internship_id=id,
        employer_user_id=current_user.user_id,
    )
    if not listing:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error("Internship opportunity not found."),
        )

    records = ApplicationRepository.list_applicants_for_employer_internship(
        db=db,
        internship_id=id,
        employer_user_id=current_user.user_id,
    )

    # Employer AI ranking uses the canonical persisted hybrid match score.
    # Candidates without a calculated Match are placed after scored candidates.
    # Stable application timestamps provide deterministic tie-breaking.
    ranked_records = sorted(
        records,
        key=lambda record: (
            record[2] is None,
            -(record[2].overall_score if record[2] is not None else -1),
            record[0].applied_date is None,
            -(record[0].applied_date.toordinal() if record[0].applied_date else 0),
            str(record[0].id),
        ),
    )

    items = []
    scored_rank = 0

    for app, profile, match in ranked_records:
        ai_rank = None

        if match is not None:
            scored_rank += 1
            ai_rank = scored_rank

        skills = MatchingDataRepository.get_skill_names_for_student(db, profile.id)

        items.append(
            EmployerApplicantResponse.from_orm_data(
                application=app,
                profile=profile,
                match=match,
                skills=skills,
                ai_rank=ai_rank,
            )
        )

    return EmployerApplicantListResponse(
        items=items,
        total=len(items),
        internship_id=id,
    )



@router.get(
    "/{id}/applicants/{application_id}/cv",
    response_model=EmployerCVAccessResponse,
)
def get_employer_applicant_cv(
    id: UUID,
    application_id: UUID,
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
):
    """
    Return short-lived access to the current CV for a submitted applicant.

    Authorization is application-scoped and server-authoritative:
    - authenticated account must be an employer
    - opportunity must belong to that employer
    - application must belong to that opportunity
    - draft/saved applications are not visible
    - candidate identity and CV storage path are resolved server-side
    """
    record = ApplicationRepository.get_applicant_detail_for_employer(
        db=db,
        internship_id=id,
        application_id=application_id,
        employer_user_id=current_user.user_id,
    )

    if not record:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error(
                "Applicant record not found for this opportunity."
            ),
        )

    application, profile, _match = record

    if application.status == "saved":
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error(
                "Applicant record not found for this opportunity."
            ),
        )

    storage_path = profile.cv_storage_path

    if not storage_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate CV is not available.",
        )

    try:
        signed_url = generate_candidate_cv_signed_url(
            user_id=profile.user_id,
            storage_path=storage_path,
            expires_in=CV_SIGNED_URL_EXPIRY_SECONDS,
        )
    except CVStorageValidationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Candidate CV is temporarily unavailable.",
        )

    extension = storage_path.rsplit(".", 1)[-1].lower()

    return EmployerCVAccessResponse(
        cv_url=signed_url,
        expires_in=CV_SIGNED_URL_EXPIRY_SECONDS,
        file_type=extension,
    )


@router.post("/{id}/close", response_model=InternshipDetailResponse)
def close_internship_opportunity(
    id: UUID,
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
):
    """
    Close an employer-owned internship opportunity.
    Closed opportunities are removed from public candidate discovery and matching,
    while existing applications and employer listing history are preserved.
    Requires verified employer ownership.
    """
    listing = InternshipRepository.get_by_id_and_owner(
        db=db,
        internship_id=id,
        employer_user_id=current_user.user_id,
    )
    if not listing:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error(
                "Internship opportunity not found or not owned by current user."
            ),
        )

    try:
        updated_listing = InternshipRepository.close_listing(db=db, listing=listing)
        db.commit()
        db.refresh(updated_listing)
    except Exception:
        db.rollback()
        raise

    return InternshipDetailResponse.from_orm_model(updated_listing)


@router.get("/{id}/applicants/{application_id}", response_model=EmployerApplicantResponse)
def get_internship_applicant_detail(
    id: UUID,
    application_id: UUID,
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve detailed applicant information for an employer-owned opportunity.
    Requires authenticated employer account and listing ownership.
    Returns 404 if not found or unauthorized.
    """
    record = ApplicationRepository.get_applicant_detail_for_employer(
        db=db,
        internship_id=id,
        application_id=application_id,
        employer_user_id=current_user.user_id,
    )
    if not record:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error("Applicant record not found."),
        )

    app, profile, match = record
    skills = MatchingDataRepository.get_skill_names_for_student(db, profile.id)
    skill_evidence = MatchingDataRepository.get_skill_evidence_for_student(
        db,
        profile.id,
    )

    return EmployerApplicantResponse.from_orm_data(
        application=app,
        profile=profile,
        match=match,
        skills=skills,
        skill_evidence=skill_evidence,
    )


@router.post(
    "/{id}/applicants/{application_id}/interview",
    response_model=EmployerApplicantResponse,
)
def schedule_employer_applicant_interview(
    id: UUID,
    application_id: UUID,
    payload: EmployerInterviewScheduleRequest,
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
):
    """
    Create or reschedule the canonical interview for an applicant.

    First scheduling:
      - applied -> interviewing

    Rescheduling:
      - interviewing remains interviewing
      - no duplicate status event is created

    saved applications cannot be scheduled.
    accepted/rejected applications are terminal.

    Interview persistence and lifecycle transition are committed atomically.
    """
    record = ApplicationRepository.get_applicant_detail_for_employer(
        db=db,
        internship_id=id,
        application_id=application_id,
        employer_user_id=current_user.user_id,
    )

    if not record:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error(
                "Applicant record not found for this opportunity."
            ),
        )

    app, profile, match = record

    if app.status == "saved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot schedule interview for draft application. "
                "Candidate has not submitted yet."
            ),
        )

    if app.status in ("accepted", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Application is in terminal '{app.status}' status "
                "and cannot be scheduled."
            ),
        )

    if app.status not in ("applied", "interviewing"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot schedule interview while application "
                f"is '{app.status}'."
            ),
        )

    if (
        payload.scheduled_at.tzinfo is None
        or payload.scheduled_at.utcoffset() is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Interview scheduled_at must include a timezone offset.",
        )

    normalized_location = payload.location.strip()

    if not normalized_location:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Interview location or meeting URL is required.",
        )

    normalized_message = (
        payload.message.strip()
        if payload.message and payload.message.strip()
        else None
    )

    try:
        app.interview_scheduled_at = payload.scheduled_at
        app.interview_mode = payload.mode
        app.interview_location = normalized_location
        app.interview_message = normalized_message

        if app.status == "applied":
            ApplicationRepository.update_status(
                db=db,
                application=app,
                status="interviewing",
            )

        db.commit()
        db.refresh(app)

    except Exception:
        db.rollback()
        raise

    skills = MatchingDataRepository.get_skill_names_for_student(
        db,
        profile.id,
    )

    return EmployerApplicantResponse.from_orm_data(
        application=app,
        profile=profile,
        match=match,
        skills=skills,
    )


@router.patch(
    "/{id}/applicants/{application_id}/status",
    response_model=EmployerApplicantResponse,
)
def update_employer_applicant_status(
    id: UUID,
    application_id: UUID,
    payload: EmployerApplicantStatusUpdateRequest,
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
):
    """
    Transition applicant status for an employer-owned opportunity.
    Enforces valid recruiter lifecycle state machine:
      - applied -> interviewing, accepted, rejected
      - interviewing -> accepted, rejected
      - accepted (terminal) -> no transitions
      - rejected (terminal) -> no transitions
      - saved -> cannot be updated by employer
    Creates an authoritative ApplicationStatusEvent timeline entry.
    Requires verified employer ownership.
    """
    record = ApplicationRepository.get_applicant_detail_for_employer(
        db=db,
        internship_id=id,
        application_id=application_id,
        employer_user_id=current_user.user_id,
    )
    if not record:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error(
                "Applicant record not found for this opportunity."
            ),
        )

    app, profile, match = record
    current_status = app.status
    target_status = payload.status

    # Enforce strict transition rules
    if current_status == "saved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update status for draft application. Candidate has not submitted yet.",
        )

    if current_status in ("accepted", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Application is in terminal '{current_status}' status and cannot be modified.",
        )

    valid_transitions = {
        "applied": {"interviewing", "accepted", "rejected"},
        "interviewing": {"accepted", "rejected"},
    }

    allowed = valid_transitions.get(current_status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status transition from '{current_status}' to '{target_status}'.",
        )

    try:
        updated_app = ApplicationRepository.update_status(
            db=db,
            application=app,
            status=target_status,
            notes=payload.notes,
            notes_provided=payload.notes is not None,
        )
        db.commit()
        db.refresh(updated_app)
    except Exception:
        db.rollback()
        raise

    skills = MatchingDataRepository.get_skill_names_for_student(db, profile.id)
    return EmployerApplicantResponse.from_orm_data(
        application=updated_app,
        profile=profile,
        match=match,
        skills=skills,
    )


@router.get("/{id}", response_model=InternshipDetailResponse)
def get_internship_detail(
    id: UUID,
    locale: Literal["en", "tr", "ar"] = Query(
        "en", description="Target content display locale ('en', 'tr', 'ar')"
    ),
    db: Session = Depends(get_db),
):
    """
    Retrieve complete details of a specific internship listing.
    Public read-only endpoint.
    When locale is 'tr' or 'ar', free-form explanatory content is localized dynamically.
    """
    listing = InternshipRepository.get_public_by_id(
        db=db,
        internship_id=id,
    )
    if not listing:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error("Internship listing not found."),
        )

    base_response = InternshipDetailResponse.from_orm_model(listing)

    if locale in ("tr", "ar"):
        translated_desc, translated_edu = translate_internship_content(
            internship_id=listing.id,
            description=listing.description,
            min_education=listing.education_requirements,
            target_locale=locale,
        )
        return base_response.model_copy(
            update={
                "description": translated_desc
                if translated_desc is not None
                else base_response.description,
                "min_education": translated_edu
                if translated_edu is not None
                else base_response.min_education,
            }
        )

    return base_response
