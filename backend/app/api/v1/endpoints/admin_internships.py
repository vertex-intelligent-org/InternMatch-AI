"""Server-authorized administration of internship listings."""

import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from app.core.config import settings
from app.core.security import AuthenticatedUser, require_admin_user
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
    AdminInternshipChangesRequest,
    AdminInternshipCreateRequest,
    AdminInternshipDetailResponse,
    InternshipDetailResponse,
    InternshipListResponse,
    InternshipSummaryResponse,
)
from app.services.embeddings import generate_embedding
from app.services.employer_product_policy import (
    EmployerListingLimitError,
    require_employer_listing_capacity,
)
from app.services.opportunity_alert_enqueue import (
    enqueue_new_opportunity_alert_fanout,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter()

PublicationStatus = Literal[
    "draft",
    "under_review",
    "published",
    "closed",
]


@router.get(
    "",
    response_model=InternshipListResponse,
)
def list_admin_internships(
    publication_status: Optional[PublicationStatus] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    _admin_user: AuthenticatedUser = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """List internship listings across all publication states."""
    if publication_status == "published":
        # Published in the admin console means candidate-visible,
        # not merely a raw database status label.
        items, total = InternshipRepository.list_internships(
            db=db,
            limit=limit,
            offset=offset,
        )
    else:
        items, total = InternshipRepository.list_for_admin(
            db=db,
            publication_status=publication_status,
            limit=limit,
            offset=offset,
        )

    return InternshipListResponse(
        items=[
            InternshipSummaryResponse.from_orm_model(item)
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=InternshipDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_internship(
    payload: AdminInternshipCreateRequest,
    admin_user: AuthenticatedUser = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """
    Create an administrator-curated internship opportunity.

    The listing is never attributed to an employer account. Administrators
    may create either a hidden draft or an immediately public curated
    opportunity.
    """
    try:
        embedding = generate_embedding(payload.description)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Opportunity creation is temporarily unavailable."
            ),
        ) from exc

    if (
        not embedding
        or not isinstance(embedding, (list, tuple))
        or len(embedding) != settings.EMBEDDING_DIMENSION
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Opportunity creation is temporarily unavailable."
            ),
        )

    try:
        listing = InternshipRepository.create_curated_listing(
            db=db,
            title=payload.title,
            company=payload.company,
            location=payload.location,
            work_type=payload.work_type,
            description=payload.description,
            required_skills=payload.required_skills,
            preferred_skills=payload.preferred_skills,
            language=payload.language,
            education_requirements=payload.education_requirements,
            experience_requirements=payload.experience_requirements,
            publication_status=payload.publication_status,
            description_embedding=list(embedding),
            metadata={
                "created_via": "admin_console",
                "created_by_admin_user_id": str(
                    admin_user.user_id
                ),
            },
        )
        db.commit()
        db.refresh(listing)
    except Exception:
        db.rollback()
        raise

    return InternshipDetailResponse.from_orm_model(
        listing
    )


def _get_admin_managed_listing(
    db: Session,
    internship_id: UUID,
    *,
    for_update: bool = False,
):
    """
    Return only a first-party admin-console curated listing.

    Admin moderation remains allowed elsewhere for employer listings,
    but recruiter actions must never cross the employer ownership
    boundary.
    """
    if for_update:
        listing = (
            InternshipRepository
            .get_by_id_for_update(
                db=db,
                internship_id=internship_id,
            )
        )
    else:
        listing = (
            InternshipRepository
            .get_by_id(
                db=db,
                internship_id=internship_id,
            )
        )

    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internship listing not found.",
        )

    metadata = (
        listing.metadata_json
        if isinstance(
            listing.metadata_json,
            dict,
        )
        else {}
    )

    admin_managed = (
        listing.listing_source
        == "curated"
        and listing.employer_user_id
        is None
        and listing.employer_organization_id
        is None
        and metadata.get("created_via")
        == "admin_console"
    )

    if not admin_managed:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Admin recruiter actions are limited "
                "to opportunities created by the "
                "admin console. Employer-owned "
                "opportunities must be managed by "
                "their employer."
            ),
        )

    return listing


