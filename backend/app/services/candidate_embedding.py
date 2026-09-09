"""
Candidate Summary & Embedding Persistence Service
Provides canonical text summary builder and vector embedding persistence
orchestration for candidates.
"""

import re
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import EducationEntry, ExperienceEntry, ProjectEntry
from app.repositories.matching_data import MatchingDataRepository
from app.repositories.student_profile import StudentProfileRepository
from app.services.embeddings import generate_embedding


class CandidateEmbeddingPreconditionError(ValueError):
    """Raised when candidate embedding generation/persistence preconditions are not met."""

    pass


def _normalize_text_scalar(val: Optional[str]) -> str:
    """Strip outer whitespace and collapse repeated internal whitespace to a single space."""
    if not val or not isinstance(val, str):
        return ""
    return re.sub(r"\s+", " ", val.strip())


def _normalize_string_list(items: Optional[Sequence[str]]) -> List[str]:
    """
    Ignore empty/whitespace-only items, normalize whitespace,
    deduplicate case-insensitively while preserving original normalized casing,
    and sort alphabetically by casefolded value.
    """
    if not items:
        return []
    seen_folded = set()
    result = []
    for item in items:
        if not item or not isinstance(item, str):
            continue
        norm = re.sub(r"\s+", " ", item.strip())
        if not norm:
            continue
        folded = norm.casefold()
        if folded not in seen_folded:
            seen_folded.add(folded)
            result.append(norm)
    return sorted(result, key=lambda x: x.casefold())


def _extract_preference_list(prefs: Optional[Dict[str, Any]], key: str) -> List[str]:
    """
    Validate and extract specified preference key from preferences dictionary.
    Raises CandidateEmbeddingPreconditionError if preferences shape or items are invalid.
    """
    if prefs is None:
        return []
    if not isinstance(prefs, dict):
        raise CandidateEmbeddingPreconditionError("preferences must be a dictionary or None")
    if key not in prefs or prefs[key] is None:
        return []
    val = prefs[key]
    if not isinstance(val, list):
        raise CandidateEmbeddingPreconditionError(
            f"Preference '{key}' must be a list, got {type(val).__name__}"
        )
    for item in val:
        if item is not None and not isinstance(item, str):
            raise CandidateEmbeddingPreconditionError(
                f"Preference '{key}' items must be strings, got {type(item).__name__}"
            )
    return _normalize_string_list([item for item in val if isinstance(item, str)])


def build_candidate_embedding_text(
    *,
    headline: Optional[str] = None,
    skills: Sequence[str] = (),
    education: Sequence[EducationEntry] = (),
    experience: Sequence[ExperienceEntry] = (),
    projects: Sequence[ProjectEntry] = (),
    preferences: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Construct canonical summary text representation for candidate embedding generation.
    Deterministic, case-preserving, whitespace-collapsed, casefold-sorted string lists.
    Only non-empty sections are included, separated by blank lines.
    Excludes PII (full_name, IDs, cv_storage_path, timestamps, raw CV text).
    """
    sections: List[str] = []

    # 1. Headline
    norm_headline = _normalize_text_scalar(headline)
    if norm_headline:
        sections.append(f"Headline: {norm_headline}")

    # 2. Skills
    norm_skills = _normalize_string_list(skills)
    if norm_skills:
        skills_lines = ["Skills:"] + [f"- {s}" for s in norm_skills]
        sections.append("\n".join(skills_lines))

    # 3. Education
    edu_lines: List[str] = []
    for entry in education:
        deg = _normalize_text_scalar(getattr(entry, "degree", ""))
        inst = _normalize_text_scalar(getattr(entry, "institution", ""))
        sy = str(entry.start_year) if getattr(entry, "start_year", None) is not None else ""
        ey = str(entry.end_year) if getattr(entry, "end_year", None) is not None else ""
        if deg or inst or sy or ey:
            edu_lines.append(f"- {deg} | {inst} | {sy} | {ey}")
    if edu_lines:
        sections.append("\n".join(["Education:"] + edu_lines))

    # 4. Experience
    exp_lines: List[str] = []
    for entry in experience:
        role = _normalize_text_scalar(getattr(entry, "role", ""))
        company = _normalize_text_scalar(getattr(entry, "company", ""))
        sd = str(entry.start_date) if getattr(entry, "start_date", None) is not None else ""
        ed = str(entry.end_date) if getattr(entry, "end_date", None) is not None else ""
        desc = _normalize_text_scalar(getattr(entry, "description", ""))
        if role or company or sd or ed or desc:
            exp_lines.append(f"- {role} | {company} | {sd} | {ed} | {desc}")
    if exp_lines:
        sections.append("\n".join(["Experience:"] + exp_lines))

    # 5. Projects
    proj_lines: List[str] = []
    for entry in projects:
        title = _normalize_text_scalar(getattr(entry, "title", ""))
        raw_tech = getattr(entry, "tech_stack", None)
        tech_norm = _normalize_string_list(raw_tech)
        tech_joined = ", ".join(tech_norm)
        desc = _normalize_text_scalar(getattr(entry, "description", ""))
        if title or tech_joined or desc:
            proj_lines.append(f"- {title} | {tech_joined} | {desc}")
    if proj_lines:
        sections.append("\n".join(["Projects:"] + proj_lines))

    # 6. Preferences
    work_types = _extract_preference_list(preferences, "work_types")
    desired_locations = _extract_preference_list(preferences, "desired_locations")
    target_roles = _extract_preference_list(preferences, "target_roles")

    pref_lines: List[str] = []
    if work_types:
        pref_lines.append(f"- work_types: {', '.join(work_types)}")
    if desired_locations:
        pref_lines.append(f"- desired_locations: {', '.join(desired_locations)}")
    if target_roles:
        pref_lines.append(f"- target_roles: {', '.join(target_roles)}")
    if pref_lines:
        sections.append("\n".join(["Preferences:"] + pref_lines))

    return "\n\n".join(sections)


def generate_and_persist_candidate_embedding(
    db: Session,
    user_id: UUID,
) -> List[float]:
    """
    Generate and persist summary_embedding for candidate profile identified by user_id.
    Loads candidate matching context, builds canonical summary text, invokes embedding provider,
    and flushes persisted embedding on StudentProfile.
    Caller owns database transaction (commit/rollback).
    """
    profile = MatchingDataRepository.get_profile_by_user_id(db, user_id=user_id)
    if profile is None:
        raise CandidateEmbeddingPreconditionError(
            f"No StudentProfile found for user_id '{user_id}'"
        )

    # Keep semantic ranking grounded consistently with direct skill scoring.
    # Known self-declared-only skills stay visible on the profile but do not
    # influence the candidate embedding used by ranking.
    skills = MatchingDataRepository.get_ranking_skill_names_for_student(
        db,
        profile.id,
    )
    education = MatchingDataRepository.get_education_for_student(db, profile.id)
    experience = MatchingDataRepository.get_experience_for_student(db, profile.id)
    projects = MatchingDataRepository.get_projects_for_student(db, profile.id)

    summary_text = build_candidate_embedding_text(
        headline=profile.headline,
        skills=skills,
        education=education,
        experience=experience,
        projects=projects,
        preferences=profile.preferences,
    )

    if not summary_text.strip():
        raise CandidateEmbeddingPreconditionError(
            "Candidate summary text is empty; cannot generate embedding"
        )

    embedding = generate_embedding(summary_text)

    StudentProfileRepository.set_summary_embedding(
        db=db,
        profile=profile,
        embedding=embedding,
    )

    return embedding
