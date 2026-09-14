"""
Candidate Profile Structured Write Repository Foundation
Provides atomic transactional replacement of candidate profile data
(StudentProfile, StudentSkill, EducationEntry, ExperienceEntry, ProjectEntry)
from extracted CV schemas without performing commit/rollback.
Preserves manual skills and reconciles CV-evidenced skill provenance.
"""

import re
from typing import Any, Dict
from uuid import UUID

from app.db.models import (
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    Skill,
    StudentProfile,
    StudentSkill,
)
from app.repositories.student_profile import StudentProfileRepository
from app.services.cv_profile_extraction import ExtractedCandidateProfile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session


def replace_candidate_profile_from_extraction(
    db: Session,
    *,
    user_id: UUID,
    cv_storage_path: str,
    extracted: ExtractedCandidateProfile,
) -> StudentProfile:
    """
    Atomically update candidate profile and structured CV data in a single transaction.
    Invalidates summary_embedding prior to replacement.
    Replaces previous candidate CV skills with the skills extracted from the new CV.
    Flushes all mutations to the current session.
    Caller owns transaction lifecycle (commit/rollback).
    """
    if not isinstance(user_id, UUID):
        raise ValueError("user_id must be a valid UUID")

    if not cv_storage_path or not isinstance(cv_storage_path, str):
        raise ValueError("cv_storage_path must be a non-empty string")

    if not isinstance(extracted, ExtractedCandidateProfile):
        raise TypeError(
            "extracted must be an ExtractedCandidateProfile instance, "
            f"got {type(extracted).__name__}"
        )

    # 1. Preserve existing manual/profile metadata and overlay only
    # meaningful semantic preferences extracted from the CV.
    existing_profile = StudentProfileRepository.get_by_user_id(db, user_id=user_id)
    preferences_dict: Dict[str, Any] = dict(
        (existing_profile.preferences or {}) if existing_profile else {}
    )

    extracted_preferences: Dict[str, Any] = {}
    if extracted.preferences:
        if hasattr(extracted.preferences, "model_dump"):
            extracted_preferences = extracted.preferences.model_dump()
        elif isinstance(extracted.preferences, dict):
            extracted_preferences = extracted.preferences

    for key in ("work_types", "desired_locations", "target_roles"):
        value = extracted_preferences.get(key)
        if value:
            preferences_dict[key] = value

    # 2. Upsert base StudentProfile record
    profile = StudentProfileRepository.upsert_by_user_id(
        db=db,
        user_id=user_id,
        full_name=re.sub(r"\s+", " ", extracted.full_name.strip()),
        headline=re.sub(r"\s+", " ", extracted.headline.strip()) if extracted.headline else None,
        cv_storage_path=cv_storage_path.strip(),
        preferences=preferences_dict,
    )
    db.flush()

    # 3. Explicitly invalidate summary_embedding before updating related structured rows
    StudentProfileRepository.invalidate_summary_embedding(db, profile)

    # 4. Remove previous history entries (education, experience, projects)
    db.execute(delete(EducationEntry).where(EducationEntry.student_id == profile.id))
    db.execute(delete(ExperienceEntry).where(ExperienceEntry.student_id == profile.id))
    db.execute(delete(ProjectEntry).where(ProjectEntry.student_id == profile.id))

    # 5. Reconcile CV-evidenced skills while preserving manual/profile skills.
    #
    # Existing self-declared skills are never destroyed by CV replacement.
    # The latest accepted CV is authoritative only for cv_evidenced state.
    existing_rows = list(
        db.scalars(
            select(StudentSkill).where(
                StudentSkill.student_id == profile.id
            )
        ).all()
    )

    existing_by_folded: Dict[str, StudentSkill] = {}
    for row in existing_rows:
        skill_name = row.skill.name if row.skill else None
        if not skill_name:
            skill_row = db.get(Skill, row.skill_id)
            skill_name = skill_row.name if skill_row else None

        if not skill_name:
            continue

        folded = re.sub(r"\s+", " ", skill_name.strip()).casefold()
        if folded:
            existing_by_folded[folded] = row

    extracted_by_folded: Dict[str, tuple[str, str]] = {}

    for s in extracted.skills:
        if not s.name or not isinstance(s.name, str):
            continue

        norm_name = re.sub(r"\s+", " ", s.name.strip())
        if not norm_name:
            continue

        folded = norm_name.casefold()
        if folded in extracted_by_folded:
            continue

        prof_level = (
            s.proficiency_level.strip()
            if s.proficiency_level and s.proficiency_level.strip()
            else "intermediate"
        )

        extracted_by_folded[folded] = (norm_name, prof_level)

    # Any previous CV evidence absent from the newly accepted CV is removed.
    # Self-declared evidence remains intact.
    for folded, row in list(existing_by_folded.items()):
        # The accepted current CV makes CV provenance authoritative for every
        # pre-existing skill row, whether the skill appears in this CV or not.
        row.cv_provenance_known = True

        if folded not in extracted_by_folded and row.cv_evidenced:
            row.cv_evidenced = False

            if not row.self_declared:
                db.delete(row)

    # Add or upgrade every skill evidenced by the newly accepted CV.
    for folded, (display_name, prof_level) in extracted_by_folded.items():
        existing_row = existing_by_folded.get(folded)

        if existing_row is not None:
            existing_row.cv_evidenced = True
            existing_row.cv_provenance_known = True
            existing_row.proficiency_level = prof_level
            continue

        stmt = select(Skill).where(func.lower(Skill.name) == folded)
        skill_row = db.scalar(stmt)

        if not skill_row:
            skill_row = Skill(name=display_name)
            db.add(skill_row)
            db.flush()

        db.add(
            StudentSkill(
                student_id=profile.id,
                skill_id=skill_row.id,
                proficiency_level=prof_level,
                cv_evidenced=True,
                self_declared=False,
                cv_provenance_known=True,
            )
        )

    # 6. Insert Education History Entries
    for edu in extracted.education:
        inst = re.sub(r"\s+", " ", edu.institution.strip()) if edu.institution else ""
        deg = re.sub(r"\s+", " ", edu.degree.strip()) if edu.degree else ""
        if inst or deg:
            db.add(
                EducationEntry(
                    student_id=profile.id,
                    institution=inst,
                    degree=deg,
                    start_year=edu.start_year,
                    end_year=edu.end_year,
                )
            )

    # 7. Insert Experience History Entries
    for exp in extracted.experience:
        comp = re.sub(r"\s+", " ", exp.company.strip()) if exp.company else ""
        role = re.sub(r"\s+", " ", exp.role.strip()) if exp.role else ""
        desc = exp.description.strip() if exp.description else None
        if comp or role:
            db.add(
                ExperienceEntry(
                    student_id=profile.id,
                    company=comp,
                    role=role,
                    description=desc,
                    start_date=exp.start_date,
                    end_date=exp.end_date,
                )
            )

    # 8. Insert Project Entries
    for proj in extracted.projects:
        title = re.sub(r"\s+", " ", proj.title.strip()) if proj.title else ""
        desc = proj.description.strip() if proj.description else None
        tech_stack = (
            [re.sub(r"\s+", " ", t.strip()) for t in proj.tech_stack if t and t.strip()]
            if proj.tech_stack
            else []
        )
        if title:
            db.add(
                ProjectEntry(
                    student_id=profile.id,
                    title=title,
                    tech_stack=tech_stack,
                    description=desc,
                )
            )

    db.flush()
    return profile
