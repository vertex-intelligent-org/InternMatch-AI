"""
Protected Student Profile Endpoints
Provides authenticated read, write, and CV upload access to candidate profiles.
"""

import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from app.core.logging import get_logger
from app.core.rate_limit import enforce_rate_limit
from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.repositories.candidate_profile_write import (
    replace_candidate_profile_from_extraction,
)
from app.repositories.matching_data import MatchingDataRepository
from app.repositories.processing_job import ProcessingJobRepository
from app.repositories.student_profile import StudentProfileRepository
from app.services.ai_quota import FEATURE_CV_ANALYSIS
from app.services.ai_quota_integration import (
    acquire_job_ai_quota_lock,
    build_cv_request_fingerprint,
    get_http_idempotent_job_ai_quota,
    is_retryable_released_job_ai_quota,
    release_job_ai_quota_if_present,
    reserve_http_idempotent_job_ai_quota,
    reserve_job_ai_quota,
)
from app.services.avatar_storage import (
    MAX_AVATAR_SIZE_BYTES,
    AvatarStorageValidationError,
    delete_candidate_avatar,
    generate_avatar_signed_url,
    store_candidate_avatar,
)
from app.services.candidate_embedding import (
    generate_and_persist_candidate_embedding,
)
from app.services.cv_enqueue import enqueue_cv_extraction
from app.services.cv_profile_extraction import ExtractedCandidateProfile
from app.services.cv_storage import (
    MAX_CV_SIZE_BYTES,
    CVStorageValidationError,
    delete_candidate_cv,
    store_candidate_cv,
)
from app.services.match_enqueue import enqueue_match_calculation
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

logger = get_logger(__name__)
router = APIRouter()


class StudentProfileCreateUpdate(BaseModel):
    """Request schema for creating or updating candidate profile."""

    full_name: str = Field(..., min_length=1, description="Candidate full name")
    headline: Optional[str] = Field(None, description="Short professional headline")
    cv_storage_path: Optional[str] = Field(None, description="Storage path for CV file")
    preferences: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Job/internship preferences"
    )
    skills: Optional[List[str]] = Field(
        None, description="List of candidate skills"
    )

    @field_validator("skills")
    @classmethod
    def validate_skills_list(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        if len(v) > 50:
            raise ValueError("Candidate profile cannot have more than 50 skills.")
        for item in v:
            if not isinstance(item, str):
                raise ValueError("Each skill must be a string.")
            clean = re.sub(r"\s+", " ", item.strip())
            if not clean:
                raise ValueError("Skill name cannot be empty.")
            if len(clean) > 80:
                raise ValueError(f"Skill name '{clean}' exceeds maximum limit of 80 characters.")
        return v


class EducationResponse(BaseModel):
    """Schema for structured education history entry in profile response."""

    institution: str
    degree: str
    start_year: Optional[int] = None
    end_year: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ExperienceResponse(BaseModel):
    """Schema for structured work experience entry in profile response."""

    company: str
    role: str
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)


class ProjectResponse(BaseModel):
    """Schema for structured project entry in profile response."""

    title: str
    tech_stack: List[str] = Field(default_factory=list)
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class StudentProfileResponse(BaseModel):
    """Authoritative API schema for candidate profile response."""

    id: UUID
    user_id: UUID
    full_name: str
    headline: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    education: List[EducationResponse] = Field(default_factory=list)
    experience: List[ExperienceResponse] = Field(default_factory=list)
    projects: List[ProjectResponse] = Field(default_factory=list)
    preferences: Optional[Dict[str, Any]] = Field(default_factory=dict)
    cv_url: Optional[str] = None
    avatar_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AvatarUploadResponse(BaseModel):
    """Response schema for profile avatar upload."""

    avatar_url: str
    message: str = "Avatar uploaded successfully."


class AvatarDeleteResponse(BaseModel):
    """Response schema for profile avatar deletion."""

    avatar_url: Optional[str] = None
    message: str = "Avatar removed successfully."


