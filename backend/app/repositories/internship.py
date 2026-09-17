"""
Internship Catalog Repository Foundation
Provides read-only database access for internship listings.
"""

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.db.models import EmployerOrganization, InternshipListing
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session


def public_internship_visibility_condition():
    """
    Canonical public/candidate visibility rule.

    Curated visibility is explicit and never inferred from a NULL owner.
    Employer listings are public only while their bound organization is
    currently verified. Legacy/unknown rows are never public.
    """
    verified_organization_ids = select(
        EmployerOrganization.id
    ).where(
        EmployerOrganization.verification_status == "verified"
    )

    return and_(
        InternshipListing.publication_status == "published",
        or_(
            InternshipListing.listing_source == "curated",
            and_(
                InternshipListing.listing_source == "employer",
                InternshipListing.employer_organization_id.in_(
                    verified_organization_ids
                ),
            ),
        ),
    )


class InternshipRepository:
    """Repository handling database read operations for InternshipListing."""

    @staticmethod
    def get_by_id(
        db: Session,
        internship_id: UUID,
    ) -> Optional[InternshipListing]:
        """
        Fetch a listing by primary key without applying public visibility.

        Internal/server-authoritative use only. Candidate/public HTTP paths
        must use get_public_by_id().
        """
        stmt = select(InternshipListing).where(
            InternshipListing.id == internship_id
        )
        return db.scalar(stmt)

    @staticmethod
    def get_public_by_id(
        db: Session,
        internship_id: UUID,
    ) -> Optional[InternshipListing]:
        """
        Fetch one currently public internship.

        Curated rows remain eligible when active. Employer-owned rows require
        a currently verified employer organization.
        """
        stmt = select(InternshipListing).where(
            InternshipListing.id == internship_id,
            public_internship_visibility_condition(),
        )
        return db.scalar(stmt)

    @staticmethod
    def get_public_by_id_for_update(
        db: Session,
        internship_id: UUID,
    ) -> Optional[InternshipListing]:
        """
        Fetch and lock one currently public internship for a candidate write.

        populate_existing prevents an already-loaded identity-map instance
        from bypassing a fresh visibility decision immediately before the
        saved -> applied mutation.
        """
        stmt = (
            select(InternshipListing)
            .where(
                InternshipListing.id == internship_id,
                public_internship_visibility_condition(),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return db.scalar(stmt)

    @staticmethod
    def list_internships(
        db: Session,
        work_type: Optional[str] = None,
        location: Optional[str] = None,
        skill: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[InternshipListing], int]:
        """
        Fetch paginated and filtered list of active internship listings.
        Excludes closed listings from public discovery.
        Returns (items, total_count).
        """
        stmt = select(InternshipListing).where(
            public_internship_visibility_condition(),
        )

        if work_type and work_type.strip():
            stmt = stmt.where(
                func.lower(InternshipListing.work_type) == work_type.strip().lower()
            )

        if location and location.strip():
            loc_pattern = f"%{location.strip().lower()}%"
            stmt = stmt.where(func.lower(InternshipListing.location).like(loc_pattern))

        if skill and skill.strip():
            skill_pattern = f"%{skill.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(cast(InternshipListing.required_skills, String)).like(
                        skill_pattern
                    ),
                    func.lower(cast(InternshipListing.preferred_skills, String)).like(
                        skill_pattern
                    ),
                )
            )

        # Count total matching rows
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = db.scalar(count_stmt) or 0

        # Apply ordering and pagination
        safe_limit = max(1, min(limit, 50))
        safe_offset = max(0, offset)
        paged_stmt = (
            stmt.order_by(InternshipListing.created_at.desc())
            .offset(safe_offset)
            .limit(safe_limit)
        )
        items = list(db.scalars(paged_stmt).all())

        return items, total

    @staticmethod
    def create_employer_listing(
        db: Session,
        employer_user_id: UUID,
        employer_organization_id: UUID,
        title: str,
        company: str,
        location: str,
        work_type: str,
        description: str,
        required_skills: List[str],
        preferred_skills: List[str],
        language: Optional[str] = "English",
        education_requirements: Optional[str] = None,
        experience_requirements: Optional[str] = None,
        description_embedding: Optional[List[float]] = None,
    ) -> InternshipListing:
        """
        Create and persist a new InternshipListing owned by employer_user_id.
        Flushes session state; does not commit transaction.
        """
        listing = InternshipListing(
            employer_user_id=employer_user_id,
            employer_organization_id=employer_organization_id,
            listing_source="employer",
            publication_status="under_review",
            is_active=False,
            title=title,
            company=company,
            location=location,
            work_type=work_type,
            description=description,
            required_skills=required_skills or [],
            preferred_skills=preferred_skills or [],
            language=language or "English",
            education_requirements=education_requirements,
            experience_requirements=experience_requirements,
            description_embedding=description_embedding,
        )
        db.add(listing)
        db.flush()
        return listing

    @staticmethod
    def create_curated_listing(
        db: Session,
        *,
        title: str,
        company: str,
        location: str,
        work_type: str,
        description: str,
        required_skills: List[str],
        preferred_skills: List[str],
        publication_status: str,
        language: Optional[str] = "English",
        education_requirements: Optional[str] = None,
        experience_requirements: Optional[str] = None,
        description_embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InternshipListing:
        """
        Create a server-authorized curated listing.

        Curated listings are never represented as employer-authored:
        both employer ownership fields remain NULL and provenance is
        retained in metadata_json for internal auditability.
        """
        is_published = publication_status == "published"

        listing = InternshipListing(
            employer_user_id=None,
            employer_organization_id=None,
            listing_source="curated",
            publication_status=publication_status,
            is_active=is_published,
            title=title,
            company=company,
            location=location,
            work_type=work_type,
            description=description,
            required_skills=required_skills or [],
            preferred_skills=preferred_skills or [],
            language=language or "English",
            education_requirements=education_requirements,
            experience_requirements=experience_requirements,
            description_embedding=description_embedding,
            metadata_json=metadata or {},
        )

        db.add(listing)
        db.flush()
        return listing

    @staticmethod
    def count_published_by_employer(
        db: Session,
        employer_user_id: UUID,
        *,
        exclude_internship_id: Optional[UUID] = None,
    ) -> int:
        """Count authoritative published employer-owned listings."""

        stmt = (
            select(func.count())
            .select_from(InternshipListing)
            .where(
                InternshipListing.employer_user_id
                == employer_user_id,
                InternshipListing.listing_source
                == "employer",
                public_internship_visibility_condition(),
            )
        )

        if exclude_internship_id is not None:
            stmt = stmt.where(
                InternshipListing.id
                != exclude_internship_id
            )

        return int(db.scalar(stmt) or 0)

    @staticmethod
    def list_by_employer(
        db: Session,
        employer_user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[InternshipListing], int]:
        """
        Fetch paginated list of internship listings strictly owned by employer_user_id.
        Returns (items, total_count) ordered by created_at DESC.
        """
        stmt = select(InternshipListing).where(
            InternshipListing.employer_user_id == employer_user_id
        )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = db.scalar(count_stmt) or 0

        safe_limit = max(1, min(limit, 50))
        safe_offset = max(0, offset)
        paged_stmt = (
            stmt.order_by(InternshipListing.created_at.desc())
            .offset(safe_offset)
            .limit(safe_limit)
        )
        items = list(db.scalars(paged_stmt).all())
        return items, total

    @staticmethod
    def get_by_id_and_owner(
        db: Session,
        internship_id: UUID,
        employer_user_id: UUID,
    ) -> Optional[InternshipListing]:
        """
        Fetch single internship listing record ensuring it is owned by employer_user_id.
        """
        stmt = select(InternshipListing).where(
            InternshipListing.id == internship_id,
            InternshipListing.employer_user_id == employer_user_id,
        )
        return db.scalar(stmt)

    @staticmethod
    def update_employer_listing(
        db: Session,
        listing: InternshipListing,
        *,
        title: str,
        company: str,
        location: str,
        work_type: str,
        description: str,
        required_skills: List[str],
        preferred_skills: List[str],
        language: Optional[str] = "English",
        education_requirements: Optional[str] = None,
        experience_requirements: Optional[str] = None,
        description_embedding: Optional[List[float]] = None,
    ) -> InternshipListing:
        """
        Update an already ownership-verified employer listing in place.

        Does not alter employer ownership, publication state, primary key,
        creation timestamp, applications, or historical relationships.
        Flushes session state; does not commit the transaction.
        """

        listing.title = title
        listing.company = company
        listing.location = location
        listing.work_type = work_type
        listing.description = description
        listing.required_skills = required_skills or []
        listing.preferred_skills = preferred_skills or []
        listing.language = language or "English"
        listing.education_requirements = education_requirements
        listing.experience_requirements = experience_requirements

        if description_embedding is not None:
            listing.description_embedding = description_embedding

        # Any employer-authored content change invalidates prior publication
        # approval. The listing must be reviewed again before candidates can
        # discover or apply to it.
        listing.publication_status = "under_review"
        listing.is_active = False

        db.flush()
        return listing

    @staticmethod
    def list_for_admin(
        db: Session,
        publication_status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[InternshipListing], int]:
        """List all internship listings for server-authorized admin review."""
        stmt = select(InternshipListing)

        if publication_status:
            stmt = stmt.where(
                InternshipListing.publication_status == publication_status
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = db.scalar(count_stmt) or 0

        safe_limit = max(1, min(limit, 50))
        safe_offset = max(0, offset)

        paged_stmt = (
            stmt.order_by(InternshipListing.created_at.desc())
            .offset(safe_offset)
            .limit(safe_limit)
        )

        items = list(db.scalars(paged_stmt).all())
        return items, total

    @staticmethod
    def get_by_id_for_update(
        db: Session,
        internship_id: UUID,
    ) -> Optional[InternshipListing]:
        """Fetch and lock one listing for an authoritative admin mutation."""
        stmt = (
            select(InternshipListing)
            .where(InternshipListing.id == internship_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return db.scalar(stmt)

    @staticmethod
    def reopen_listing(
        db: Session,
        listing: InternshipListing,
    ) -> InternshipListing:
        """Republish a closed listing and keep the legacy activity mirror aligned."""
        listing.publication_status = "published"
        listing.is_active = True
        db.flush()
        return listing

    @staticmethod
    def close_listing(
        db: Session,
        listing: InternshipListing,
    ) -> InternshipListing:
        """
        Mark an internship listing as closed.

        publication_status is authoritative. is_active is maintained only as
        the legacy compatibility mirror.
        """
        listing.publication_status = "closed"
        listing.is_active = False
        db.flush()
        return listing
