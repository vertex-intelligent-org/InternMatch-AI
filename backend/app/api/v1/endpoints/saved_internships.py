"""
Candidate Saved Internships Endpoints
Provides authenticated endpoints for saving/bookmarking internships,
listing candidate saved internships with real listing data, and unsaving bookmarks.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.repositories.internship import InternshipRepository
from app.repositories.saved_internship import SavedInternshipRepository
from app.repositories.student_profile import StudentProfileRepository
from app.schemas.internship import InternshipSummaryResponse
from app.schemas.saved_internship import (
    SavedInternshipItem,
    SavedInternshipListResponse,
    SaveInternshipResponse,
    UnsaveInternshipResponse,
)
from fastapi import APIRouter, Depends, Query, status
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


@router.get("", response_model=SavedInternshipListResponse)
def list_saved_internships(
    limit: int = Query(20, ge=1, le=50, description="Pagination limit (default 20, max 50)"),
    offset: int = Query(0, ge=0, description="Pagination offset (default 0)"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve candidate saved internships (bookmarks) with complete real internship summary data.
    Requires valid Supabase Bearer JWT authentication token.
    Identity is strictly derived from the validated JWT subject UUID.
    Returns saved internships ordered newest saved first.
    """
    records, total = SavedInternshipRepository.list_for_user(
        db=db,
        user_id=current_user.user_id,
        limit=limit,
        offset=offset,
    )

    items = [
        SavedInternshipItem(
            id=saved.id,
            internship_id=saved.internship_id,
            saved_at=saved.created_at,
            internship=InternshipSummaryResponse.from_orm_model(internship),
        )
        for saved, internship in records
    ]

    return SavedInternshipListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{internship_id}",
    response_model=SaveInternshipResponse,
    responses={
        404: {"description": "Internship listing or Candidate profile not found"},
    },
)
def save_internship(
    internship_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Save/bookmark an internship for the authenticated candidate.
    Requires valid Supabase Bearer JWT authentication token.
    Identity is strictly derived from the validated JWT subject UUID.
    Idempotent: duplicate save returns existing saved bookmark state.
    """
    profile = StudentProfileRepository.get_by_user_id(db=db, user_id=current_user.user_id)
    if not profile:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error(
                "Candidate profile not found. Please create a profile before saving internships."
            ),
        )

    internship = InternshipRepository.get_public_by_id(
        db=db,
        internship_id=internship_id,
    )
    if not internship:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=format_not_found_error("Internship listing not found."),
        )

    try:
        saved, _ = SavedInternshipRepository.save(
            db=db,
            student_id=profile.id,
            internship_id=internship_id,
        )
        db.commit()
        db.refresh(saved)
    except Exception:
        db.rollback()
        raise

    return SaveInternshipResponse(
        id=saved.id,
        internship_id=internship_id,
        saved_at=saved.created_at,
        is_saved=True,
        message="Internship saved successfully.",
    )


@router.delete(
    "/{internship_id}",
    response_model=UnsaveInternshipResponse,
)
def unsave_internship(
    internship_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Remove candidate's bookmark for an internship.
    Requires valid Supabase Bearer JWT authentication token.
    Identity is strictly derived from the validated JWT subject UUID.
    Idempotent: unsaving a non-bookmarked internship returns 200 OK cleanly.
    Never modifies or deletes InternshipListing or Application records.
    """
    profile = StudentProfileRepository.get_by_user_id(db=db, user_id=current_user.user_id)
    if profile:
        try:
            SavedInternshipRepository.unsave(
                db=db,
                student_id=profile.id,
                internship_id=internship_id,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

    return UnsaveInternshipResponse(
        internship_id=internship_id,
        is_saved=False,
        message="Internship unsaved successfully.",
    )