class CVProcessingResponse(BaseModel):
    """Response schema for successfully enqueued CV upload."""

    job_id: UUID
    status: Literal["queued"] = "queued"
    message: str = "CV processing enqueued successfully."
    estimated_seconds: int = 60


class CVConfirmReplacementRequest(BaseModel):
    """Request schema for confirming pending CV replacement."""

    job_id: UUID


class CVCancelResponse(BaseModel):
    """Response schema for cancelling an active CV analysis."""

    job_id: UUID
    status: str = "cancelled"
    message: str = "CV analysis cancelled."


class CVConfirmReplacementResponse(BaseModel):
    """Response schema for confirming pending CV replacement."""

    status: str = "completed"
    profile_id: UUID
    message: str = "CV replacement confirmed and profile updated."


def format_error_payload(code: str, message: str) -> Dict[str, Any]:
    """Format standard machine-readable error payload."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }


@router.get("", response_model=StudentProfileResponse)
def get_my_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve the authenticated user's own structured student profile.
    Requires valid Supabase Bearer JWT authentication token.
    Identity is strictly derived from the validated JWT subject UUID.
    Loads structured skills, education, experience, and projects deterministically.
    """
    profile_data = MatchingDataRepository.get_structured_profile_by_user_id(
        db,
        user_id=current_user.user_id,
    )

    if profile_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=format_error_payload(
                "NOT_FOUND",
                "Student profile not found for authenticated user.",
            ),
        )

    avatar_url = generate_avatar_signed_url(
        user_id=current_user.user_id,
        storage_path=profile_data["avatar_storage_path"],
    )

    return StudentProfileResponse(
        id=profile_data["id"],
        user_id=profile_data["user_id"],
        full_name=profile_data["full_name"],
        headline=profile_data["headline"],
        skills=profile_data["skills"],
        education=[
            EducationResponse.model_validate(entry)
            for entry in profile_data["education"]
        ],
        experience=[
            ExperienceResponse.model_validate(entry)
            for entry in profile_data["experience"]
        ],
        projects=[
            ProjectResponse.model_validate(entry)
            for entry in profile_data["projects"]
        ],
        preferences=profile_data["preferences"] or {},
        avatar_url=avatar_url,
    )


