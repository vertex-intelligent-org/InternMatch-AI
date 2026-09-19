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
from app.db.models import ProcessingJob
from app.db.session import get_db
from app.repositories.application import ApplicationRepository
from app.repositories.employer_organization import EmployerOrganizationRepository
from app.repositories.internship import InternshipRepository
from app.repositories.matching_data import MatchingDataRepository
from app.repositories.notification import NotificationRepository
from app.schemas.application import (
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
from app.services.ai_quota import (
    AIQuotaExceededError,
    AIQuotaIdempotencyConflictError,
)
from app.services.ai_quota_integration import (
    build_ai_request_fingerprint,
    format_ai_idempotency_conflict_payload,
    format_ai_quota_exceeded_payload,
)
from app.services.content_translation import translate_internship_content
from app.services.cv_storage import (
    CVStorageValidationError,
    download_candidate_cv,
)
from app.services.embeddings import generate_embedding
from app.services.employer_ai_quota import (
    EMPLOYER_CANDIDATE_INSIGHT,
    EMPLOYER_INTERNSHIP_DESCRIPTION,
    EMPLOYER_INTERVIEW_KIT,
    EMPLOYER_SHORTLIST_COMPARISON,
    EmployerAIQuotaAccessError,
    EmployerAIQuotaConfigurationError,
    execute_employer_ai_with_quota,
)
from app.services.employer_candidate_insight import (
    EmployerCandidateInsightResponse,
    generate_employer_candidate_insight,
)
from app.services.employer_internship_description import (
    EmployerInternshipDescriptionRequest,
    EmployerInternshipDescriptionResponse,
    generate_employer_internship_description,
)
from app.services.employer_interview_kit import (
    EmployerInterviewKitResponse,
    generate_employer_interview_kit,
)
from app.services.employer_pipeline_analytics import (
    EmployerPipelineAnalyticsResponse,
    get_employer_pipeline_analytics,
)
from app.services.employer_product_policy import (
    FEATURE_INTERNSHIP_DESCRIPTION,
    FEATURE_INTERVIEW_KIT,
    FEATURE_PIPELINE_ANALYTICS,
    FEATURE_SHORTLIST_COMPARISON,
    EmployerFeatureAccessError,
    EmployerListingLimitError,
    EmployerProductPolicyResponse,
    get_employer_product_policy,
    require_employer_feature,
    require_employer_listing_capacity,
)
from app.services.employer_shortlist_comparison import (
    EmployerShortlistComparisonRequest,
    EmployerShortlistComparisonResponse,
    generate_employer_shortlist_comparison,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

logger = get_logger(__name__)

router = APIRouter()


def _execute_employer_ai_with_quota_response(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
    idempotency_key: str | None,
    request_fingerprint: str,
    callback,
):
    """Run one Employer AI request through durable product-unit quota."""

    if idempotency_key is None or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Idempotency-Key header is required "
                "for Employer AI requests."
            ),
        )

    try:
        return execute_employer_ai_with_quota(
            db,
            user_id=user_id,
            feature_key=feature_key,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            callback=callback,
        )
    except AIQuotaExceededError as exc:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=format_ai_quota_exceeded_payload(exc),
        )
    except AIQuotaIdempotencyConflictError:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=format_ai_idempotency_conflict_payload(),
        )
    except EmployerAIQuotaAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except EmployerAIQuotaConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Employer AI usage policy is "
                "not configured."
            ),
        ) from exc


def _require_employer_feature(
    db: Session,
    *,
    user_id: UUID,
    feature_key: str,
) -> None:
    """Translate backend product-policy denial to an API 403."""

    try:
        require_employer_feature(
            db,
            user_id=user_id,
            feature_key=feature_key,
        )
    except EmployerFeatureAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Employer Pro is required "
                "for this feature."
            ),
        ) from exc


_ACTIVE_MATCH_JOB_STATUSES = ("queued", "processing")


