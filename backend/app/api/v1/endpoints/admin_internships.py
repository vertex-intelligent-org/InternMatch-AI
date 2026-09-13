"""Server-authorized administration of internship listings."""

from typing import Literal, Optional
from uuid import UUID

from app.core.security import AuthenticatedUser, require_admin_user
from app.db.session import get_db
from app.repositories.employer_organization import EmployerOrganizationRepository
from app.repositories.internship import InternshipRepository
from app.services.employer_product_policy import (
    EmployerListingLimitError,
    require_employer_listing_capacity,
)
from app.schemas.internship import (
    InternshipDetailResponse,
    InternshipListResponse,
    InternshipSummaryResponse,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session


router = APIRouter()

PublicationStatus = Literal[
    "draft",
    "under_review",
    "published",
    "closed",
]


@router.get(
    "",
    response_model=InternshipListResponse,
)
def list_admin_internships(
    publication_status: Optional[PublicationStatus] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    _admin_user: AuthenticatedUser = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """List internship listings across all publication states."""
    items, total = InternshipRepository.list_for_admin(
        db=db,
        publication_status=publication_status,
        limit=limit,
        offset=offset,
    )

    return InternshipListResponse(
        items=[
            InternshipSummaryResponse.from_orm_model(item)
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{id}",
    response_model=InternshipDetailResponse,
)
def get_admin_internship(
    id: UUID,
    _admin_user: AuthenticatedUser = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Read one listing without applying public visibility rules."""
    listing = InternshipRepository.get_by_id(
        db=db,
        internship_id=id,
    )

    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internship listing not found.",
        )

    return InternshipDetailResponse.from_orm_model(listing)


@router.post(
    "/{id}/close",
    response_model=InternshipDetailResponse,
)
def close_admin_internship(
    id: UUID,
    _admin_user: AuthenticatedUser = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """Administratively close an internship listing."""
    listing = InternshipRepository.get_by_id_for_update(
        db=db,
        internship_id=id,
    )

    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internship listing not found.",
        )

    try:
        if listing.publication_status != "closed":
            listing = InternshipRepository.close_listing(
                db=db,
                listing=listing,
            )

        db.commit()
        db.refresh(listing)
    except Exception:
        db.rollback()
        raise

    return InternshipDetailResponse.from_orm_model(listing)


@router.post(
    "/{id}/reopen",
    response_model=InternshipDetailResponse,
)
def reopen_admin_internship(
    id: UUID,
    _admin_user: AuthenticatedUser = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    """
    Republish a closed listing.

    Employer-owned listings require a currently verified organization.
    """
    snapshot = InternshipRepository.get_by_id(
        db=db,
        internship_id=id,
    )

    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internship listing not found.",
        )

    if snapshot.publication_status != "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only closed internship listings can be reopened.",
        )

    if snapshot.listing_source == "employer":
        organization_id = snapshot.employer_organization_id

        if organization_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Employer-owned listing is not bound "
                    "to an organization."
                ),
            )

        organization = EmployerOrganizationRepository.get_by_id_for_update(
            db,
            organization_id,
        )

        if (
            organization is None
            or organization.verification_status != "verified"
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Employer organization must be verified "
                    "before reopening."
                ),
            )

        employer_user_id = snapshot.employer_user_id

        if employer_user_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Employer-owned listing has no "
                    "authoritative employer owner."
                ),
            )

        try:
            require_employer_listing_capacity(
                db,
                user_id=employer_user_id,
                exclude_internship_id=snapshot.id,
            )
        except EmployerListingLimitError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "The employer's current plan has no "
                    "capacity for another published internship."
                ),
            ) from exc

    listing = InternshipRepository.get_by_id_for_update(
        db=db,
        internship_id=id,
    )

    if (
        listing is None
        or listing.publication_status != "closed"
    ):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Internship listing changed before "
                "the reopen action completed."
            ),
        )

    try:
        listing = InternshipRepository.reopen_listing(
            db=db,
            listing=listing,
        )
        db.commit()
        db.refresh(listing)
    except Exception:
        db.rollback()
        raise

    return InternshipDetailResponse.from_orm_model(listing)
