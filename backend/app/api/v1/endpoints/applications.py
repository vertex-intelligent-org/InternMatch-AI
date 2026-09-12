"""
Candidate Application Operations Endpoints
Provides endpoints for personalized cover letter generation, application
listing, and tracker status/notes updates.
"""

from typing import Optional
from uuid import UUID

from app.core.rate_limit import enforce_rate_limit
from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.repositories.application import ApplicationRepository
from app.repositories.match import MatchRepository
from app.repositories.processing_job import ProcessingJobRepository
from app.schemas.application import (
    ApplicationDetailResponse,
    ApplicationGenerateAcceptedResponse,
    ApplicationGenerateRequest,
    ApplicationListResponse,
    ApplicationStatusUpdateRequest,
    ApplicationSubmitRequest,
    ApplicationTrackerResponse,
)
from app.schemas.job import AIJobAcceptedResponse
from app.services.ai_quota import FEATURE_APPLICATION_SUPPORT
from app.services.ai_quota_integration import (
    acquire_job_ai_quota_lock,
    build_ai_request_fingerprint,
    get_http_idempotent_job_ai_quota,
    is_retryable_released_job_ai_quota,
    release_job_ai_quota_if_present,
    reserve_http_idempotent_job_ai_quota,
    reserve_job_ai_quota,
)
from app.services.application_enqueue import enqueue_application_generation
from app.services.interview_prep_enqueue import enqueue_interview_prep_generation
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("", response_model=ApplicationListResponse)
def get_my_applications(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve candidate internship applications for the Application Tracker.
    Requires valid Supabase Bearer JWT authentication token.
    Identity is strictly derived from the validated JWT subject UUID.
    Returns applications ordered by updated_at DESC, created_at DESC.
    """
    records = ApplicationRepository.list_for_user(
        db=db, user_id=current_user.user_id
    )

    items = [
        ApplicationTrackerResponse.from_orm_tuple(
            application=app, internship=internship
        )
        for app, internship in records
    ]

    return ApplicationListResponse(applications=items)


@router.get("/{id}", response_model=ApplicationDetailResponse)
def get_application_detail(
    id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve candidate application details including chronological status timeline.
    Requires valid Supabase Bearer JWT authentication token.
    Identity is strictly derived from the validated JWT subject UUID.
    Returns 404 if application is not found or owned by another candidate.
    """
    record = ApplicationRepository.get_with_internship_for_user(
        db=db,
        application_id=id,
        user_id=current_user.user_id,
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    application, internship = record
    events = ApplicationRepository.list_events_for_application(
        db=db,
        application_id=id,
    )

    return ApplicationDetailResponse.from_orm_data(
        application=application,
        internship=internship,
        events=events,
    )


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def discard_saved_application_draft(
    id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Permanently discard an unsubmitted candidate application draft.

    Only applications currently in status 'saved' may be deleted.
    Submitted application history is never deleted through this endpoint.
    Ownership is enforced through the authenticated Supabase JWT subject.
    """
    record = ApplicationRepository.get_with_internship_for_user(
        db=db,
        application_id=id,
        user_id=current_user.user_id,
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    application, _internship = record

    if application.status != "saved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only saved application drafts can be discarded "
                f"(current status: '{application.status}')."
            ),
        )

    try:
        ApplicationRepository.delete(
            db=db,
            application=application,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return None


@router.post(
    "/generate",
    response_model=ApplicationGenerateAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_application(
    payload: ApplicationGenerateRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=200,
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Enqueue asynchronous personalized application cover-letter generation job.
    Requires valid Supabase Bearer JWT authentication token.
    Identity is strictly derived from the validated JWT subject UUID.
    Verifies match ownership prior to enqueuing job. Returns 404 if match is
    not found or owned by another user.
    """
    enforce_rate_limit(
        user_id=current_user.user_id, scope="application_generate"
    )

    # Verify match exists and is owned by authenticated user
    match_record = MatchRepository.get_match_with_details_for_user(
        db=db,
        match_id=payload.match_id,
        user_id=current_user.user_id,
    )
    if not match_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match not found.",
        )

    application_request_fingerprint = build_ai_request_fingerprint(
        {
            "match_id": str(payload.match_id),
            "tone": payload.tone,
            "content_locale": payload.content_locale,
        }
    )

    try:
        if idempotency_key is not None:
            # Ownership has already been verified. Serialize the idempotency
            # lookup and job creation with the same per-user feature lock.
            acquire_job_ai_quota_lock(
                db,
                user_id=current_user.user_id,
                feature_key=FEATURE_APPLICATION_SUPPORT,
            )

            existing_request = get_http_idempotent_job_ai_quota(
                db,
                user_id=current_user.user_id,
                feature_key=FEATURE_APPLICATION_SUPPORT,
                raw_idempotency_key=idempotency_key,
                request_fingerprint=application_request_fingerprint,
            )

            if existing_request is not None:
                existing_operation = existing_request["operation"]
                existing_job = existing_request["job"]

                if not is_retryable_released_job_ai_quota(
                    existing_operation
                ):
                    db.rollback()

                    return ApplicationGenerateAcceptedResponse(
                        job_id=existing_job.id,
                        status="queued",
                        message=(
                            "Personalized application generation "
                            "request already exists."
                        ),
                    )

                processing_job = existing_job
                processing_job.status = "queued"
                processing_job.progress_percent = 0
                processing_job.result = None
                processing_job.error = None

                reserve_http_idempotent_job_ai_quota(
                    db,
                    user_id=current_user.user_id,
                    feature_key=FEATURE_APPLICATION_SUPPORT,
                    job_id=processing_job.id,
                    raw_idempotency_key=idempotency_key,
                    request_fingerprint=application_request_fingerprint,
                )
            else:
                processing_job = ProcessingJobRepository.create(
                    db=db,
                    user_id=current_user.user_id,
                    job_type="application_generation",
                )

                reserve_http_idempotent_job_ai_quota(
                    db,
                    user_id=current_user.user_id,
                    feature_key=FEATURE_APPLICATION_SUPPORT,
                    job_id=processing_job.id,
                    raw_idempotency_key=idempotency_key,
                    request_fingerprint=application_request_fingerprint,
                )
        else:
            processing_job = ProcessingJobRepository.create(
                db=db,
                user_id=current_user.user_id,
                job_type="application_generation",
            )

            reserve_job_ai_quota(
                db,
                user_id=current_user.user_id,
                feature_key=FEATURE_APPLICATION_SUPPORT,
                job_id=processing_job.id,
            )

        db.commit()

    except Exception:
        db.rollback()
        raise

    try:
        enqueue_application_generation(
            job_id=processing_job.id,
            user_id=current_user.user_id,
            match_id=payload.match_id,
            tone=payload.tone,
            content_locale=payload.content_locale,
        )
    except Exception:
        safe_error = "Failed to enqueue application generation job."
        try:
            processing_job.status = "failed"
            processing_job.progress_percent = 100
            processing_job.result = None
            processing_job.error = safe_error
            release_job_ai_quota_if_present(
                db,
                feature_key=FEATURE_APPLICATION_SUPPORT,
                job_id=processing_job.id,
                reason="enqueue_failure",
            )
            db.commit()
        except Exception:
            db.rollback()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue application generation job.",
        )

    return ApplicationGenerateAcceptedResponse(
        job_id=processing_job.id,
        status="queued",
        message="Personalized application generation enqueued.",
    )


@router.post("/{id}/submit", response_model=ApplicationTrackerResponse)
def submit_application(
    id: UUID,
    payload: Optional[ApplicationSubmitRequest] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Candidate explicitly submits a saved application draft to the employer.
    Transitions status from 'saved' -> 'applied'.
    Sets applied_date and appends an authoritative ApplicationStatusEvent.
    If internship is closed, rejects new submissions with 400.
    """
    record = ApplicationRepository.get_with_internship_for_user(
        db=db,
        application_id=id,
        user_id=current_user.user_id,
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    application, internship = record

    if application.status != "saved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Application is already submitted (current status: '{application.status}')."
            ),
        )

    if application.internship_id and not application.internship.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This internship opportunity has been closed "
                "and is no longer accepting new submissions."
            ),
        )

    cover_letter = payload.cover_letter if payload else None
    notes = payload.notes if payload else None

    if cover_letter is not None:
        application.generated_cover_letter = cover_letter

    try:
        updated_app = ApplicationRepository.update_status(
            db=db,
            application=application,
            status="applied",
            notes=notes,
            notes_provided=notes is not None,
        )
        db.commit()
        db.refresh(updated_app)
    except Exception:
        db.rollback()
        raise

    return ApplicationTrackerResponse.from_orm_tuple(
        application=updated_app,
        internship=internship,
    )


@router.patch("/{id}/status", response_model=ApplicationTrackerResponse)
def update_application_status(
    id: UUID,
    payload: ApplicationStatusUpdateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update candidate application notes or explicitly submit (saved -> applied).
    Candidates cannot self-set status to interviewing, accepted, or rejected.
    """
    record = ApplicationRepository.get_with_internship_for_user(
        db=db,
        application_id=id,
        user_id=current_user.user_id,
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    application, internship = record
    target_status = payload.status
    notes_provided = "notes" in payload.model_fields_set

    # Candidate authority constraint: cannot self-transition to employer-controlled statuses
    if target_status in ("interviewing", "accepted", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Candidates cannot manually set application status to interviewing, "
                "accepted, or rejected. Status transitions are managed by the employer."
            ),
        )

    if target_status == "saved" and application.status != "saved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revert a submitted application back to saved draft.",
        )

    if target_status == "applied" and application.status == "saved":
        if internship and not getattr(internship, "is_active", True):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "This internship opportunity has been closed "
                    "and is no longer accepting submissions."
                ),
            )

    try:
        updated_app = ApplicationRepository.update_status(
            db=db,
            application=application,
            status=target_status,
            notes=payload.notes,
            notes_provided=notes_provided,
        )
        db.commit()
        db.refresh(updated_app)
    except Exception:
        db.rollback()
        raise

    return ApplicationTrackerResponse.from_orm_tuple(
        application=updated_app,
        internship=internship,
    )


