"""
Candidate Matches Endpoints
Provides authenticated read access for pre-calculated internship matches
and POST trigger to enqueue match calculation.
"""

from typing import Literal
from uuid import UUID

from app.core.rate_limit import enforce_rate_limit
from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.repositories.match import MatchRepository
from app.repositories.processing_job import ProcessingJobRepository
from app.schemas.match import (
    MatchCalculationAcceptedResponse,
    MatchExplanationResponse,
    MatchItemResponse,
    MatchListResponse,
)
from app.services.ai_quota import AIQuotaExceededError
from app.services.match_enqueue import enqueue_match_calculation
from app.services.match_explanation import get_or_create_match_explanation
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("", response_model=MatchListResponse)
def get_my_matches(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve pre-calculated matches for the authenticated candidate, sorted by score.
    Requires valid Supabase Bearer JWT authentication token.
    Identity is strictly derived from the validated JWT subject UUID.
    """
    records = MatchRepository.get_matches_for_user(
        db=db, user_id=current_user.user_id
    )

    items = [
        MatchItemResponse.from_orm_tuple(match=match, internship=internship)
        for match, internship in records
    ]

    return MatchListResponse(matches=items)


@router.post(
    "/calculate",
    response_model=MatchCalculationAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def calculate_matches(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Enqueue asynchronous candidate match calculation background processing job.
    Requires valid Supabase Bearer JWT authentication token.
    Identity is strictly derived from the validated JWT subject UUID.
    Creates ProcessingJob record (status='queued'), commits before enqueue,
    and dispatches task to Redis RQ queue.
    """
    enforce_rate_limit(
        user_id=current_user.user_id, scope="match_calculate"
    )

    try:
        processing_job = ProcessingJobRepository.create(
            db=db,
            user_id=current_user.user_id,
            job_type="match_calculation",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    try:
        enqueue_match_calculation(
            job_id=processing_job.id,
            user_id=current_user.user_id,
            candidate_limit=50,
        )
    except Exception:
        safe_error = "Failed to enqueue match calculation job."
        try:
            processing_job.status = "failed"
            processing_job.progress_percent = 100
            processing_job.result = None
            processing_job.error = safe_error
            db.commit()
        except Exception:
            db.rollback()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue match calculation job.",
        )

    return MatchCalculationAcceptedResponse(
        job_id=processing_job.id,
        status="queued",
        message="Matching calculation enqueued.",
    )


@router.get(
    "/{id}/explanation",
    response_model=MatchExplanationResponse,
)
def get_match_explanation(
    id: UUID,
    content_locale: Literal["en", "tr", "ar"] = Query(
        "en", description="Target content display locale ('en', 'tr', 'ar')"
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve grounded LLM explanation ('Why You Match') and skill gap
    analysis for a match in target content_locale.
    Requires valid Supabase Bearer JWT authentication token.
    Identity is strictly derived from the validated JWT subject UUID.
    Returns 404 if match is not found or owned by another user.
    """
    enforce_rate_limit(
        user_id=current_user.user_id, scope="match_explanation"
    )

    try:
        explanation = get_or_create_match_explanation(
            db=db,
            match_id=id,
            user_id=current_user.user_id,
            content_locale=content_locale,
        )
    except AIQuotaExceededError:
        # Global handler emits the machine-readable AI_QUOTA_EXCEEDED contract.
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Match explanation service is temporarily unavailable.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve match explanation.",
        ) from exc

    if explanation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match not found.",
        )

    return explanation
