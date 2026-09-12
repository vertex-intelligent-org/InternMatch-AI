"""
RQ worker for durable, cancellable interview-preparation generation.
"""

from typing import Union
from uuid import UUID

from app.db.session import SessionLocal
from app.repositories.application import ApplicationRepository
from app.repositories.processing_job import ProcessingJobRepository
from app.services.ai_quota import (
    AIQuotaExceededError,
    FEATURE_INTERVIEW_PREP,
)
from app.services.ai_quota_integration import (
    format_ai_quota_exceeded_payload,
    release_job_ai_quota_if_present,
)
from app.services.interview_prep import get_or_create_interview_prep
from tasks.durable_ai_generation import (
    DurableAIGenerationCancelled,
    job_cancel_requested,
    lock_active_job_or_cancel,
    prepare_job_completion,
)


def _normalize_uuid(value: Union[UUID, str], name: str) -> UUID:
    if isinstance(value, UUID):
        return value

    if isinstance(value, str):
        try:
            return UUID(value)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError(
                f"Invalid UUID string for {name}: {value!r}"
            ) from exc

    raise ValueError(
        f"Invalid UUID type for {name}: {type(value).__name__}"
    )


def _release_cancelled_quota(db, job_id: UUID) -> None:
    try:
        release_job_ai_quota_if_present(
            db,
            feature_key=FEATURE_INTERVIEW_PREP,
            job_id=job_id,
            reason="user_cancelled",
        )
        db.commit()
    except Exception:
        db.rollback()


def _persist_failure(
    *,
    job_id: UUID,
    user_id: UUID,
    error: str,
    result: dict | None,
) -> None:
    fail_db = SessionLocal()

    try:
        job = ProcessingJobRepository.get_by_id_and_user_id_for_update(
            db=fail_db,
            job_id=job_id,
            user_id=user_id,
        )

        if job is None:
            fail_db.rollback()
            return

        fail_db.refresh(job)

        if (
            job.job_type != "interview_prep"
            or job_cancel_requested(job)
            or job.status == "completed"
        ):
            fail_db.rollback()
            return

        job.status = "failed"
        job.progress_percent = 100
        job.result = result
        job.error = error

        release_job_ai_quota_if_present(
            fail_db,
            feature_key=FEATURE_INTERVIEW_PREP,
            job_id=job_id,
            reason="worker_failure",
        )

        fail_db.commit()
    except Exception:
        fail_db.rollback()
    finally:
        fail_db.close()


def run_interview_prep_generation(
    job_id: Union[UUID, str],
    user_id: Union[UUID, str],
    application_id: Union[UUID, str],
    content_locale: str = "en",
) -> dict:
    norm_job_id = _normalize_uuid(job_id, "job_id")
    norm_user_id = _normalize_uuid(user_id, "user_id")
    norm_application_id = _normalize_uuid(
        application_id,
        "application_id",
    )

    locale = (content_locale or "en").strip().lower()
    if locale not in {"en", "tr", "ar"}:
        raise ValueError(
            f"Unsupported interview preparation locale: {content_locale!r}"
        )

    db = SessionLocal()
    job_validated = False

    try:
        job = ProcessingJobRepository.get_by_id(
            db=db,
            job_id=norm_job_id,
        )

        if job is None:
            raise ValueError(
                f"ProcessingJob {norm_job_id} not found."
            )

        if job.user_id != norm_user_id:
            raise ValueError(
                f"ProcessingJob {norm_job_id} ownership mismatch."
            )

        if job.job_type != "interview_prep":
            raise ValueError(
                "ProcessingJob type mismatch: expected "
                f"'interview_prep', got {job.job_type!r}."
            )

        job_validated = True

        if job_cancel_requested(job):
            return {
                "job_id": str(norm_job_id),
                "status": "cancelled",
            }

        if job.status == "completed":
            return {
                "job_id": str(norm_job_id),
                "status": "completed",
                "result": (
                    job.result
                    if isinstance(job.result, dict)
                    else {}
                ),
            }

        job = lock_active_job_or_cancel(
            db,
            job_id=norm_job_id,
            user_id=norm_user_id,
            expected_job_type="interview_prep",
        )

        job.status = "processing"
        job.progress_percent = 10
        job.result = None
        job.error = None
        db.commit()

        record = ApplicationRepository.get_with_internship_for_user(
            db=db,
            application_id=norm_application_id,
            user_id=norm_user_id,
        )

        if not record:
            raise ValueError("Application not found.")

        application, internship = record

        if internship is None:
            raise ValueError(
                "Interview preparation requires an internship-linked "
                "application."
            )

        def finalize_response(response: object) -> None:
            prepare_job_completion(
                db,
                job_id=norm_job_id,
                user_id=norm_user_id,
                expected_job_type="interview_prep",
                response=response,
            )

        response = get_or_create_interview_prep(
            db=db,
            application=application,
            internship=internship,
            user_id=norm_user_id,
            content_locale=locale,
            processing_job_id=norm_job_id,
            before_async_finalize=finalize_response,
        )

        # Cache hits do not reserve quota and therefore finalize here.
        result_payload = prepare_job_completion(
            db,
            job_id=norm_job_id,
            user_id=norm_user_id,
            expected_job_type="interview_prep",
            response=response,
        )
        db.commit()

        return {
            "job_id": str(norm_job_id),
            "status": "completed",
            "result": result_payload,
        }

    except DurableAIGenerationCancelled:
        db.rollback()
        _release_cancelled_quota(db, norm_job_id)

        return {
            "job_id": str(norm_job_id),
            "status": "cancelled",
        }

    except AIQuotaExceededError as exc:
        db.rollback()

        if job_validated:
            _persist_failure(
                job_id=norm_job_id,
                user_id=norm_user_id,
                error="AI quota exceeded.",
                result=format_ai_quota_exceeded_payload(exc),
            )

        raise

    except Exception:
        db.rollback()

        if job_validated:
            _persist_failure(
                job_id=norm_job_id,
                user_id=norm_user_id,
                error="Interview preparation generation failed.",
                result=None,
            )

        raise

    finally:
        db.close()
