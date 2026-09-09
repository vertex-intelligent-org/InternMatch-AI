"""
Student Profile Repository Foundation
Provides authenticated user-scoped database access for student profile records.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set
from uuid import UUID

from app.db.models import Skill, StudentProfile, StudentSkill
from app.repositories.matching_data import MatchingDataRepository
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session


class StudentProfileRepository:
    """Repository handling database read and state mutation operations for StudentProfile."""

    @staticmethod
    def get_by_user_id(db: Session, user_id: UUID) -> Optional[StudentProfile]:
        """
        Fetch student profile record scoped strictly to the authenticated user's UUID.
        Does not query or expose another user's profile.
        """
        stmt = select(StudentProfile).where(StudentProfile.user_id == user_id)
        return db.scalar(stmt)

    @staticmethod
    def upsert_by_user_id(
        db: Session,
        user_id: UUID,
        full_name: str,
        headline: Optional[str] = None,
        cv_storage_path: Optional[str] = None,
        preferences: Optional[Dict[str, Any]] = None,
    ) -> StudentProfile:
        """
        Create or update a student profile for the authenticated user_id.
        Ownership is strictly governed by the passed user_id.
        Invalidates cached summary_embedding if embedding-relevant profile inputs change.
        Flushes session state; does not commit transaction (owned by endpoint layer).
        """
        profile = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
        now = datetime.now(timezone.utc)

        if profile:
            old_preferences = profile.preferences or {}
            new_preferences = preferences if preferences is not None else old_preferences
            semantic_preference_keys = (
                "work_types",
                "desired_locations",
                "target_roles",
            )
            semantic_preferences_changed = any(
                old_preferences.get(key) != new_preferences.get(key)
                for key in semantic_preference_keys
            )
            embedding_inputs_changed = (
                profile.headline != headline
                or semantic_preferences_changed
            )

            if embedding_inputs_changed:
                profile.summary_embedding = None

            profile.full_name = full_name
            profile.headline = headline
            if cv_storage_path is not None:
                profile.cv_storage_path = cv_storage_path
            if preferences is not None:
                profile.preferences = preferences
            profile.updated_at = now
        else:
            profile = StudentProfile(
                user_id=user_id,
                full_name=full_name,
                headline=headline,
                cv_storage_path=cv_storage_path,
                preferences=preferences or {},
                created_at=now,
                updated_at=now,
            )
            db.add(profile)

        db.flush()
        return profile

    @staticmethod
    def sync_student_skills(
        db: Session,
        student_id: UUID,
        skills: Sequence[str],
    ) -> bool:
        """
        Synchronize candidate self-declared/profile skills with the provided list.

        CV evidence is server-authoritative and is never removed by manual profile
        editing. A skill may therefore be:
          - CV-evidenced only
          - self-declared only
          - both CV-evidenced and self-declared

        Returns True when self-declared/profile state meaningfully changes.
        """
        incoming_norm_map: Dict[str, str] = {}

        for skill_name in skills:
            if not isinstance(skill_name, str):
                continue

            clean = re.sub(r"\s+", " ", skill_name.strip())
            if not clean:
                continue

            folded = clean.casefold()
            if folded not in incoming_norm_map:
                incoming_norm_map[folded] = clean

        incoming_keys: Set[str] = set(incoming_norm_map.keys())

        rows = list(
            db.execute(
                select(StudentSkill, Skill)
                .join(Skill, StudentSkill.skill_id == Skill.id)
                .where(StudentSkill.student_id == student_id)
            ).all()
        )

        existing_by_folded: Dict[str, tuple[StudentSkill, Skill]] = {}

        for student_skill, skill_row in rows:
            folded = re.sub(
                r"\s+",
                " ",
                skill_row.name.strip(),
            ).casefold()

            if folded:
                existing_by_folded[folded] = (
                    student_skill,
                    skill_row,
                )

        current_self_declared = {
            folded
            for folded, (student_skill, _skill_row)
            in existing_by_folded.items()
            if student_skill.self_declared
        }

        if current_self_declared == incoming_keys:
            return False

        # Remove self-declared state for omitted skills.
        for folded in current_self_declared - incoming_keys:
            student_skill, _skill_row = existing_by_folded[folded]

            student_skill.self_declared = False

            # Delete association only when no CV evidence remains.
            if not student_skill.cv_evidenced:
                db.delete(student_skill)

        # Add self-declared state for newly selected/manual skills.
        for folded in incoming_keys - current_self_declared:
            existing = existing_by_folded.get(folded)

            if existing is not None:
                student_skill, _skill_row = existing
                student_skill.self_declared = True
                continue

            display_name = incoming_norm_map[folded]

            stmt_find = select(Skill).where(
                func.lower(Skill.name) == folded
            )
            skill_row = db.scalar(stmt_find)

            if not skill_row:
                skill_row = Skill(name=display_name)
                db.add(skill_row)
                db.flush()

            db.add(
                StudentSkill(
                    student_id=student_id,
                    skill_id=skill_row.id,
                    proficiency_level="intermediate",
                    cv_evidenced=False,
                    self_declared=True,
                    cv_provenance_known=True,
                )
            )

        db.flush()
        return True

    @staticmethod
    def set_summary_embedding(
        db: Session,
        profile: StudentProfile,
        embedding: List[float],
    ) -> StudentProfile:
        """
        Persist vector summary embedding on StudentProfile and update updated_at.
        Flushes session state; does not commit transaction.
        """
        profile.summary_embedding = embedding
        profile.updated_at = datetime.now(timezone.utc)
        db.flush()
        return profile

    @staticmethod
    def invalidate_summary_embedding(
        db: Session,
        profile: StudentProfile,
    ) -> StudentProfile:
        """
        Invalidate cached summary_embedding on StudentProfile (set to None) if not already None.
        Flushes session state; does not commit transaction.
        """
        if profile.summary_embedding is not None:
            profile.summary_embedding = None
            profile.updated_at = datetime.now(timezone.utc)
            db.flush()
        return profile

    @staticmethod
    def update_avatar_storage_path(
        db: Session,
        user_id: UUID,
        avatar_storage_path: str,
    ) -> Optional[StudentProfile]:
        """
        Persist candidate avatar storage path on StudentProfile without modifying summary_embedding.
        Flushes session state; does not commit transaction.
        """
        profile = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
        if not profile:
            return None

        profile.avatar_storage_path = avatar_storage_path
        profile.updated_at = datetime.now(timezone.utc)
        db.flush()
        return profile

    @staticmethod
    def clear_avatar_storage_path(
        db: Session,
        user_id: UUID,
    ) -> Optional[StudentProfile]:
        """
        Clear candidate avatar storage path on StudentProfile without modifying summary_embedding.
        Flushes session state; does not commit transaction.
        """
        profile = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
        if not profile:
            return None

        profile.avatar_storage_path = None
        profile.updated_at = datetime.now(timezone.utc)
        db.flush()
        return profile
