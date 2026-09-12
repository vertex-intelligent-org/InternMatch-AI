"""
Saved Internship Repository Foundation
Provides database operations for candidate bookmarks (SavedInternship),
including idempotent save, unsave, and non-N+1 paginated joined retrieval.
"""

from typing import List, Optional, Tuple
from uuid import UUID

from app.db.models import InternshipListing, SavedInternship, StudentProfile
from app.repositories.internship import public_internship_visibility_condition
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


class SavedInternshipRepository:
    """Repository handling database read and write operations for candidate bookmarks."""

    @staticmethod
    def get_by_student_and_internship(
        db: Session,
        student_id: UUID,
        internship_id: UUID,
    ) -> Optional[SavedInternship]:
        """Fetch existing SavedInternship record by student_id and internship_id."""
        stmt = select(SavedInternship).where(
            SavedInternship.student_id == student_id,
            SavedInternship.internship_id == internship_id,
        )
        return db.scalars(stmt).first()

    @staticmethod
    def save(
        db: Session,
        student_id: UUID,
        internship_id: UUID,
    ) -> Tuple[SavedInternship, bool]:
        """
        Save/bookmark an internship for candidate.
        Idempotent: if bookmark already exists, returns (existing, False).
        Uses a savepoint (begin_nested) to safely handle concurrent insert races
        enforcing DB uniqueness without corrupting the active transaction session.
        Performs db.flush() but leaves transaction commit ownership to endpoint layer.
        """
        existing = SavedInternshipRepository.get_by_student_and_internship(
            db=db,
            student_id=student_id,
            internship_id=internship_id,
        )
        if existing:
            return existing, False

        try:
            with db.begin_nested():
                new_saved = SavedInternship(
                    student_id=student_id,
                    internship_id=internship_id,
                )
                db.add(new_saved)
                db.flush()
            return new_saved, True
        except IntegrityError as exc:
            # Check if concurrent transaction committed the duplicate row
            existing = SavedInternshipRepository.get_by_student_and_internship(
                db=db,
                student_id=student_id,
                internship_id=internship_id,
            )
            if existing:
                return existing, False
            # Re-raise unrelated integrity errors (e.g. invalid FK)
            raise exc

    @staticmethod
    def unsave(
        db: Session,
        student_id: UUID,
        internship_id: UUID,
    ) -> bool:
        """
        Remove candidate's bookmark for an internship.
        Idempotent: returns True if bookmark was deleted, False if it was not found.
        Never modifies or deletes InternshipListing or Application records.
        Performs db.flush() but leaves transaction commit ownership to endpoint layer.
        """
        existing = SavedInternshipRepository.get_by_student_and_internship(
            db=db,
            student_id=student_id,
            internship_id=internship_id,
        )
        if not existing:
            return False

        db.delete(existing)
        db.flush()
        return True

    @staticmethod
    def list_for_user(
        db: Session,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Tuple[SavedInternship, InternshipListing]], int]:
        """
        Fetch paginated saved internships for candidate identified by user_id.
        Joins StudentProfile to enforce tenant ownership strictly in SQL.
        Joins InternshipListing in a single query to eliminate N+1 latency.
        Deterministically ordered by SavedInternship.created_at DESC, SavedInternship.id DESC.
        Returns (items, total_count).
        """
        base_stmt = (
            select(SavedInternship, InternshipListing)
            .join(
                StudentProfile,
                SavedInternship.student_id == StudentProfile.id,
            )
            .join(
                InternshipListing,
                SavedInternship.internship_id == InternshipListing.id,
            )
            .where(
                StudentProfile.user_id == user_id,
                public_internship_visibility_condition(),
            )
        )

        count_stmt = (
            select(func.count(SavedInternship.id))
            .join(
                StudentProfile,
                SavedInternship.student_id == StudentProfile.id,
            )
            .join(
                InternshipListing,
                SavedInternship.internship_id == InternshipListing.id,
            )
            .where(
                StudentProfile.user_id == user_id,
                public_internship_visibility_condition(),
            )
        )
        total = db.scalar(count_stmt) or 0

        safe_limit = max(1, min(limit, 50))
        safe_offset = max(0, offset)

        paged_stmt = (
            base_stmt.order_by(
                SavedInternship.created_at.desc(),
                SavedInternship.id.desc(),
            )
            .offset(safe_offset)
            .limit(safe_limit)
        )
        records = list(db.execute(paged_stmt).tuples().all())
        return records, total
