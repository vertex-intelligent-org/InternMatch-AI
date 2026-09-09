"""
Deterministic Match Calculation & Persistence Service Foundation
Connects matching data repository, vector retrieval, skill classification,
and scoring engine to compute and persist hybrid candidate match records.
"""

import math
from collections.abc import Callable
from typing import Any, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Match
from app.repositories.match import MatchRepository
from app.repositories.matching_data import MatchingDataRepository
from app.repositories.vector_retrieval import VectorRetrievalRepository
from app.services.scoring import calculate_hybrid_score
from app.services.skill_matching import SkillMatchResult, classify_skill_matches


class MatchCalculationPreconditionError(Exception):
    """Raised when profile or embedding preconditions required for matching are not met."""

    pass


def round_score_for_persistence(score: float) -> int:
    """
    Round float score [0.0, 100.0] to database integer using round-half-up semantics.
    int(score + 0.5)
    Raises ValueError for non-finite values or values outside [0.0, 100.0].
    """
    if math.isnan(score) or math.isinf(score):
        raise ValueError(f"Invalid non-finite persistence score: {score}")

    if not (0.0 <= score <= 100.0):
        raise ValueError(f"Persistence score {score} out of valid range [0.0, 100.0]")

    return int(score + 0.5)


def parse_preferences(
    preferences: Any,
) -> Tuple[Optional[List[str]], Optional[List[str]]]:
    """
    Extract work_types and desired_locations safely from JSON preferences dictionary.
    Raises MatchCalculationPreconditionError if a present key is not a JSON list of strings.
    """
    if preferences is None:
        return None, None

    if not isinstance(preferences, dict):
        raise MatchCalculationPreconditionError(
            "Stored preferences must be a JSON dictionary object."
        )

    def _extract_string_list(key: str) -> Optional[List[str]]:
        if key not in preferences or preferences[key] is None:
            return None
        val = preferences[key]
        if not isinstance(val, list):
            raise MatchCalculationPreconditionError(
                f"Preference key '{key}' must be a JSON list of strings."
            )
        for idx, item in enumerate(val):
            if not isinstance(item, str):
                raise MatchCalculationPreconditionError(
                    f"Preference key '{key}' item at index {idx} must be a string."
                )
        return val

    wt = _extract_string_list("work_types")
    loc = _extract_string_list("desired_locations")
    return wt, loc


def build_skill_gap_analysis(skill_match_result: SkillMatchResult) -> dict:
    """
    Build canonical deterministic skill_gap_analysis dictionary.
    Combines matched required then matched preferred skills.
    Combines missing required then missing preferred skills.
    De-duplicates preserving first occurrence, original spelling, and order.
    Sets summary = "" and recommendations = [].
    """
    raw_matching = (
        skill_match_result.matched_required_skills
        + skill_match_result.matched_preferred_skills
    )
    raw_missing = (
        skill_match_result.missing_required_skills
        + skill_match_result.missing_preferred_skills
    )

    def _dedupe(skills: Sequence[str]) -> List[str]:
        seen = set()
        deduped = []
        for s in skills:
            norm = s.strip().casefold()
            if norm and norm not in seen:
                seen.add(norm)
                deduped.append(s)
        return deduped

    return {
        "matching_skills": _dedupe(raw_matching),
        "missing_skills": _dedupe(raw_missing),
        "summary": "",
        "recommendations": [],
    }


def calculate_and_persist_matches(
    db: Session,
    user_id: UUID,
    candidate_limit: int,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> List[Match]:
    """
    Calculate and persist hybrid matches for candidate identified by user_id.
    Executes profile loading, vector candidate retrieval, skill classification,
    hybrid score calculation, persistence rounding, in-place match synchronization,
    and stale match cleanup.
    Flushes DB session but NEVER commits or rolls back transaction.
    """
    if candidate_limit <= 0:
        raise ValueError(f"Invalid candidate_limit {candidate_limit}. Limit must be > 0.")

    # 1. Load profile
    profile = MatchingDataRepository.get_profile_by_user_id(db, user_id)
    if profile is None:
        raise MatchCalculationPreconditionError(
            f"No StudentProfile found for user_id {user_id}."
        )

    # 2. Require summary_embedding
    if not profile.summary_embedding:
        raise MatchCalculationPreconditionError(
            f"StudentProfile for user_id {user_id} has missing or empty summary_embedding."
        )

    # 3. Parse preferences safely
    work_types, desired_locations = parse_preferences(profile.preferences)

    # 4. Load only skills permitted to influence canonical ranking.
    #
    # This preserves legacy unknown rows for migration compatibility while
    # excluding known self-declared-only claims from the 50% skill component.
    candidate_skills = MatchingDataRepository.get_ranking_skill_names_for_student(
        db,
        profile.id,
    )

    if progress_callback is not None:
        progress_callback(35)

    # 5. Retrieve vector candidates
    candidates = VectorRetrievalRepository.get_nearest_internships(
        db=db,
        candidate_embedding=profile.summary_embedding,
        limit=candidate_limit,
    )

    if progress_callback is not None:
        progress_callback(60)

    # Pre-fetch existing matches for student to enable fast in-place update
    existing_matches = MatchRepository.get_matches_by_student_id(db, profile.id)
    existing_match_map = {m.internship_id: m for m in existing_matches}

    if progress_callback is not None:
        progress_callback(75)

    current_matches: List[Match] = []
    current_internship_ids: List[UUID] = []

    # 6. Process candidates
    for cand in candidates:
        internship = cand.internship
        current_internship_ids.append(internship.id)

        req_skills = internship.required_skills or []
        pref_skills = internship.preferred_skills or []

        skill_match_res = classify_skill_matches(
            candidate_skills=candidate_skills,
            required_skills=req_skills,
            preferred_skills=pref_skills,
        )

        hybrid_score = calculate_hybrid_score(
            skill_match_result=skill_match_res,
            cosine_distance=cand.cosine_distance,
            work_types=work_types,
            desired_locations=desired_locations,
            internship_work_type=internship.work_type,
            internship_location=internship.location,
        )

        skill_gap = build_skill_gap_analysis(skill_match_res)

        p_skill = round_score_for_persistence(hybrid_score.skill_score)
        p_vector = round_score_for_persistence(hybrid_score.vector_score)
        p_attribute = round_score_for_persistence(hybrid_score.attribute_score)
        p_overall = round_score_for_persistence(hybrid_score.overall_score)

        existing_match = existing_match_map.get(internship.id)

        match_obj = MatchRepository.upsert_match(
            db=db,
            student_id=profile.id,
            internship_id=internship.id,
            overall_score=p_overall,
            skill_score=p_skill,
            vector_score=p_vector,
            attribute_score=p_attribute,
            skill_gap_analysis=skill_gap,
            existing_match=existing_match,
        )
        current_matches.append(match_obj)

    # 7. Delete stale matches for this student only
    MatchRepository.delete_stale_matches(
        db=db,
        student_id=profile.id,
        current_internship_ids=current_internship_ids,
    )

    # 8. Flush DB session to expose ORM state/IDs without committing
    db.flush()

    # 9. Return matches in vector candidate input order
    return current_matches