@router.put("", response_model=StudentProfileResponse)
def upsert_my_profile(
    payload: StudentProfileCreateUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create or update the authenticated user's own student profile.
    Requires valid Supabase Bearer JWT authentication token.
    Ownership is strictly governed by the authenticated JWT subject UUID.
    Transaction commit boundary is owned by this endpoint handler.
    """
    profile = StudentProfileRepository.upsert_by_user_id(
        db=db,
        user_id=current_user.user_id,
        full_name=payload.full_name,
        headline=payload.headline,
        cv_storage_path=payload.cv_storage_path,
        preferences=payload.preferences,
    )

    if payload.skills is not None:
        skills_changed = StudentProfileRepository.sync_student_skills(
            db=db,
            student_id=profile.id,
            skills=payload.skills,
        )
        if skills_changed:
            StudentProfileRepository.invalidate_summary_embedding(db, profile)

    try:
        db.commit()
        db.refresh(profile)

        skills = MatchingDataRepository.get_skill_names_for_student(db, student_id=profile.id)
        education = MatchingDataRepository.get_education_for_student(db, student_id=profile.id)
        experience = MatchingDataRepository.get_experience_for_student(db, student_id=profile.id)
        projects = MatchingDataRepository.get_projects_for_student(db, student_id=profile.id)

        avatar_url = generate_avatar_signed_url(
            user_id=current_user.user_id,
            storage_path=profile.avatar_storage_path,
        )

        return StudentProfileResponse(
            id=profile.id,
            user_id=profile.user_id,
            full_name=profile.full_name,
            headline=profile.headline,
            skills=skills,
            education=[EducationResponse.model_validate(e) for e in education],
            experience=[ExperienceResponse.model_validate(e) for e in experience],
            projects=[ProjectResponse.model_validate(p) for p in projects],
            preferences=profile.preferences or {},
            avatar_url=avatar_url,
        )
    except Exception:
        db.rollback()
        raise


@router.post("/cv", response_model=CVProcessingResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_candidate_cv(
    file: UploadFile = File(...),
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
    Upload candidate CV document (PDF/DOCX) to initiate background AI profile extraction.
    Validates file format and size <= 10 MiB, uploads securely to private Supabase Storage,
    persists durable ProcessingJob, and enqueues background worker task.
    """
    # 1. Enforce rate limiting before reading/storing content
    enforce_rate_limit(user_id=current_user.user_id, scope="cv_upload")

    # 2. Read content up to max size + 1 to guard against oversized payloads
    max_read_bytes = MAX_CV_SIZE_BYTES + 1
    content = await file.read(max_read_bytes)

    if len(content) > MAX_CV_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=format_error_payload(
                "PAYLOAD_TOO_LARGE",
                "CV file exceeds maximum limit of 10 MB.",
            ),
        )

    cv_request_fingerprint = build_cv_request_fingerprint(
        content=content,
        filename=file.filename or "",
        content_type=file.content_type or "",
    )

    # Fast-path duplicate retries before storage I/O.
    if idempotency_key is not None:
        existing_request = get_http_idempotent_job_ai_quota(
            db,
            user_id=current_user.user_id,
            feature_key=FEATURE_CV_ANALYSIS,
            raw_idempotency_key=idempotency_key,
            request_fingerprint=cv_request_fingerprint,
        )

        if (
            existing_request is not None
            and not is_retryable_released_job_ai_quota(
                existing_request["operation"]
            )
        ):
            existing_job = existing_request["job"]
            db.rollback()

            return CVProcessingResponse(
                job_id=existing_job.id,
                status="queued",
                message="CV processing request already exists.",
                estimated_seconds=60,
            )

        # Do not keep a read transaction open during external storage I/O.
        db.rollback()

    # 3. Validate MIME/extension/signature and upload to private Supabase Storage
    try:
        stored_cv = store_candidate_cv(
            user_id=current_user.user_id,
            filename=file.filename or "",
            content_type=file.content_type or "",
            content=content,
        )
    except CVStorageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=format_error_payload("BAD_REQUEST", str(exc)),
        )

    # 4. Create/reuse durable ProcessingJob and commit BEFORE enqueue.
    try:
        if idempotency_key is not None:
            # Re-check under the same feature advisory lock. This closes the
            # race where two identical HTTP requests both missed the fast path.
            acquire_job_ai_quota_lock(
                db,
                user_id=current_user.user_id,
                feature_key=FEATURE_CV_ANALYSIS,
            )

            existing_request = get_http_idempotent_job_ai_quota(
                db,
                user_id=current_user.user_id,
                feature_key=FEATURE_CV_ANALYSIS,
                raw_idempotency_key=idempotency_key,
                request_fingerprint=cv_request_fingerprint,
            )

            if existing_request is not None:
                existing_operation = existing_request["operation"]
                existing_job = existing_request["job"]

                if not is_retryable_released_job_ai_quota(
                    existing_operation
                ):
                    db.rollback()

                    try:
                        delete_candidate_cv(
                            user_id=current_user.user_id,
                            storage_path=stored_cv.storage_path,
                        )
                    except Exception:
                        pass

                    return CVProcessingResponse(
                        job_id=existing_job.id,
                        status="queued",
                        message="CV processing request already exists.",
                        estimated_seconds=60,
                    )

                job = existing_job
                job.status = "queued"
                job.progress_percent = 0
                job.result = None
                job.error = None

                reserve_http_idempotent_job_ai_quota(
                    db,
                    user_id=current_user.user_id,
                    feature_key=FEATURE_CV_ANALYSIS,
                    job_id=job.id,
                    raw_idempotency_key=idempotency_key,
                    request_fingerprint=cv_request_fingerprint,
                )
            else:
                job = ProcessingJobRepository.create(
                    db=db,
                    user_id=current_user.user_id,
                    job_type="cv_extraction",
                )

                reserve_http_idempotent_job_ai_quota(
                    db,
                    user_id=current_user.user_id,
                    feature_key=FEATURE_CV_ANALYSIS,
                    job_id=job.id,
                    raw_idempotency_key=idempotency_key,
                    request_fingerprint=cv_request_fingerprint,
                )
        else:
            job = ProcessingJobRepository.create(
                db=db,
                user_id=current_user.user_id,
                job_type="cv_extraction",
            )

            reserve_job_ai_quota(
                db,
                user_id=current_user.user_id,
                feature_key=FEATURE_CV_ANALYSIS,
                job_id=job.id,
            )

        db.commit()
        db.refresh(job)

    except Exception:
        db.rollback()

        # Best-effort cleanup of uploaded object if DB persistence fails.
        try:
            delete_candidate_cv(
                user_id=current_user.user_id,
                storage_path=stored_cv.storage_path,
            )
        except Exception:
            pass

        raise

    # 4. Enqueue background extraction task to RQ
    try:
        enqueue_cv_extraction(
            job_id=job.id,
            user_id=current_user.user_id,
            storage_path=stored_cv.storage_path,
        )
    except Exception:
        # If durable ProcessingJob commit succeeded but RQ enqueue failed:
        # mark ProcessingJob failed, commit, and return HTTP 503
        try:
            job.status = "failed"
            job.progress_percent = 100
            job.result = None
            job.error = "Failed to enqueue CV extraction job."
            release_job_ai_quota_if_present(
                db,
                feature_key=FEATURE_CV_ANALYSIS,
                job_id=job.id,
                reason="enqueue_failure",
            )
            db.commit()
        except Exception:
            db.rollback()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=format_error_payload(
                "SERVICE_UNAVAILABLE",
                "Failed to enqueue CV extraction job. Please try again later.",
            ),
        )

    # 5. Return HTTP 202 Accepted with exact API contract
    return CVProcessingResponse(
        job_id=job.id,
        status="queued",
        message="CV processing enqueued successfully.",
        estimated_seconds=60,
    )


