"""
Match Repository Foundation
Provides database read and write operations for candidate internship matches.
"""

from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from app.db.models import InternshipListing, Match, StudentProfile
from sqlalchemy import CursorResult, delete, select
from sqlalchemy.orm import Session


class MatchRepository:
    """Repository handling database read and write operations for candidate matches."""

    @staticmethod
    def get_matches_for_user(
        db: Session, user_id: UUID
    ) -> List[Tuple[Match, InternshipListing]]:
        """
        Fetch pre-calculated matches for the candidate identified by user_id.
        Joins StudentProfile to enforce tenant ownership strictly in SQL.
        Joins InternshipListing to load internship summary data.
        Ordered by overall_score DESC, created_at DESC.
        """
        stmt = (
            select(Match, InternshipListing)
            .join(StudentProfile, Match.student_id == StudentProfile.id)
            .join(InternshipListing, Match.internship_id == InternshipListing.id)
            .where(StudentProfile.user_id == user_id)
            .order_by(Match.overall_score.desc(), Match.created_at.desc())
        )
        return list(db.execute(stmt).tuples().all())

    @staticmethod
    def get_match_with_details_for_user(
        db: Session, match_id: UUID, user_id: UUID
    ) -> Optional[Tuple[Match, StudentProfile, InternshipListing]]:
        """
        Fetch a specific Match by match_id and enforce ownership via
        StudentProfile.user_id == user_id. Joins StudentProfile and InternshipListing.
        Returns (Match, StudentProfile, InternshipListing) or None if not found
        or not owned by the specified user.
        """
        stmt = (
            select(Match, StudentProfile, InternshipListing)
            .join(StudentProfile, Match.student_id == StudentProfile.id)
            .join(InternshipListing, Match.internship_id == InternshipListing.id)
            .where(Match.id == match_id, StudentProfile.user_id == user_id)
        )
        return db.execute(stmt).tuples().first()

    @staticmethod
    def get_matches_by_student_id(db: Session, student_id: UUID) -> List[Match]:
        """Fetch all existing Match records for a student."""
        stmt = select(Match).where(Match.student_id == student_id)
        return list(db.scalars(stmt).all())


    @staticmethod
    def get_match_by_student_and_internship(
        db: Session,
        *,
        student_id: UUID,
        internship_id: UUID,
    ) -> Match | None:
        """Fetch one student's match for one internship."""
        stmt = select(Match).where(
            Match.student_id == student_id,
            Match.internship_id == internship_id,
        )
        return db.scalar(stmt)

    @staticmethod
    def upsert_match(
        db: Session,
        student_id: UUID,
        internship_id: UUID,
        overall_score: int,
        skill_score: int,
        vector_score: int,
        attribute_score: int,
        skill_gap_analysis: dict,
        existing_match: Optional[Match] = None,
    ) -> Match:
        """
        Create a new Match or update an existing Match in place.
        Preserves Match.id and created_at on update.
        Resets why_you_match to None.
        Does NOT commit or rollback.
        """
        if existing_match:
            existing_match.overall_score = overall_score
            existing_match.skill_score = skill_score
            existing_match.vector_score = vector_score
            existing_match.attribute_score = attribute_score
            existing_match.skill_gap_analysis = skill_gap_analysis
            existing_match.why_you_match = None
            return existing_match

        new_match = Match(
            student_id=student_id,
            internship_id=internship_id,
            overall_score=overall_score,
            skill_score=skill_score,
            vector_score=vector_score,
            attribute_score=attribute_score,
            skill_gap_analysis=skill_gap_analysis,
            why_you_match=None,
        )
        db.add(new_match)
        return new_match

    @staticmethod
    def delete_stale_matches(
        db: Session, student_id: UUID, current_internship_ids: Sequence[UUID]
    ) -> int:
        """
        Delete Match rows for student_id whose internship_id is not in current_internship_ids.
        If current_internship_ids is empty, deletes all Match rows for student_id.
        Does NOT affect other students' matches. Does NOT commit or rollback.
        """
        if current_internship_ids:
            stmt = delete(Match).where(
                Match.student_id == student_id,
                Match.internship_id.not_in(current_internship_ids),
            )
        else:
            stmt = delete(Match).where(Match.student_id == student_id)

        result = db.execute(stmt)
        return int(result.rowcount) if isinstance(result, CursorResult) else 0