def _admin_applicant_response(
    db: Session,
    application,
    profile,
) -> EmployerApplicantResponse:
    skills = (
        MatchingDataRepository
        .get_skill_names_for_student(
            db,
            profile.id,
        )
    )

    skill_evidence = (
        MatchingDataRepository
        .get_skill_evidence_for_student(
            db,
            profile.id,
        )
    )

    # Deliberately omit recruiter ranking/match scoring from the admin
    # workflow. Admin actions operate on candidate status and evidence,
    # not automated ranking.
    return EmployerApplicantResponse.from_orm_data(
        application=application,
        profile=profile,
        match=None,
        skills=skills,
        skill_evidence=skill_evidence,
        ai_rank=None,
    )


@router.get(
    "/{id}/applicants",
    response_model=EmployerApplicantListResponse,
)
def list_admin_internship_applicants(
    id: UUID,
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    _get_admin_managed_listing(
        db=db,
        internship_id=id,
    )

    records = (
        ApplicationRepository
        .list_applicants_for_admin_internship(
            db=db,
            internship_id=id,
        )
    )

    items = [
        _admin_applicant_response(
            db,
            application,
            profile,
        )
        for application, profile
        in records
    ]

    return EmployerApplicantListResponse(
        items=items,
        total=len(items),
        internship_id=id,
    )


@router.get(
    "/{id}/applicants/{application_id}",
    response_model=EmployerApplicantResponse,
)
def get_admin_internship_applicant(
    id: UUID,
    application_id: UUID,
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    _get_admin_managed_listing(
        db=db,
        internship_id=id,
    )

    record = (
        ApplicationRepository
        .get_applicant_detail_for_admin(
            db=db,
            internship_id=id,
            application_id=application_id,
        )
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Applicant record not found.",
        )

    application, profile = record

    return _admin_applicant_response(
        db,
        application,
        profile,
    )


@router.patch(
    "/{id}/applicants/{application_id}/status",
    response_model=EmployerApplicantResponse,
)
def update_admin_internship_applicant_status(
    id: UUID,
    application_id: UUID,
    payload: EmployerApplicantStatusUpdateRequest,
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    _get_admin_managed_listing(
        db=db,
        internship_id=id,
    )

    record = (
        ApplicationRepository
        .get_applicant_detail_for_admin(
            db=db,
            internship_id=id,
            application_id=application_id,
        )
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Applicant record not found.",
        )

    application, profile = record

    current_status = application.status
    target_status = payload.status

    if current_status in (
        "accepted",
        "rejected",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Application is already in terminal "
                f"'{current_status}' status."
            ),
        )

    valid_transitions = {
        "applied": {
            "interviewing",
            "accepted",
            "rejected",
        },
        "interviewing": {
            "accepted",
            "rejected",
        },
    }

    if (
        target_status
        not in valid_transitions.get(
            current_status,
            set(),
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid status transition from "
                f"'{current_status}' to "
                f"'{target_status}'."
            ),
        )

    try:
        updated = (
            ApplicationRepository
            .update_status(
                db=db,
                application=application,
                status=target_status,
                notes=payload.notes,
                notes_provided=(
                    payload.notes is not None
                ),
            )
        )
        db.commit()
        db.refresh(updated)
    except Exception:
        db.rollback()
        raise

    return _admin_applicant_response(
        db,
        updated,
        profile,
    )


@router.post(
    "/{id}/applicants/{application_id}/interview",
    response_model=EmployerApplicantResponse,
)
def schedule_admin_internship_applicant_interview(
    id: UUID,
    application_id: UUID,
    payload: EmployerInterviewScheduleRequest,
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    _get_admin_managed_listing(
        db=db,
        internship_id=id,
    )

    record = (
        ApplicationRepository
        .get_applicant_detail_for_admin(
            db=db,
            internship_id=id,
            application_id=application_id,
        )
    )

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Applicant record not found.",
        )

    application, profile = record

    if application.status in (
        "accepted",
        "rejected",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "A terminal application cannot "
                "be scheduled for interview."
            ),
        )

    if application.status not in (
        "applied",
        "interviewing",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only applied or interviewing "
                "applications can be scheduled."
            ),
        )

    if (
        payload.scheduled_at.tzinfo is None
        or payload.scheduled_at.utcoffset()
        is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Interview scheduled_at must "
                "include a timezone offset."
            ),
        )

    normalized_location = (
        payload.location.strip()
    )

    if not normalized_location:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Interview location or meeting "
                "URL is required."
            ),
        )

    normalized_message = (
        payload.message.strip()
        if (
            payload.message
            and payload.message.strip()
        )
        else None
    )

    try:
        application.interview_scheduled_at = (
            payload.scheduled_at
        )
        application.interview_mode = (
            payload.mode
        )
        application.interview_location = (
            normalized_location
        )
        application.interview_message = (
            normalized_message
        )

        if application.status == "applied":
            ApplicationRepository.update_status(
                db=db,
                application=application,
                status="interviewing",
            )

        db.commit()
        db.refresh(application)
    except Exception:
        db.rollback()
        raise

    return _admin_applicant_response(
        db,
        application,
        profile,
    )


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_admin_internship(
    id: UUID,
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    """
    Permanently delete a listing only when no candidate has started an
    application. Otherwise the admin must close the listing instead.
    """
    listing = _get_admin_managed_listing(
        db=db,
        internship_id=id,
        for_update=True,
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


@router.get(
    "/{id}",
    response_model=AdminInternshipDetailResponse,
)
def get_admin_internship(
    id: UUID,
    _admin_user: AuthenticatedUser = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Read one listing without applying public visibility rules."""
    listing = InternshipRepository.get_by_id(
        db=db,
        internship_id=id,
    )

    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internship listing not found.",
        )

    return AdminInternshipDetailResponse.from_orm_model(listing)


@router.post(
    "/{id}/close",
    response_model=InternshipDetailResponse,
)
def close_admin_internship(
    id: UUID,
    _admin_user: AuthenticatedUser = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Administratively close an internship listing."""
    listing = InternshipRepository.get_by_id_for_update(
        db=db,
        internship_id=id,
    )

    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internship listing not found.",
        )

    try:
        if listing.publication_status != "closed":
            listing = InternshipRepository.close_listing(
                db=db,
                listing=listing,
            )

        db.commit()
        db.refresh(listing)
    except Exception:
        db.rollback()
        raise

    return InternshipDetailResponse.from_orm_model(listing)


@router.post(
    "/{id}/reopen",
    response_model=InternshipDetailResponse,
)
def reopen_admin_internship(
    id: UUID,
    _admin_user: AuthenticatedUser = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """
    Republish a closed listing.

    Employer-owned listings require a currently verified organization.
    """
    snapshot = InternshipRepository.get_by_id(
        db=db,
        internship_id=id,
    )

    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internship listing not found.",
        )

    if snapshot.publication_status != "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only closed internship listings can be reopened.",
        )

    if snapshot.listing_source == "employer":
        organization_id = snapshot.employer_organization_id

        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Employer-owned listing is not bound "
                    "to an organization."
                ),
            )

        organization = EmployerOrganizationRepository.get_by_id_for_update(
            db,
            organization_id,
        )

        if (
            organization is None
            or organization.verification_status != "verified"
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Employer organization must be verified "
                    "before reopening."
                ),
            )

        employer_user_id = snapshot.employer_user_id

        if employer_user_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Employer-owned listing has no "
                    "authoritative employer owner."
                ),
            )

        try:
            require_employer_listing_capacity(
                db,
                user_id=employer_user_id,
                exclude_internship_id=snapshot.id,
            )
        except EmployerListingLimitError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "The employer's current plan has no "
                    "capacity for another published internship."
                ),
            ) from exc

    listing = InternshipRepository.get_by_id_for_update(
        db=db,
        internship_id=id,
    )

    if (
        listing is None
        or listing.publication_status != "closed"
    ):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Internship listing changed before "
                "the reopen action completed."
            ),
        )

    try:
        listing = InternshipRepository.reopen_listing(
            db=db,
            listing=listing,
        )
        db.commit()
        db.refresh(listing)
    except Exception:
        db.rollback()
        raise

    return InternshipDetailResponse.from_orm_model(listing)



