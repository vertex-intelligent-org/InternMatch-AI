"""
RQ CV Extraction Task
Provides background execution boundary for candidate CV document download,
fast-path/multimodal parsing, structured LLM extraction, candidate identity evaluation,
profile persistence, and embedding generation.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Union
from uuid import UUID

from app.db.models import ProcessingJob
from app.db.session import SessionLocal
from app.repositories.candidate_profile_write import (
    replace_candidate_profile_from_extraction,
)
from app.repositories.processing_job import ProcessingJobRepository
from app.repositories.student_profile import StudentProfileRepository
from app.services.ai_quota import FEATURE_CV_ANALYSIS
from app.services.ai_quota_integration import (
    ensure_job_ai_quota_reserved_if_present,
    release_job_ai_quota_if_present,
    settle_job_ai_quota_if_present,
)
from app.services.ai_telemetry import (
    activate_ai_telemetry_context,
    reset_ai_telemetry_context,
)
from app.services.candidate_embedding import (
    generate_and_persist_candidate_embedding,
)
from app.services.candidate_identity import (
    IdentityVerdict,
    evaluate_candidate_identity,
)
from app.services.cv_parser import CVParsingError, extract_cv_text
from app.services.cv_profile_extraction import (
    ExtractedCandidateProfile,
    extract_structured_candidate_profile,
    extract_structured_candidate_profile_multimodal,
)
from app.services.cv_storage import download_candidate_cv
from app.services.cv_validation import (
    InvalidCVDocumentError,
    validate_cv_document,
    validate_cv_document_multimodal,
)
from app.services.match_enqueue import enqueue_match_calculation
from sqlalchemy import update


def _normalize_uuid(val: Union[UUID, str], param_name: str) -> UUID:
    """Normalize UUID object or string to UUID instance. Raises ValueError for invalid format."""
    if isinstance(val, UUID):
        return val
    if isinstance(val, str):
        try:
            return UUID(val)
        except (ValueError, AttributeError, TypeError):
            raise ValueError(f"Invalid UUID string format for {param_name}: '{val}'")
    raise ValueError(
        f"Invalid UUID type for {param_name}: expected UUID or str, got {type(val).__name__}"
    )


class CVExtractionCancelled(Exception):
    """Internal control-flow signal for a user-cancelled CV extraction."""


def _job_cancel_requested(job: Any) -> bool:
    result = job.result if isinstance(job.result, dict) else {}
    return result.get("cancel_requested") is True


def _raise_if_cancel_requested(db: Any, job: Any) -> None:
    """Refresh the tracked job before continuing past a cancellation boundary."""
    db.refresh(job)
    if _job_cancel_requested(job):
        raise CVExtractionCancelled()


def _lock_active_cv_job(
    db: Any,
    job_id: UUID,
    user_id: UUID,
) -> Any:
    """
    Lock the target ProcessingJob immediately before a state commit or
    destructive profile mutation and re-read its latest cancellation state.
    """
    locked_job = ProcessingJobRepository.get_by_id_and_user_id_for_update(
        db=db,
        job_id=job_id,
        user_id=user_id,
    )

    if locked_job is None:
        raise ValueError(f"ProcessingJob with id '{job_id}' not found.")

    # The job may already exist in this Session's identity map from the initial
    # lookup. Refresh after acquiring the database row lock so cancellation
    # committed by a competing transaction cannot remain hidden behind stale
    # ORM attributes.
    db.refresh(locked_job)

    if _job_cancel_requested(locked_job):
        raise CVExtractionCancelled()

    return locked_job


def _publish_progress(job_id: UUID, progress_percent: int) -> None:
    """Persist a best-effort progress checkpoint without reopening terminal jobs."""
    progress_db = SessionLocal()
    try:
        if progress_percent < 0 or progress_percent > 100:
            progress_db.rollback()
            return

        statement = (
            update(ProcessingJob)
            .where(
                ProcessingJob.id == job_id,
                ProcessingJob.status.in_(("queued", "processing")),
            )
            .values(
                status="processing",
                progress_percent=progress_percent,
                updated_at=datetime.now(timezone.utc),
            )
            .execution_options(synchronize_session=False)
        )

        result = progress_db.execute(statement)
        if result.rowcount == 0:
            progress_db.rollback()
            return

        progress_db.commit()
    except Exception:
        progress_db.rollback()
    finally:
        progress_db.close()


def run_cv_extraction(
    job_id: Union[UUID, str],
    user_id: Union[UUID, str],
    storage_path: str,
    content_locale: str = "en",
) -> Dict[str, Any]:
    """
    RQ Task execution boundary for candidate CV extraction pipeline.
    Validates job ownership and job_type, executes download -> parse -> LLM -> DB -> embedding,
    and manages transaction lifecycle atomically.
    """
    norm_job_id = _normalize_uuid(job_id, "job_id")
    norm_user_id = _normalize_uuid(user_id, "user_id")

    clean_path = storage_path.strip() if isinstance(storage_path, str) else ""
    if not clean_path:
        raise ValueError("storage_path cannot be empty")

    db = SessionLocal()
    job_validated = False
    telemetry_token = None

    try:
        job = ProcessingJobRepository.get_by_id(db, norm_job_id)
        if job is None:
            raise ValueError(f"ProcessingJob with id '{norm_job_id}' not found.")

        if job.user_id != norm_user_id:
            raise ValueError(
                f"Job ownership mismatch: ProcessingJob {norm_job_id} "
                f"belongs to user {job.user_id}, "
                f"not user {norm_user_id}."
            )

        if job.job_type != "cv_extraction":
            raise ValueError(
                f"ProcessingJob type mismatch: expected 'cv_extraction', got '{job.job_type}'."
            )

        # Precondition checks passed for target job
        job_validated = True

        # A completed durable job must never invoke CV AI extraction again.
        completed_result = (
            job.result
            if isinstance(job.result, dict)
            else {}
        )
        if job.status == "completed":
            if completed_result.get("requires_confirmation") is True:
                return {
                    "job_id": str(norm_job_id),
                    "status": "completed",
                    "requires_confirmation": True,
                }

            if completed_result.get("profile_id"):
                return {
                    "job_id": str(norm_job_id),
                    "status": "completed",
                    "profile_id": str(
                        completed_result["profile_id"]
                    ),
                }

        # Check cancellation before a released retry can reserve capacity.
        _raise_if_cancel_requested(db, job)

        quota_state = ensure_job_ai_quota_reserved_if_present(
            db,
            user_id=norm_user_id,
            feature_key=FEATURE_CV_ANALYSIS,
            job_id=norm_job_id,
        )

        telemetry_token = activate_ai_telemetry_context(
            user_id=norm_user_id,
            processing_job_id=norm_job_id,
            quota_operation_id=(
                quota_state["operation"].id
                if quota_state is not None
                else None
            ),
        )

        if (
            quota_state is not None
            and quota_state.get("outcome") == "re_reserved"
        ):
            db.commit()

        # Publish the first visible processing checkpoint separately.
        _publish_progress(norm_job_id, 10)

        # Step 1: Download private CV object from storage
        cv_bytes = download_candidate_cv(
            user_id=norm_user_id,
            storage_path=clean_path,
        )
        _raise_if_cancel_requested(db, job)
        _publish_progress(norm_job_id, 20)

        ext = clean_path.rsplit(".", 1)[-1].lower() if "." in clean_path else ""

        extracted_profile: ExtractedCandidateProfile
        used_fast_path = False

        # Step 2 & 3 & 4: Fast-path text extraction + fallback strategy
        if ext == "pdf":
            # Attempt the fast text path first. A PDF with a weak/partial text
            # layer must fall back to multimodal document understanding rather
            # than being rejected solely because text extraction was poor.
            fallback_to_multimodal = False

            try:
                extracted_text = extract_cv_text(
                    storage_path=clean_path,
                    content=cv_bytes,
                )
                used_fast_path = bool(extracted_text and len(extracted_text.strip()) > 0)
            except CVParsingError:
                used_fast_path = False
                fallback_to_multimodal = True

            if used_fast_path:
                _publish_progress(norm_job_id, 35)

                try:
                    validate_cv_document(
                        text=extracted_text,
                        content_locale=content_locale or "en",
                    )
                except InvalidCVDocumentError as validation_exc:
                    if validation_exc.reason_code != "insufficient_content":
                        raise
                    fallback_to_multimodal = True

                if not fallback_to_multimodal:
                    _publish_progress(norm_job_id, 55)
                    extracted_profile = extract_structured_candidate_profile(
                        text=extracted_text,
                        content_locale=content_locale or "en",
                    )

            if fallback_to_multimodal:
                # Fallback Path: Gemini multimodal PDF document understanding.
                #
                # Once multimodal processing starts, its result/error is authoritative.
                # Do not mask a validation or structured-extraction failure with the
                # earlier text-parser exception.
                _publish_progress(norm_job_id, 35)
                validate_cv_document_multimodal(
                    content=cv_bytes,
                    mime_type="application/pdf",
                    content_locale=content_locale or "en",
                )
                _publish_progress(norm_job_id, 55)
                extracted_profile = extract_structured_candidate_profile_multimodal(
                    content=cv_bytes,
                    mime_type="application/pdf",
                    content_locale=content_locale or "en",
                )
        else:
            # DOCX: Normal text extraction fast path
            extracted_text = extract_cv_text(
                storage_path=clean_path,
                content=cv_bytes,
            )
            _publish_progress(norm_job_id, 35)
            validate_cv_document(
                text=extracted_text,
                content_locale=content_locale or "en",
            )
            _publish_progress(norm_job_id, 55)
            extracted_profile = extract_structured_candidate_profile(
                text=extracted_text,
                content_locale=content_locale or "en",
            )

        _raise_if_cancel_requested(db, job)
        _publish_progress(norm_job_id, 70)

        # Step 5: Candidate Identity Guard check BEFORE profile mutation
        existing_profile = StudentProfileRepository.get_by_user_id(db, user_id=norm_user_id)
        identity_result = evaluate_candidate_identity(
            existing_profile=existing_profile,
            extracted=extracted_profile,
            db=db,
        )

        if identity_result.verdict == IdentityVerdict.POSSIBLE_MISMATCH:
            # Do NOT replace candidate profile. Persist pending confirmation state.
            # Serialize this terminal commit against a concurrent cancellation.
            job = _lock_active_cv_job(
                db=db,
                job_id=norm_job_id,
                user_id=norm_user_id,
            )
            job.status = "completed"
            job.progress_percent = 100
            job.error = None
            job.result = {
                "requires_confirmation": True,
                "confirmed": False,
                "reason": "possible_identity_mismatch",
                "extracted_name": extracted_profile.full_name,
                "existing_name": existing_profile.full_name if existing_profile else None,
                "cv_storage_path": clean_path,
                "extracted_profile": extracted_profile.model_dump(mode="json"),
            }
            settle_job_ai_quota_if_present(
                db,
                feature_key=FEATURE_CV_ANALYSIS,
                job_id=norm_job_id,
            )
            db.commit()

            return {
                "job_id": str(norm_job_id),
                "status": "completed",
                "requires_confirmation": True,
            }

        # Step 6: Transactional structured candidate data persistence
        #
        # Serialize the final mutation boundary against cancellation. If the
        # cancellation transaction committed first, abort before touching the
        # candidate profile. If this worker locks first, cancellation waits
        # until this atomic profile+embedding transaction reaches completion.
        job = _lock_active_cv_job(
            db=db,
            job_id=norm_job_id,
            user_id=norm_user_id,
        )

        profile = replace_candidate_profile_from_extraction(
            db=db,
            user_id=norm_user_id,
            cv_storage_path=clean_path,
            extracted=extracted_profile,
        )

        # Step 7: Candidate summary embedding generation & persistence
        #
        # Do not publish progress from a separate database session between
        # profile replacement and embedding generation. These mutations must
        # remain atomic so an embedding failure can roll back the entire
        # candidate replacement.
        generate_and_persist_candidate_embedding(
            db=db,
            user_id=norm_user_id,
        )

        # Step 8: Mark job completed
        job.status = "completed"
        job.progress_percent = 100
        job.error = None
        job.result = {
            "profile_id": str(profile.id),
        }

        settle_job_ai_quota_if_present(
            db,
            feature_key=FEATURE_CV_ANALYSIS,
            job_id=norm_job_id,
        )
        db.commit()

        # Start initial match calculation after the completed CV/profile transaction.
        # This optimization is best-effort: matching failure must never fail CV extraction.
        match_job_id = None
        match_db = SessionLocal()
        try:
            match_job = ProcessingJobRepository.create(
                db=match_db,
                user_id=norm_user_id,
                job_type="match_calculation",
            )
            match_job_id = match_job.id
            match_db.commit()

            try:
                enqueue_match_calculation(
                    job_id=match_job_id,
                    user_id=norm_user_id,
                    candidate_limit=50,
                )
            except Exception:
                match_db.rollback()
                failed_match_job = ProcessingJobRepository.get_by_id(
                    match_db, match_job_id
                )
                if failed_match_job:
                    failed_match_job.status = "failed"
                    failed_match_job.progress_percent = 100
                    failed_match_job.result = None
                    failed_match_job.error = "Failed to enqueue automatic match calculation."
                    match_db.commit()
        except Exception:
            match_db.rollback()
        finally:
            match_db.close()

        return {
            "job_id": str(norm_job_id),
            "status": "completed",
            "profile_id": str(profile.id),
        }
    except CVExtractionCancelled:
        db.rollback()

        # HTTP cancellation normally releases the reservation in the same
        # transaction as the durable cancellation marker. This is an
        # idempotent worker-side safety release for races/replays.
        try:
            release_job_ai_quota_if_present(
                db,
                feature_key=FEATURE_CV_ANALYSIS,
                job_id=norm_job_id,
                reason="user_cancelled",
            )
            db.commit()
        except Exception:
            db.rollback()

        return {
            "job_id": str(norm_job_id),
            "status": "cancelled",
        }
    except Exception as exc:
        try:
            db.rollback()
        finally:
            db.close()

        # If job passed ownership and type validation, persist failure state in a fresh session
        if job_validated:
            fail_db = SessionLocal()
            try:
                fail_job = ProcessingJobRepository.get_by_id(fail_db, norm_job_id)
                if fail_job and not _job_cancel_requested(fail_job):
                    fail_job.status = "failed"
                    fail_job.progress_percent = 100
                    fail_job.result = None
                    if isinstance(exc, InvalidCVDocumentError):
                        fail_job.error = (
                            "The uploaded document does not appear to be a valid CV or resume. "
                            "Please upload a valid resume."
                        )
                    elif isinstance(exc, CVParsingError):
                        fail_job.error = (
                            "We couldn't read the uploaded document. Please make sure the "
                            "file is not corrupted and is a valid PDF or DOCX file."
                        )
                    else:
                        fail_job.error = "CV processing failed."

                    release_job_ai_quota_if_present(
                        fail_db,
                        feature_key=FEATURE_CV_ANALYSIS,
                        job_id=norm_job_id,
                        reason="worker_failure",
                    )
                    fail_db.commit()
            except Exception:
                fail_db.rollback()
            finally:
                fail_db.close()

        raise
    finally:
        if telemetry_token is not None:
            reset_ai_telemetry_context(
                telemetry_token
            )
        db.close()