@router.post(
    "/cv/{job_id}/cancel",
    response_model=CVCancelResponse,
    status_code=status.HTTP_200_OK,
)
def cancel_cv_analysis(
    job_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CVCancelResponse:
    """
    Cancel an active user-owned CV analysis.

    The cancellation marker is persisted before returning. A running worker
    observes that marker at safe checkpoints and before any profile mutation.
    """
    job = ProcessingJobRepository.get_by_id_and_user_id_for_update(
        db=db,
        job_id=job_id,
        user_id=current_user.user_id,
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=format_error_payload(
                "NOT_FOUND",
                "CV analysis job was not found.",
            ),
        )

    if job.job_type != "cv_extraction":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=format_error_payload(
                "INVALID_JOB_TYPE",
                "This job is not a CV analysis.",
            ),
        )

    job_result = job.result if isinstance(job.result, dict) else {}

    # Idempotent replay after a successful cancellation request.
    if job_result.get("cancel_requested") is True:
        return CVCancelResponse(job_id=job.id)

    # Once analysis has reached a terminal state, cancellation must not claim
    # that already-committed work was stopped.
    if job.status in {"completed", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=format_error_payload(
                "CV_ANALYSIS_NOT_ACTIVE",
                "This CV analysis is no longer active.",
            ),
        )

    updated_result = dict(job_result)
    updated_result["cancel_requested"] = True
    updated_result["cancelled"] = True

    # ProcessingJob currently supports queued/processing/completed/failed only.
    # Store cancellation semantically in result while using failed as the
    # existing terminal database state.
    job.status = "failed"
    job.progress_percent = 100
    job.result = updated_result
    job.error = "CV analysis cancelled by user."

    release_job_ai_quota_if_present(
        db,
        feature_key=FEATURE_CV_ANALYSIS,
        job_id=job.id,
        reason="user_cancelled",
    )
    db.commit()

    return CVCancelResponse(job_id=job.id)