@router.post(
    "/{id}/approve",
    response_model=InternshipDetailResponse,
)
def approve_admin_internship(
    id: UUID,
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    """
    Approve an employer-submitted listing after human review.

    Organization verification and active-listing capacity are rechecked under
    the same publication transaction before the listing becomes public.
    """
    snapshot = InternshipRepository.get_by_id(
        db=db,
        internship_id=id,
    )

    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internship listing not found.",
        )

    if snapshot.listing_source != "employer":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only employer-submitted listings use "
                "the review approval workflow."
            ),
        )

    if snapshot.publication_status != "under_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only listings currently under review "
                "can be approved."
            ),
        )

    organization_id = (
        snapshot.employer_organization_id
    )

    if organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Employer-owned listing is not bound "
                "to an organization."
            ),
        )

    organization = (
        EmployerOrganizationRepository
        .get_by_id_for_update(
            db,
            organization_id,
        )
    )

    if (
        organization is None
        or organization.verification_status
        != "verified"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Employer organization must be "
                "verified before publication."
            ),
        )

    employer_user_id = (
        snapshot.employer_user_id
    )

    if employer_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Employer-owned listing has no "
                "authoritative employer owner."
            ),
        )

    try:
        require_employer_listing_capacity(
            db,
            user_id=employer_user_id,
            exclude_internship_id=snapshot.id,
        )
    except EmployerListingLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The employer's current plan has no "
                "capacity for another published internship."
            ),
        ) from exc

    listing = (
        InternshipRepository.get_by_id_for_update(
            db=db,
            internship_id=id,
        )
    )

    if (
        listing is None
        or listing.publication_status
        != "under_review"
    ):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Internship listing changed before "
                "the approval action completed."
            ),
        )

    try:
        listing = (
            InternshipRepository.reopen_listing(
                db=db,
                listing=listing,
            )
        )

        approval_decided_at = datetime.now(
            timezone.utc
        ).isoformat()

        NotificationRepository.create(
            db,
            recipient_user_id=employer_user_id,
            event_type="listing_published",
            entity_type="internship",
            entity_id=listing.id,
            data={
                "internship_id": str(
                    listing.id
                ),
                "publication_status": "published",
            },
            dedupe_key=(
                f"internship:{listing.id}:"
                "published:"
                f"{approval_decided_at}"
            ),
        )

        db.commit()
        db.refresh(listing)

        # Engagement fan-out is asynchronous and intentionally
        # isolated from the authoritative publication transaction.
        # Queue failure must never roll back an approved listing.
        try:
            enqueue_new_opportunity_alert_fanout(
                listing.id
            )
        except Exception:
            logger.exception(
                "New opportunity alert fan-out enqueue failed "
                "for internship %s.",
                listing.id,
            )
    except Exception:
        db.rollback()
        raise

    return InternshipDetailResponse.from_orm_model(
        listing
    )


