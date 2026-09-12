"""
RQ worker for durable, cancellable Why You Match generation.
"""

from typing import Union
from uuid import UUID

from app.db.session import SessionLocal
from app.repositories.processing_job import ProcessingJobRepository
from app.services.ai_quota import (
    AIQuotaExceededError,
    FEATURE_MATCH_EXPLANATION,
)
from app.services.ai_quota_integration import (
    format_ai_quota_exceeded_payload,
    release_job_ai_quota_if_present,
)
from app.services.match_explanation import get_or_create_match_explanation
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
            feature_key=FEATURE_MATCH_EXPLANATION,
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
            job.job_type != "match_explanation"
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
            feature_key=FEATURE_MATCH_EXPLANATION,
            job_id=job_id,
            reason="worker_failure",
        )

        fail_db.commit()
    except Exception:
        fail_db.rollback()
    finally:
        fail_db.close()


def run_match_explanation_generation(
    job_id: Union[UUID, str],
    user_id: Union[UUID, str],
    match_id: Union[UUID, str],
    content_locale: str = "en",
) -> dict:
    norm_job_id = _normalize_uuid(job_id, "job_id")
    norm_user_id = _normalize_uuid(user_id, "user_id")
    norm_match_id = _normalize_uuid(match_id, "match_id")

    locale = (content_locale or "en").strip().lower()
    if locale not in {"en", "tr", "ar"}:
        raise ValueError(
            f"Unsupported match explanation locale: {content_locale!r}"
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

        if job.job_type != "match_explanation":
            raise ValueError(
                "ProcessingJob type mismatch: expected "
                f"'match_explanation', got {job.job_type!r}."
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
            expected_job_type="match_explanation",
        )

        job.status = "processing"
        job.progress_percent = 10
        job.result = None
        job.error = None
        db.commit()

        def finalize_response(response: object) -> None:
            prepare_job_completion(
                db,
                job_id=norm_job_id,
                user_id=norm_user_id,
                expected_job_type="match_explanation",
                response=response,
            )

        response = get_or_create_match_explanation(
            db=db,
            match_id=norm_match_id,
            user_id=norm_user_id,
            content_locale=locale,
            processing_job_id=norm_job_id,
            before_async_finalize=finalize_response,
        )

        if response is None:
            raise ValueError("Match not found.")

        # Cache hits and deterministic/existing fallbacks do not reserve quota,
        # so they reach here without the service-level fresh-generation
        # finalizer. Finalize them under the same authoritative lock.
        result_payload = prepare_job_completion(
            db,
            job_id=norm_job_id,
            user_id=norm_user_id,
            expected_job_type="match_explanation",
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
                error="Match explanation generation failed.",
                result=None,
            )

        raise

    finally:
        db.close()