@router.post(
    "/{id}/interview-prep",
    response_model=AIJobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_interview_prep(
    id: UUID,
    content_locale: str = "en",
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Enqueue cancellable interview preparation for a scheduled interview.

    Ownership and application/interview eligibility remain synchronous.
    Fresh AI quota remains worker-owned so cached responses consume no credit.
    """
    enforce_rate_limit(
        user_id=current_user.user_id,
        scope="interview_prep",
    )

    normalized_locale = (
        content_locale or "en"
    ).strip().lower()

    if normalized_locale not in {"en", "tr", "ar"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="content_locale must be one of: en, tr, ar.",
        )

    record = ApplicationRepository.get_with_internship_for_user(
        db=db,
        application_id=id,
        user_id=current_user.user_id,
    )

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )

    application, internship = record

    if internship is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Interview preparation requires an "
                "internship-linked application."
            ),
        )

    if application.status != "interviewing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Interview preparation is available only "
                "during the interviewing stage."
            ),
        )

    if application.interview_scheduled_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Interview preparation requires a scheduled interview."
            ),
        )

    try:
        processing_job = ProcessingJobRepository.create(
            db=db,
            user_id=current_user.user_id,
            job_type="interview_prep",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    try:
        enqueue_interview_prep_generation(
            job_id=processing_job.id,
            user_id=current_user.user_id,
            application_id=id,
            content_locale=normalized_locale,
        )
    except Exception:
        db.rollback()

        try:
            failed_job = (
                ProcessingJobRepository
                .get_by_id_and_user_id_for_update(
                    db=db,
                    job_id=processing_job.id,
                    user_id=current_user.user_id,
                )
            )

            if failed_job is not None:
                failed_job.status = "failed"
                failed_job.progress_percent = 100
                failed_job.result = None
                failed_job.error = (
                    "Failed to enqueue interview preparation."
                )

            db.commit()
        except Exception:
            db.rollback()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue interview preparation.",
        ) from None

    return AIJobAcceptedResponse(
        job_id=processing_job.id,
        status="queued",
        message="Interview preparation generation enqueued.",
    )
