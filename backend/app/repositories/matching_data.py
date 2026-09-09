"""
Matching Data Read Repository Foundation
Provides trusted internal database read operations for candidate matching context.
"""

from typing import List, Optional
from uuid import UUID

from app.db.models import (
    EducationEntry,
    ExperienceEntry,
    InternshipListing,
    ProjectEntry,
    Skill,
    StudentProfile,
    StudentSkill,
)
from sqlalchemy import select, text
from sqlalchemy.orm import Session


class MatchingDataRepository:
    """Repository providing read operations for candidate profile and internship
    matching context."""

    @staticmethod
    def get_profile_by_user_id(db: Session, user_id: UUID) -> Optional[StudentProfile]:
        """
        Retrieve StudentProfile record by authenticated user_id.
        Returns None if no profile exists for the specified user_id.
        """
        stmt = select(StudentProfile).where(StudentProfile.user_id == user_id)
        return db.scalar(stmt)

    @staticmethod
    def get_skill_names_for_student(db: Session, student_id: UUID) -> List[str]:
        """
        Retrieve deterministic list of skill names for a given student_id.
        Joins StudentSkill -> Skill. Results ordered alphabetically by Skill.name.
        """
        stmt = (
            select(Skill.name)
            .join(StudentSkill, StudentSkill.skill_id == Skill.id)
            .where(StudentSkill.student_id == student_id)
            .order_by(Skill.name.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_ranking_skill_names_for_student(
        db: Session,
        student_id: UUID,
    ) -> List[str]:
        """
        Return candidate skills permitted to influence canonical ranking.

        Included:
          - current CV-evidenced skills
          - pre-provenance legacy skills whose historical CV source is unknown

        Excluded:
          - known self-declared-only skills

        The legacy compatibility branch prevents migration-time score collapse,
        while newly-added profile claims cannot improve ranking without CV
        evidence.
        """
        stmt = (
            select(Skill.name)
            .join(StudentSkill, StudentSkill.skill_id == Skill.id)
            .where(
                StudentSkill.student_id == student_id,
                (
                    StudentSkill.cv_evidenced.is_(True)
                    | StudentSkill.cv_provenance_known.is_(False)
                ),
            )
            .order_by(Skill.name.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_skill_evidence_for_student(
        db: Session,
        student_id: UUID,
    ) -> List[dict]:
        """
        Return deterministic skill provenance for a candidate.

        Provenance is backend-owned and derived from StudentSkill state.
        """
        stmt = (
            select(
                Skill.name,
                StudentSkill.cv_evidenced,
                StudentSkill.self_declared,
                StudentSkill.cv_provenance_known,
            )
            .join(StudentSkill, StudentSkill.skill_id == Skill.id)
            .where(StudentSkill.student_id == student_id)
            .order_by(Skill.name.asc())
        )

        return [
            {
                "name": name,
                "cv_evidenced": bool(cv_evidenced),
                "self_declared": bool(self_declared),
                "cv_provenance_known": bool(cv_provenance_known),
            }
            for name, cv_evidenced, self_declared, cv_provenance_known
            in db.execute(stmt).all()
        ]

    @staticmethod
    def get_education_for_student(db: Session, student_id: UUID) -> List[EducationEntry]:
        """
        Retrieve EducationEntry records for a given student_id.
        Ordered deterministically by start_year ASC, id ASC.
        """
        stmt = (
            select(EducationEntry)
            .where(EducationEntry.student_id == student_id)
            .order_by(EducationEntry.start_year.asc(), EducationEntry.id.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_experience_for_student(db: Session, student_id: UUID) -> List[ExperienceEntry]:
        """
        Retrieve ExperienceEntry records for a given student_id.
        Ordered deterministically by start_date ASC, id ASC.
        """
        stmt = (
            select(ExperienceEntry)
            .where(ExperienceEntry.student_id == student_id)
            .order_by(ExperienceEntry.start_date.asc(), ExperienceEntry.id.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_projects_for_student(db: Session, student_id: UUID) -> List[ProjectEntry]:
        """
        Retrieve ProjectEntry records for a given student_id.
        Ordered deterministically by title ASC, id ASC.
        """
        stmt = (
            select(ProjectEntry)
            .where(ProjectEntry.student_id == student_id)
            .order_by(ProjectEntry.title.asc(), ProjectEntry.id.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_internship_by_id(db: Session, internship_id: UUID) -> Optional[InternshipListing]:
        """
        Retrieve InternshipListing by primary key UUID, including description_embedding.
        Returns None if internship does not exist.
        """
        stmt = select(InternshipListing).where(InternshipListing.id == internship_id)
        return db.scalar(stmt)


    @staticmethod
    def get_structured_profile_by_user_id(
        db: Session,
        user_id: UUID,
    ) -> Optional[dict[str, object]]:
        """Fetch the complete structured profile with one PostgreSQL round trip."""
        bind = db.get_bind()

        if (
            bind is None
            or bind.dialect.name != "postgresql"
        ):
            profile = MatchingDataRepository.get_profile_by_user_id(
                db,
                user_id,
            )

            if profile is None:
                return None

            education = MatchingDataRepository.get_education_for_student(
                db,
                profile.id,
            )
            experience = MatchingDataRepository.get_experience_for_student(
                db,
                profile.id,
            )
            projects = MatchingDataRepository.get_projects_for_student(
                db,
                profile.id,
            )

            return {
                "id": profile.id,
                "user_id": profile.user_id,
                "full_name": profile.full_name,
                "headline": profile.headline,
                "preferences": profile.preferences,
                "avatar_storage_path": profile.avatar_storage_path,
                "skills": MatchingDataRepository.get_skill_names_for_student(
                    db,
                    profile.id,
                ),
                "education": [
                    {
                        "institution": entry.institution,
                        "degree": entry.degree,
                        "start_year": entry.start_year,
                        "end_year": entry.end_year,
                    }
                    for entry in education
                ],
                "experience": [
                    {
                        "company": entry.company,
                        "role": entry.role,
                        "description": entry.description,
                        "start_date": entry.start_date,
                        "end_date": entry.end_date,
                    }
                    for entry in experience
                ],
                "projects": [
                    {
                        "title": entry.title,
                        "tech_stack": entry.tech_stack,
                        "description": entry.description,
                    }
                    for entry in projects
                ],
            }

        row = db.execute(
            text(
                """
                SELECT
                    sp.id,
                    sp.user_id,
                    sp.full_name,
                    sp.headline,
                    sp.preferences,
                    sp.avatar_storage_path,

                    COALESCE(
                        (
                            SELECT jsonb_agg(
                                s.name
                                ORDER BY s.name ASC
                            )
                            FROM public.student_skills ss
                            JOIN public.skills s
                                ON s.id = ss.skill_id
                            WHERE ss.student_id = sp.id
                        ),
                        CAST('[]' AS jsonb)
                    ) AS skills,

                    COALESCE(
                        (
                            SELECT jsonb_agg(
                                jsonb_build_object(
                                    'institution', e.institution,
                                    'degree', e.degree,
                                    'start_year', e.start_year,
                                    'end_year', e.end_year
                                )
                                ORDER BY
                                    e.start_year ASC,
                                    e.id ASC
                            )
                            FROM public.education_entries e
                            WHERE e.student_id = sp.id
                        ),
                        CAST('[]' AS jsonb)
                    ) AS education,

                    COALESCE(
                        (
                            SELECT jsonb_agg(
                                jsonb_build_object(
                                    'company', x.company,
                                    'role', x.role,
                                    'description', x.description,
                                    'start_date', x.start_date,
                                    'end_date', x.end_date
                                )
                                ORDER BY
                                    x.start_date ASC,
                                    x.id ASC
                            )
                            FROM public.experience_entries x
                            WHERE x.student_id = sp.id
                        ),
                        CAST('[]' AS jsonb)
                    ) AS experience,

                    COALESCE(
                        (
                            SELECT jsonb_agg(
                                jsonb_build_object(
                                    'title', p.title,
                                    'tech_stack', p.tech_stack,
                                    'description', p.description
                                )
                                ORDER BY
                                    p.title ASC,
                                    p.id ASC
                            )
                            FROM public.project_entries p
                            WHERE p.student_id = sp.id
                        ),
                        CAST('[]' AS jsonb)
                    ) AS projects

                FROM public.student_profiles sp
                WHERE sp.user_id = :user_id
                LIMIT 1
                """
            ),
            {
                "user_id": user_id,
            },
        ).mappings().one_or_none()

        if row is None:
            return None

        return dict(row)

    @staticmethod
    def get_ai_grounding_context(
        db: Session,
        student_id: UUID,
    ) -> dict[str, list[str]]:
        """
        Fetch AI grounding context with one PostgreSQL round trip.

        SQLite and other non-PostgreSQL test/runtime environments
        preserve the existing repository methods and their contracts.
        """

        bind = db.get_bind()

        if (
            bind is None
            or bind.dialect.name
            != "postgresql"
        ):
            education = (
                MatchingDataRepository
                .get_education_for_student(
                    db,
                    student_id,
                )
            )
            experience = (
                MatchingDataRepository
                .get_experience_for_student(
                    db,
                    student_id,
                )
            )
            projects = (
                MatchingDataRepository
                .get_projects_for_student(
                    db,
                    student_id,
                )
            )

            return {
                "skills": (
                    MatchingDataRepository
                    .get_skill_names_for_student(
                        db,
                        student_id,
                    )
                ),
                "education_entries": [
                    (
                        f"{entry.degree} at "
                        f"{entry.institution} "
                        f"({entry.start_year or ''}-"
                        f"{entry.end_year or ''})"
                    )
                    for entry in education
                ],
                "experience_entries": [
                    (
                        f"{entry.role} at "
                        f"{entry.company}: "
                        f"{entry.description or ''}"
                    )
                    for entry in experience
                ],
                "project_entries": [
                    (
                        f"{entry.title} "
                        f"({', '.join(entry.tech_stack or [])}): "
                        f"{entry.description or ''}"
                    )
                    for entry in projects
                ],
            }

        row = db.execute(
            text(
                """
                SELECT
                    COALESCE(
                        (
                            SELECT
                                jsonb_agg(s.name ORDER BY s.name ASC)
                            FROM public.student_skills ss
                            JOIN public.skills s
                                ON s.id = ss.skill_id
                            WHERE
                                ss.student_id = :student_id
                        ),
                        CAST('[]' AS jsonb)
                    ) AS skills,

                    COALESCE(
                        (
                            SELECT
                                jsonb_agg(
                                    e.degree || ' at ' ||
                                    e.institution || ' (' ||
                                    CASE
                                        WHEN e.start_year IS NULL
                                             OR e.start_year = 0
                                        THEN ''
                                        ELSE CAST(e.start_year AS text)
                                    END ||
                                    '-' ||
                                    CASE
                                        WHEN e.end_year IS NULL
                                             OR e.end_year = 0
                                        THEN ''
                                        ELSE CAST(e.end_year AS text)
                                    END ||
                                    ')'
                                    ORDER BY
                                        e.start_year ASC,
                                        e.id ASC
                                )
                            FROM public.education_entries e
                            WHERE
                                e.student_id = :student_id
                        ),
                        CAST('[]' AS jsonb)
                    ) AS education_entries,

                    COALESCE(
                        (
                            SELECT
                                jsonb_agg(
                                    x.role || ' at ' ||
                                    x.company || ': ' ||
                                    COALESCE(
                                        x.description,
                                        ''
                                    )
                                    ORDER BY
                                        x.start_date ASC,
                                        x.id ASC
                                )
                            FROM public.experience_entries x
                            WHERE
                                x.student_id = :student_id
                        ),
                        CAST('[]' AS jsonb)
                    ) AS experience_entries,

                    COALESCE(
                        (
                            SELECT
                                jsonb_agg(
                                    p.title || ' (' ||
                                    COALESCE(
                                        array_to_string(
                                            p.tech_stack,
                                            ', '
                                        ),
                                        ''
                                    ) ||
                                    '): ' ||
                                    COALESCE(
                                        p.description,
                                        ''
                                    )
                                    ORDER BY
                                        p.title ASC,
                                        p.id ASC
                                )
                            FROM public.project_entries p
                            WHERE
                                p.student_id = :student_id
                        ),
                        CAST('[]' AS jsonb)
                    ) AS project_entries
                """
            ),
            {
                "student_id": student_id,
            },
        ).mappings().one()

        result = {}

        for key in (
            "skills",
            "education_entries",
            "experience_entries",
            "project_entries",
        ):
            value = row[key]

            if not isinstance(
                value,
                list,
            ):
                raise TypeError(
                    "PostgreSQL grounding context "
                    f"field '{key}' must be a list."
                )

            result[key] = [
                str(item)
                for item in value
            ]

        return result
