"""
RQ Match Calculation Task
Provides background execution boundary for candidate match calculation jobs.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Union
from uuid import UUID

from app.db.models import ProcessingJob
from app.db.session import SessionLocal
from app.repositories.matching_data import MatchingDataRepository
from app.repositories.processing_job import ProcessingJobRepository
from app.services.candidate_embedding import generate_and_persist_candidate_embedding
from app.services.match_calculation import calculate_and_persist_matches
from sqlalchemy import update
from sqlalchemy.engine import Connection


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


def _publish_progress(
    connection: Connection | None,
    job_id: UUID,
    progress_percent: int,
) -> None:
    """Persist a real match-calculation stage without reopening terminal jobs."""
    if connection is None or progress_percent <= 0 or progress_percent >= 100:
        return

    try:
        statement = (
            update(ProcessingJob)
            .where(
                ProcessingJob.id == job_id,
                ProcessingJob.status == "processing",
            )
            .values(
                progress_percent=progress_percent,
                updated_at=datetime.now(timezone.utc),
            )
        )

        result = connection.execute(statement)

        if result.rowcount == 0:
            connection.rollback()
            return

        connection.commit()
    except Exception:
        connection.rollback()


def run_match_calculation(
    job_id: Union[UUID, str],
    user_id: Union[UUID, str],
    candidate_limit: int = 50,
) -> Dict[str, Any]:
    """
    RQ Task execution boundary for match calculation.
    Accepts job_id, user_id, and optional candidate_limit (default 50).
    Validates job ownership and type, sets job state, executes match calculation,
    and manages transaction lifecycle cleanly.
    """
    norm_job_id = _normalize_uuid(job_id, "job_id")
    norm_user_id = _normalize_uuid(user_id, "user_id")

    if candidate_limit <= 0:
        raise ValueError(f"Invalid candidate_limit {candidate_limit}. Limit must be > 0.")

    db = SessionLocal()
    job_validated = False
    progress_connection: Connection | None = None

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

        if job.job_type != "match_calculation":
            raise ValueError(
                f"ProcessingJob type mismatch: expected 'match_calculation', got '{job.job_type}'."
            )

        # Precondition checks passed for target job
        job_validated = True

        # Transition to processing state
        job.status = "processing"
        job.progress_percent = 10
        job.result = None
        job.error = None
        db.commit()

        progress_connection = db.get_bind().connect()

        # Recover a missing cached candidate embedding.
        profile = MatchingDataRepository.get_profile_by_user_id(
            db=db,
            user_id=norm_user_id,
        )
        if profile is not None and not profile.summary_embedding:
            generate_and_persist_candidate_embedding(
                db=db,
                user_id=norm_user_id,
            )

        # Call Gate 2.19 match calculation service
        matches = calculate_and_persist_matches(
            db=db,
            user_id=norm_user_id,
            candidate_limit=candidate_limit,
            progress_callback=lambda progress: _publish_progress(
                progress_connection,
                norm_job_id,
                progress,
            ),
        )

        # Transition to completed state
        match_count = len(matches)
        job.status = "completed"
        job.progress_percent = 100
        job.error = None
        job.result = {"match_count": match_count}

        db.commit()

        return {
            "job_id": str(norm_job_id),
            "status": "completed",
            "match_count": match_count,
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
                fail_job = ProcessingJobRepository.get_by_id(fail_db, norm_job_id)
                if fail_job:
                    fail_job.status = "failed"
                    fail_job.progress_percent = 100
                    fail_job.result = None
                    fail_job.error = "Match calculation failed."
                    fail_db.commit()
            except Exception:
                fail_db.rollback()
            finally:
                fail_db.close()

        raise
    finally:
        if progress_connection is not None:
            progress_connection.close()
        db.close()