def _active_match_calculation_user_ids(db: Session, user_ids) -> set:
    """
    Return candidate auth user IDs with an authoritative active match job.

    Employer-facing ranking must fail closed while recalculation is queued
    or processing so a previously persisted score is never presented as fresh.
    """
    normalized_user_ids = {
        user_id
        for user_id in user_ids
        if user_id is not None
    }

    if not normalized_user_ids:
        return set()

    rows = (
        db.query(ProcessingJob.user_id)
        .filter(
            ProcessingJob.user_id.in_(normalized_user_ids),
            ProcessingJob.job_type == "match_calculation",
            ProcessingJob.status.in_(_ACTIVE_MATCH_JOB_STATUSES),
        )
        .distinct()
        .all()
    )

    return {row[0] for row in rows}


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

        try:
            require_employer_listing_capacity(
                db,
                user_id=current_user.user_id,
            )
        except EmployerListingLimitError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Employer Free supports one "
                    "published internship at a time. "
                    "Close the current internship or "
                    "upgrade to Employer Pro."
                ),
            ) from exc

        listing = InternshipRepository.create_employer_listing(
            db=db,
            employer_user_id=current_user.user_id,
            employer_organization_id=organization.id,
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
        NotificationRepository.create_for_admins(
            db,
            event_type="listing_review_requested",
            entity_type="internship",
            entity_id=listing.id,
            data={
                "internship_id": str(
                    listing.id
                ),
                "organization_id": str(
                    organization.id
                ),
                "title": listing.title,
                "company": listing.company,
                "publication_status":
                    "under_review",
            },
            dedupe_key=(
                f"internship:{listing.id}:"
                "review-requested:create"
            ),
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



@router.get(
    "/mine/{id}",
    response_model=InternshipDetailResponse,
)
def get_my_internship_detail(
    id: UUID,
    current_user: AuthenticatedUser = Depends(
        require_employer_user
    ),
    db: Session = Depends(get_db),
):
    """
    Return one internship owned by the authenticated employer.

    This owner-only endpoint intentionally does not apply public
    visibility rules so an employer can reopen and edit a listing
    that is under review, draft, closed, or otherwise non-public.

    Cross-employer access returns 404.
    """
    listing = InternshipRepository.get_by_id_and_owner(
        db=db,
        internship_id=id,
        employer_user_id=current_user.user_id,
    )

    if listing is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error(
                "Internship opportunity not found or "
                "not owned by current user."
            ),
        )

    return InternshipDetailResponse.from_orm_model(
        listing
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

    Requires verified employer ownership. Ownership is immutable through this
    endpoint. Any successful employer edit returns the listing to draft/hidden
    state so administrative review is required again before publication.
    Description embeddings are regenerated only when the canonical description
    changes.
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
        review_requested_at = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        NotificationRepository.create_for_admins(
            db,
            event_type="listing_review_requested",
            entity_type="internship",
            entity_id=updated_listing.id,
            data={
                "internship_id": str(
                    updated_listing.id
                ),
                "organization_id": str(
                    organization.id
                ),
                "title":
                    updated_listing.title,
                "company":
                    updated_listing.company,
                "publication_status":
                    "under_review",
            },
            dedupe_key=(
                f"internship:"
                f"{updated_listing.id}:"
                "review-requested:"
                f"{review_requested_at}"
            ),
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

    active_match_user_ids = _active_match_calculation_user_ids(
        db,
        (profile.user_id for _, profile, _ in records),
    )

    # Fail closed for recruiter ranking while a candidate recalculation is
    # queued or processing. Persisted rows may belong to the previous
    # calculation and must not be presented as current during that window.
    freshness_safe_records = [
        (
            application,
            profile,
            None if profile.user_id in active_match_user_ids else match,
        )
        for application, profile, match in records
    ]

    # Employer AI ranking uses the canonical persisted hybrid match score.
    # Candidates without a calculated Match are placed after scored candidates.
    # Stable application timestamps provide deterministic tie-breaking.
    ranked_records = sorted(
        freshness_safe_records,
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
    "/{id}/applicants/{application_id}/cv/content",
)
def download_employer_applicant_cv_content(
    id: UUID,
    application_id: UUID,
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
):
    """
    Stream a submitted candidate CV through the authenticated InternMatch API.

    Security boundary:
    - caller must have an authenticated employer session
    - opportunity must belong to the authenticated employer
    - application must belong to that opportunity
    - saved/draft applications remain invisible
    - the private storage path is resolved only on the server
    - the storage provider URL/token is never returned to the client
    - every download request re-runs authorization
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

    storage_object_path = profile.cv_storage_path

    if not storage_object_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate CV is not available.",
        )

    try:
        document_bytes = download_candidate_cv(
            user_id=profile.user_id,
            storage_path=storage_object_path,
        )
    except CVStorageValidationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Candidate CV is temporarily unavailable.",
        )

    extension = storage_object_path.rsplit(".", 1)[-1].lower()

    media_types = {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    }

    media_type = media_types.get(
        extension,
        "application/octet-stream",
    )

    safe_extension = extension if extension in media_types else "bin"

    return Response(
        content=document_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'inline; filename="candidate-cv.{safe_extension}"'
            ),
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_internship_opportunity(
    id: UUID,
    current_user: AuthenticatedUser = Depends(
        require_employer_user
    ),
    db: Session = Depends(get_db),
):
    """
    Permanently delete an employer-owned opportunity only before any
    candidate has started an application.

    Once an Application exists, the opportunity must be closed instead so
    candidate-authored history and tracker context are preserved.
    """
    listing = (
        InternshipRepository
        .get_by_id_and_owner_for_update(
            db=db,
            internship_id=id,
            employer_user_id=(
                current_user.user_id
            ),
        )
    )

    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Internship opportunity not found "
                "or not owned by current user."
            ),
        )

    application_count = (
        ApplicationRepository
        .count_for_internship(
            db=db,
            internship_id=id,
        )
    )

    if application_count > 0:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This opportunity cannot be permanently deleted "
                "because a candidate has already started an "
                "application. Close the opportunity instead."
            ),
        )

    try:
        InternshipRepository.delete_listing(
            db=db,
            listing=listing,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
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

    if profile.user_id in _active_match_calculation_user_ids(
        db,
        (profile.user_id,),
    ):
        match = None
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

    if profile.user_id in _active_match_calculation_user_ids(
        db,
        (profile.user_id,),
    ):
        match = None

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


@router.post(
    "/{id}/applicants/{application_id}/insight",
    response_model=EmployerCandidateInsightResponse,
)
def generate_employer_applicant_insight(
    id: UUID,
    application_id: UUID,
    content_locale: str = "en",
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    """Generate grounded professional candidate insight for an owned applicant.

    This endpoint is intentionally decision support only. Employer Pro
    entitlement/quota enforcement is added in the product-policy gate before
    production enablement.
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
                "Applicant record not found."
            ),
        )

    application, profile, match = record

    if match is None or match.overall_score is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Candidate insight requires a calculated match."
            ),
        )

    fingerprint = build_ai_request_fingerprint(
        {
            "operation": "employer_candidate_insight",
            "internship_id": str(id),
            "application_id": str(application_id),
            "content_locale": content_locale,
        }
    )

    return _execute_employer_ai_with_quota_response(
        db,
        user_id=current_user.user_id,
        feature_key=EMPLOYER_CANDIDATE_INSIGHT,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        callback=lambda: generate_employer_candidate_insight(
            db,
            employer_user_id=current_user.user_id,
            application=application,
            profile=profile,
            match=match,
            internship_id=id,
            content_locale=content_locale,
        ),
    )


