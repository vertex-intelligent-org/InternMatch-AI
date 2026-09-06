"""
Processing Job Repository Foundation
Provides user-scoped and internal background worker database access for processing job records.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from app.db.models import ProcessingJob
from sqlalchemy import select
from sqlalchemy.orm import Session


class ProcessingJobRepository:
    """Repository handling database read and write operations for ProcessingJob."""

    @staticmethod
    def get_by_id_and_user_id(
        db: Session, job_id: UUID, user_id: UUID
    ) -> Optional[ProcessingJob]:
        """
        Fetch processing job record scoped strictly by BOTH job_id AND user_id.
        Enforces tenant isolation directly in SQL query.
        """
        stmt = select(ProcessingJob).where(
            ProcessingJob.id == job_id, ProcessingJob.user_id == user_id
        )
        return db.scalar(stmt)

    @staticmethod
    def get_by_id_and_user_id_for_update(
        db: Session,
        job_id: UUID,
        user_id: UUID,
    ) -> Optional[ProcessingJob]:
        """
        Fetch a user-owned processing job while acquiring a database row lock.

        Used for state-changing authenticated flows that must serialize
        concurrent requests for the same ProcessingJob. PostgreSQL holds the
        row lock until the caller commits or rolls back the transaction.
        """
        stmt = (
            select(ProcessingJob)
            .where(
                ProcessingJob.id == job_id,
                ProcessingJob.user_id == user_id,
            )
            # PostgreSQL renders this as FOR NO KEY UPDATE. It still
            # serializes concurrent writers for this ProcessingJob, while
            # remaining compatible with the KEY SHARE lock required by
            # AI telemetry foreign-key validation on processing_job_id.
            .with_for_update(key_share=True)
        )
        return db.scalar(stmt)

    @staticmethod
    def get_by_id(db: Session, job_id: UUID) -> Optional[ProcessingJob]:
        """
        Internal worker lookup by primary key UUID.
        Trusted internal background worker usage ONLY; NOT for authenticated HTTP endpoints.
        """
        stmt = select(ProcessingJob).where(ProcessingJob.id == job_id)
        return db.scalar(stmt)

    @staticmethod
    def create(
        db: Session,
        user_id: UUID,
        job_type: str,
    ) -> ProcessingJob:
        """
        Create a new ProcessingJob record with status="queued" and progress_percent=0.
        Flushes session state; caller controls transaction commit/rollback.
        """
        now = datetime.now(timezone.utc)
        job = ProcessingJob(
            user_id=user_id,
            job_type=job_type,
            status="queued",
            progress_percent=0,
            created_at=now,
            updated_at=now,
        )
        db.add(job)
        db.flush()
        return job

    @staticmethod
    def update_state(
        db: Session,
        job_id: UUID,
        status: str,
        progress_percent: int,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[ProcessingJob]:
        """
        Update state of an existing ProcessingJob record by primary key UUID.
        Raises ValueError if progress_percent is outside range 0..100.
        Returns None if job does not exist.
        Flushes session state; caller controls transaction commit/rollback.
        """
        if progress_percent < 0 or progress_percent > 100:
            raise ValueError(
                f"Invalid progress_percent {progress_percent}. Must be between 0 and 100."
            )

        job = ProcessingJobRepository.get_by_id(db, job_id=job_id)
        if not job:
            return None

        job.status = status
        job.progress_percent = progress_percent
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error
        job.updated_at = datetime.now(timezone.utc)

        db.flush()
        return job