@router.post(
    "/{id}/request-changes",
    response_model=InternshipDetailResponse,
)
def request_changes_admin_internship(
    id: UUID,
    payload: AdminInternshipChangesRequest,
    _admin_user: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(get_db),
):
    """
    Return an employer-submitted listing to draft state for correction.

    Draft listings remain hidden until the employer edits/resubmits them,
    which moves them back to under_review.
    """
    listing = InternshipRepository.get_by_id_for_update(
        db=db,
        internship_id=id,
    )

    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internship listing not found.",
        )

    if listing.listing_source != "employer":
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only employer-submitted listings can "
                "receive change requests."
            ),
        )

    if listing.publication_status != "under_review":
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only listings currently under review "
                "can receive change requests."
            ),
        )

    try:
        listing.publication_status = "draft"
        listing.is_active = False

        changes_requested_at = datetime.now(
            timezone.utc
        ).isoformat()

        if listing.employer_user_id is not None:
            NotificationRepository.create(
                db,
                recipient_user_id=listing.employer_user_id,
                event_type="listing_changes_requested",
                entity_type="internship",
                entity_id=listing.id,
                data={
                    "internship_id": str(listing.id),
                    "publication_status": "draft",
                    "employer_visible_feedback": (
                        payload.employer_visible_feedback
                    ),
                },
                dedupe_key=(
                    f"internship:{listing.id}:"
                    "changes-requested:"
                    f"{changes_requested_at}"
                ),
            )

        db.commit()
        db.refresh(listing)
    except Exception:
        db.rollback()
        raise

    return InternshipDetailResponse.from_orm_model(
        listing
    )
