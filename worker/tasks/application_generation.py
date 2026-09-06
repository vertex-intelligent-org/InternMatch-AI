"""
RQ Application Generation Task
Provides background execution boundary for candidate personalized
cover-letter generation jobs.
"""

from typing import Any, Dict, Union
from uuid import UUID

from app.db.session import SessionLocal
from app.repositories.application import ApplicationRepository
from app.repositories.match import MatchRepository
from app.repositories.matching_data import MatchingDataRepository
from app.repositories.processing_job import ProcessingJobRepository
from app.services.ai_quota import FEATURE_APPLICATION_SUPPORT
from app.services.ai_quota_integration import (
    ensure_job_ai_quota_reserved_if_present,
    release_job_ai_quota_if_present,
    settle_job_ai_quota_if_present,
)
from app.services.ai_telemetry import (
    activate_ai_telemetry_context,
    reset_ai_telemetry_context,
)
from app.services.application_generation import generate_grounded_cover_letter


def _normalize_uuid(val: Union[UUID, str], param_name: str) -> UUID:
    """
    Normalize UUID object or string to UUID instance.
    Raises ValueError for invalid format.
    """
    if isinstance(val, UUID):
        return val
    if isinstance(val, str):
        try:
            return UUID(val)
        except (ValueError, AttributeError, TypeError):
            raise ValueError(
                f"Invalid UUID string format for {param_name}: '{val}'"
            )
    raise ValueError(
        f"Invalid UUID type for {param_name}: expected UUID or str, "
        f"got {type(val).__name__}"
    )


def run_application_generation(
    job_id: Union[UUID, str],
    user_id: Union[UUID, str],
    match_id: Union[UUID, str],
    tone: str,
    content_locale: str = "en",
) -> Dict[str, Any]:
    """
    RQ Task execution boundary for personalized cover-letter generation.
    Accepts job_id, user_id, match_id, tone, and content_locale.
    Validates job ownership and type, verifies match ownership,
    calls grounded LLM generation, persists application, and manages
    the transaction lifecycle cleanly.
    """
    norm_job_id = _normalize_uuid(job_id, "job_id")
    norm_user_id = _normalize_uuid(user_id, "user_id")
    norm_match_id = _normalize_uuid(match_id, "match_id")

    db = SessionLocal()
    job_validated = False
    telemetry_token = None

    try:
        job = ProcessingJobRepository.get_by_id(db, norm_job_id)
        if job is None:
            raise ValueError(
                f"ProcessingJob with id '{norm_job_id}' not found."
            )

        if job.user_id != norm_user_id:
            raise ValueError(
                f"Job ownership mismatch: ProcessingJob {norm_job_id} "
                f"belongs to user {job.user_id}, not user {norm_user_id}."
            )

        if job.job_type != "application_generation":
            raise ValueError(
                "ProcessingJob type mismatch: expected "
                f"'application_generation', got '{job.job_type}'."
            )

        # Precondition checks passed for target job
        job_validated = True

        # A successfully completed durable job is idempotent. Never invoke
        # the AI provider again if RQ delivers the same job more than once.
        completed_result = (
            job.result
            if isinstance(job.result, dict)
            else {}
        )
        if (
            job.status == "completed"
            and completed_result.get("application_id")
        ):
            return {
                "job_id": str(norm_job_id),
                "status": "completed",
                "application_id": str(
                    completed_result["application_id"]
                ),
            }

        # A retry after worker/provider failure reuses the same durable
        # operation idempotency key and re-reserves only if it was released.
        quota_state = ensure_job_ai_quota_reserved_if_present(
            db,
            user_id=norm_user_id,
            feature_key=FEATURE_APPLICATION_SUPPORT,
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

        # Transition to processing state
        job.status = "processing"
        job.progress_percent = 10
        job.result = None
        job.error = None
        db.flush()

        # Fetch match and verify ownership in SQL
        match_record = MatchRepository.get_match_with_details_for_user(
            db=db,
            match_id=norm_match_id,
            user_id=norm_user_id,
        )
        if not match_record:
            raise ValueError(
                f"Match '{norm_match_id}' not found or not owned "
                f"by user '{norm_user_id}'."
            )

        match, profile, internship = match_record

        # Gather the same grounded candidate context in one DB round trip.
        grounding_context = (
            MatchingDataRepository.get_ai_grounding_context(
                db,
                profile.id,
            )
        )
        cand_skills = grounding_context["skills"]
        edu_list = grounding_context["education_entries"]
        exp_list = grounding_context["experience_entries"]
        proj_list = grounding_context["project_entries"]

        # Call grounded LLM cover-letter generation
        cover_letter = generate_grounded_cover_letter(
            profile=profile,
            internship=internship,
            match=match,
            tone=tone,
            candidate_skills=cand_skills,
            education_entries=edu_list,
            experience_entries=exp_list,
            project_entries=proj_list,
            content_locale=content_locale,
        )

        # Create or update application in database
        application = ApplicationRepository.upsert_generated_cover_letter(
            db=db,
            student_id=profile.id,
            internship_id=internship.id,
            generated_cover_letter=cover_letter,
        )

        # Transition job to completed state
        job.status = "completed"
        job.progress_percent = 100
        job.error = None
        job.result = {"application_id": str(application.id)}

        settle_job_ai_quota_if_present(
            db,
            feature_key=FEATURE_APPLICATION_SUPPORT,
            job_id=norm_job_id,
        )
        db.commit()

        return {
            "job_id": str(norm_job_id),
            "status": "completed",
            "application_id": str(application.id),
        }
    except Exception:
        try:
            db.rollback()
        finally:
            db.close()

        # If job was validated, persist failure state in a fresh session
        if job_validated:
            fail_db = SessionLocal()
            try:
                fail_job = ProcessingJobRepository.get_by_id(
                    fail_db, norm_job_id
                )
                if fail_job:
                    fail_job.status = "failed"
                    fail_job.progress_percent = 100
                    fail_job.result = None
                    fail_job.error = "Application generation failed."
                    release_job_ai_quota_if_present(
                        fail_db,
                        feature_key=FEATURE_APPLICATION_SUPPORT,
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