@router.post(
    "/{id}/applicants/{application_id}/interview-kit",
    response_model=EmployerInterviewKitResponse,
)
def generate_employer_applicant_interview_kit(
    id: UUID,
    application_id: UUID,
    content_locale: str = "en",
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    """Generate a grounded, human-led employer interview kit.

    Employer Pro entitlement/quota enforcement is intentionally deferred to
    the product-policy gate before production enablement.
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
                "Applicant record not found."
            ),
        )

    application, profile, match = record

    if match is None or match.overall_score is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Employer interview kit requires a calculated match."
            ),
        )

    _require_employer_feature(
        db,
        user_id=current_user.user_id,
        feature_key=FEATURE_INTERVIEW_KIT,
    )

    fingerprint = build_ai_request_fingerprint(
        {
            "operation": "employer_interview_kit",
            "internship_id": str(id),
            "application_id": str(application_id),
            "content_locale": content_locale,
        }
    )

    return _execute_employer_ai_with_quota_response(
        db,
        user_id=current_user.user_id,
        feature_key=EMPLOYER_INTERVIEW_KIT,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        callback=lambda: generate_employer_interview_kit(
            db,
            employer_user_id=current_user.user_id,
            application=application,
            profile=profile,
            match=match,
            internship_id=id,
            content_locale=content_locale,
        ),
    )


@router.post(
    "/{id}/shortlist-comparison",
    response_model=EmployerShortlistComparisonResponse,
)
def compare_employer_shortlist(
    id: UUID,
    payload: EmployerShortlistComparisonRequest,
    content_locale: str = "en",
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    """Compare 2-5 owned applicants without ranking.

    Employer Pro entitlement/quota enforcement is intentionally
    added later in the product-policy gate before production.
    """

    if len(set(payload.application_ids)) != len(
        payload.application_ids
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Duplicate application IDs "
                "are not allowed."
            ),
        )

    records = []

    for application_id in payload.application_ids:
        record = (
            ApplicationRepository
            .get_applicant_detail_for_employer(
                db=db,
                internship_id=id,
                application_id=application_id,
                employer_user_id=(
                    current_user.user_id
                ),
            )
        )

        if not record:
            return JSONResponse(
                status_code=(
                    status.HTTP_404_NOT_FOUND
                ),
                content=format_not_found_error(
                    "Applicant record not found."
                ),
            )

        application, profile, match = record

        if (
            match is None
            or match.overall_score is None
        ):
            raise HTTPException(
                status_code=(
                    status.HTTP_409_CONFLICT
                ),
                detail=(
                    "Shortlist comparison requires "
                    "calculated matches for every "
                    "applicant."
                ),
            )

        records.append(
            (
                application,
                profile,
                match,
            )
        )

    _require_employer_feature(
        db,
        user_id=current_user.user_id,
        feature_key=FEATURE_SHORTLIST_COMPARISON,
    )

    fingerprint = build_ai_request_fingerprint(
        {
            "operation": "employer_shortlist_comparison",
            "internship_id": str(id),
            "application_ids": [
                str(value)
                for value in payload.application_ids
            ],
            "content_locale": content_locale,
        }
    )

    return _execute_employer_ai_with_quota_response(
        db,
        user_id=current_user.user_id,
        feature_key=EMPLOYER_SHORTLIST_COMPARISON,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        callback=lambda: generate_employer_shortlist_comparison(
            db,
            employer_user_id=current_user.user_id,
            internship_id=id,
            records=records,
            content_locale=content_locale,
        ),
    )


@router.post(
    "/employer-tools/description-assistant",
    response_model=EmployerInternshipDescriptionResponse,
)
def generate_employer_internship_description_draft(
    payload: EmployerInternshipDescriptionRequest,
    content_locale: str = "en",
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    """Generate an editable internship-description draft only.

    This endpoint does not create, publish, activate, or update an
    internship listing. Employer Pro entitlement and quota policy
    are added later before production enablement.
    """

    _require_employer_feature(
        db,
        user_id=current_user.user_id,
        feature_key=FEATURE_INTERNSHIP_DESCRIPTION,
    )

    fingerprint = build_ai_request_fingerprint(
        {
            "operation": "employer_internship_description",
            "payload": payload.model_dump(
                mode="json"
            ),
            "content_locale": content_locale,
        }
    )

    return _execute_employer_ai_with_quota_response(
        db,
        user_id=current_user.user_id,
        feature_key=EMPLOYER_INTERNSHIP_DESCRIPTION,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        callback=lambda: generate_employer_internship_description(
            employer_user_id=current_user.user_id,
            payload=payload,
            content_locale=content_locale,
        ),
    )


@router.get(
    "/employer-tools/product-policy",
    response_model=EmployerProductPolicyResponse,
)
def get_employer_product_policy_endpoint(
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
):
    """Return backend-authoritative Employer Free/Pro capabilities."""

    return get_employer_product_policy(
        db,
        user_id=current_user.user_id,
    )


@router.get(
    "/employer-tools/pipeline-analytics",
    response_model=EmployerPipelineAnalyticsResponse,
)
def get_employer_pipeline_analytics_endpoint(
    current_user: AuthenticatedUser = Depends(require_employer_user),
    db: Session = Depends(get_db),
):
    """Return a deterministic current hiring-pipeline snapshot."""

    _require_employer_feature(
        db,
        user_id=current_user.user_id,
        feature_key=FEATURE_PIPELINE_ANALYTICS,
    )

    return get_employer_pipeline_analytics(
        db,
        employer_user_id=current_user.user_id,
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

    if profile.user_id in _active_match_calculation_user_ids(
        db,
        (profile.user_id,),
    ):
        match = None
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
