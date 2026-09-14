"""
Processing Job Status Tracking Endpoints
Provides authenticated job status retrieval for asynchronous tasks.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.repositories.processing_job import ProcessingJobRepository
from app.schemas.job import ProcessingJobResponse
from app.services.processing_job_cancellation import (
    ProcessingJobCancellationNotFound,
    ProcessingJobCancellationTerminal,
    ProcessingJobCancellationUnsupported,
    cancel_user_processing_job,
)
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

router = APIRouter()


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


@router.get("/{job_id}", response_model=ProcessingJobResponse)
def get_job_status(
    job_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve status of asynchronous processing job for authenticated user.
    Query is scoped strictly by job_id and authenticated user_id.
    """
    job = ProcessingJobRepository.get_by_id_and_user_id(
        db=db, job_id=job_id, user_id=current_user.user_id
    )
    if not job:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error("Processing job not found."),
        )
    return ProcessingJobResponse.from_orm_model(job)

@router.post("/{job_id}/cancel")
def cancel_processing_job(
    job_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cancel one authenticated user's active durable AI job.

    Ownership is enforced by the same authenticated user identity used by
    GET /jobs/{job_id}. Completed jobs cannot be retroactively refunded.
    """
    try:
        job = cancel_user_processing_job(
            db=db,
            job_id=job_id,
            user_id=current_user.user_id,
        )
    except ProcessingJobCancellationNotFound:
        raise HTTPException(
            status_code=404,
            detail="Processing job not found.",
        )
    except ProcessingJobCancellationUnsupported:
        raise HTTPException(
            status_code=400,
            detail="This processing job cannot be cancelled.",
        )
    except ProcessingJobCancellationTerminal as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )

    return {
        "job_id": job.id,
        "status": "cancelled",
        "message": "AI operation cancelled.",
    }