@router.post(
    "/cv/confirm",
    response_model=CVConfirmReplacementResponse,
    status_code=status.HTTP_200_OK,
)
def confirm_cv_replacement(
    payload: CVConfirmReplacementRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Confirm and apply a pending CV profile replacement when identity mismatch warning was flagged.
    Guarantees idempotency and safe transactional profile update.
    """
    enforce_rate_limit(user_id=current_user.user_id, scope="cv_confirm")

    # Serialize confirmations for the same user-owned CV job.
    # The row lock remains held through replacement, embedding, and the
    # confirmed=True commit below, so concurrent replays observe final state.
    job = ProcessingJobRepository.get_by_id_and_user_id_for_update(
        db=db,
        job_id=payload.job_id,
        user_id=current_user.user_id,
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=format_error_payload("NOT_FOUND", "Processing job not found."),
        )

    if job.job_type != "cv_extraction":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=format_error_payload("INVALID_JOB_TYPE", "Job is not a CV extraction job."),
        )

    job_result = job.result if isinstance(job.result, dict) else {}

    # Idempotent replay handling: if already confirmed, return success without repeating writes
    if job_result.get("confirmed") is True and job_result.get("profile_id"):
        try:
            profile_id = UUID(str(job_result["profile_id"]))
            return CVConfirmReplacementResponse(
                status="completed",
                profile_id=profile_id,
                message="CV replacement was already confirmed.",
            )
        except Exception:
            pass

    if job_result.get("requires_confirmation") is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=format_error_payload(
                "NO_CONFIRMATION_PENDING",
                "This CV extraction job does not require confirmation.",
            ),
        )

    extracted_data = job_result.get("extracted_profile")
    cv_storage_path = job_result.get("cv_storage_path")

    if not extracted_data or not cv_storage_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=format_error_payload(
                "MISSING_PENDING_PAYLOAD",
                "Job result is missing pending extracted candidate profile data.",
            ),
        )

    try:
        extracted_profile = ExtractedCandidateProfile.model_validate(extracted_data)
    except Exception as exc:
        logger.warning(
            "Pending CV replacement payload validation failed: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=format_error_payload(
                "INVALID_PAYLOAD",
                "Pending CV replacement data is invalid. Please upload the CV again.",
            ),
        ) from None

    try:
        profile = replace_candidate_profile_from_extraction(
            db=db,
            user_id=current_user.user_id,
            cv_storage_path=cv_storage_path,
            extracted=extracted_profile,
        )

        generate_and_persist_candidate_embedding(
            db=db,
            user_id=current_user.user_id,
        )

        updated_result = dict(job_result)
        updated_result["requires_confirmation"] = False
        updated_result["confirmed"] = True
        updated_result["profile_id"] = str(profile.id)
        updated_result["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        job.result = updated_result

        db.commit()
    except Exception:
        db.rollback()
        raise

    # Trigger initial match calculation after successful confirmed commit
    try:
        match_job = ProcessingJobRepository.create(
            db=db,
            user_id=current_user.user_id,
            job_type="match_calculation",
        )
        db.commit()

        try:
            enqueue_match_calculation(
                job_id=match_job.id,
                user_id=current_user.user_id,
                candidate_limit=50,
            )
        except Exception as queue_exc:
            logger.warning(
                "Match calculation enqueue failed after confirmed CV replacement: %s",
                type(queue_exc).__name__,
            )

            # The match job was already committed before enqueue. Do not leave
            # a durable queued job behind when RQ rejected the enqueue.
            try:
                db.rollback()
                failed_match_job = ProcessingJobRepository.get_by_id(
                    db=db,
                    job_id=match_job.id,
                )
                if failed_match_job:
                    failed_match_job.status = "failed"
                    failed_match_job.progress_percent = 100
                    failed_match_job.result = None
                    failed_match_job.error = (
                        "Failed to enqueue automatic match calculation."
                    )
                    db.commit()
            except Exception as state_exc:
                db.rollback()
                logger.warning(
                    "Failed to persist match enqueue failure state: %s",
                    type(state_exc).__name__,
                )
    except Exception as match_err:
        logger.warning(
            "Match job persistence failed after confirmed CV replacement: %s",
            type(match_err).__name__,
        )

    return CVConfirmReplacementResponse(
        status="completed",
        profile_id=profile.id,
        message="CV replacement confirmed and profile updated.",
    )


@router.post("/avatar", response_model=AvatarUploadResponse, status_code=status.HTTP_200_OK)
async def upload_profile_avatar(
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload candidate profile avatar image (JPEG, PNG, WebP <= 5 MB).
    Uploads new object to private Supabase Storage, updates avatar_storage_path on StudentProfile,
    commits transaction, generates signed avatar_url, and best-effort removes previous object.
    """
    # 1. Enforce rate limiting before reading content
    enforce_rate_limit(user_id=current_user.user_id, scope="avatar_upload")

    # 2. Read content up to max size + 1 to guard against oversized payloads
    max_read_bytes = MAX_AVATAR_SIZE_BYTES + 1
    content = await file.read(max_read_bytes)

    if len(content) > MAX_AVATAR_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=format_error_payload(
                "PAYLOAD_TOO_LARGE",
                "Avatar file exceeds maximum limit of 5 MB.",
            ),
        )

    # 3. Validate profile exists for authenticated user
    profile = StudentProfileRepository.get_by_user_id(db, user_id=current_user.user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=format_error_payload(
                "NOT_FOUND", "Student profile not found for authenticated user."
            ),
        )

    old_storage_path = profile.avatar_storage_path

    # 4. Validate image binary and upload new object to private Supabase Storage
    try:
        stored_avatar = store_candidate_avatar(
            user_id=current_user.user_id,
            content_type=file.content_type,
            content=content,
        )
    except AvatarStorageValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=format_error_payload("BAD_REQUEST", str(exc)),
        )

    # 5. Persist new avatar_storage_path in DB
    try:
        StudentProfileRepository.update_avatar_storage_path(
            db=db,
            user_id=current_user.user_id,
            avatar_storage_path=stored_avatar.storage_path,
        )
        db.commit()
    except Exception:
        db.rollback()
        # Best-effort cleanup of newly uploaded object if DB update fails
        try:
            delete_candidate_avatar(
                user_id=current_user.user_id,
                storage_path=stored_avatar.storage_path,
            )
        except Exception:
            pass
        raise

    # 6. Generate signed URL for immediate presentation
    signed_url = generate_avatar_signed_url(
        user_id=current_user.user_id,
        storage_path=stored_avatar.storage_path,
    )

    # 7. Best-effort delete old avatar object after successful persistence
    if old_storage_path and old_storage_path != stored_avatar.storage_path:
        try:
            delete_candidate_avatar(
                user_id=current_user.user_id,
                storage_path=old_storage_path,
            )
        except Exception:
            pass

    return AvatarUploadResponse(
        avatar_url=signed_url or "",
        message="Avatar uploaded successfully.",
    )


@router.delete("/avatar", response_model=AvatarDeleteResponse, status_code=status.HTTP_200_OK)
def delete_profile_avatar(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete candidate profile avatar image.
    Safely clears avatar_storage_path on StudentProfile, commits transaction,
    and removes object from Supabase Storage.
    """
    profile = StudentProfileRepository.get_by_user_id(db, user_id=current_user.user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=format_error_payload(
                "NOT_FOUND", "Student profile not found for authenticated user."
            ),
        )

    old_storage_path = profile.avatar_storage_path

    if not old_storage_path:
        return AvatarDeleteResponse(
            avatar_url=None,
            message="No profile avatar was set.",
        )

    try:
        StudentProfileRepository.clear_avatar_storage_path(
            db=db,
            user_id=current_user.user_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Delete old storage object after DB commit
    try:
        delete_candidate_avatar(
            user_id=current_user.user_id,
            storage_path=old_storage_path,
        )
    except Exception:
        pass

    return AvatarDeleteResponse(
        avatar_url=None,
        message="Avatar removed successfully.",
    )
