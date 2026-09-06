"""
Candidate Identity Comparison Service
Provides conservative, multi-signal identity verification between an existing
candidate profile and a newly extracted CV profile before destructive replacement.
Enforces the rule that one candidate account represents one person while avoiding
false positives for name variations, formatting changes, or life updates.
"""

import difflib
import re
from typing import Any, Dict, Optional, Set
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import StudentProfile
from app.repositories.matching_data import MatchingDataRepository
from app.services.cv_profile_extraction import ExtractedCandidateProfile


class IdentityVerdict:
    """Standard machine-readable verdicts for candidate identity comparison."""

    SAME_CANDIDATE = "same_candidate"
    POSSIBLE_MISMATCH = "possible_mismatch"
    INSUFFICIENT_IDENTITY_EVIDENCE = "insufficient_identity_evidence"


class IdentityComparisonResult(BaseModel):
    """Structured result of candidate identity evaluation."""

    verdict: str = Field(
        ...,
        description="Verdict: same_candidate, possible_mismatch, or insufficient_identity_evidence",
    )
    reason: str = Field(..., description="Human-readable rationale for the verdict")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    details: Dict[str, Any] = Field(default_factory=dict)


def _normalize_token_string(text: Optional[str]) -> str:
    """Normalize text by lowercasing, stripping, and condensing whitespace."""
    if not text or not isinstance(text, str):
        return ""
    # Remove punctuation characters for token matching
    cleaned = re.sub(r"[^\w\s]", " ", text.casefold())
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_meaningful_tokens(text: Optional[str], min_length: int = 2) -> Set[str]:
    """Extract word tokens from string excluding common stop words and single characters."""
    norm = _normalize_token_string(text)
    if not norm:
        return set()
    stopwords = {
        "and",
        "the",
        "of",
        "in",
        "at",
        "for",
        "a",
        "an",
        "to",
        "on",
        "with",
        # Generic organization words are not useful identity evidence.
        "university",
        "college",
        "school",
        "institute",
        "institution",
        "technology",
        "technologies",
        "company",
        "corporation",
        "corp",
        "inc",
        "limited",
        "ltd",
        "group",
    }
    tokens = set()
    for token in norm.split():
        if len(token) >= min_length and token not in stopwords:
            tokens.add(token)
    return tokens


def _calculate_name_similarity(name1: str, name2: str) -> float:
    """
    Calculate conservative name similarity using both token intersection and SequenceMatcher.
    Handles middle initials, name orders, and minor typographical variations.
    """
    norm1 = _normalize_token_string(name1)
    norm2 = _normalize_token_string(name2)

    if not norm1 or not norm2:
        return 0.0

    if norm1 == norm2:
        return 1.0

    tokens1 = [t for t in norm1.split() if t]
    tokens2 = [t for t in norm2.split() if t]

    if not tokens1 or not tokens2:
        return 0.0

    set1 = set(tokens1)
    set2 = set(tokens2)

    # Check subset (e.g. "Mohamad Barakat" in "Mohamad A. Barakat")
    if set1.issubset(set2) or set2.issubset(set1):
        return 0.95

    # Token pairwise similarity alignment
    scores1 = [max(difflib.SequenceMatcher(None, a, b).ratio() for b in tokens2) for a in tokens1]
    scores2 = [max(difflib.SequenceMatcher(None, b, a).ratio() for a in tokens1) for b in tokens2]
    token_sim = (sum(scores1) / len(scores1) + sum(scores2) / len(scores2)) / 2

    return token_sim


def evaluate_candidate_identity(
    existing_profile: Optional[StudentProfile],
    extracted: ExtractedCandidateProfile,
    db: Optional[Session] = None,
) -> IdentityComparisonResult:
    """
    Conservatively evaluate whether a newly extracted CV profile belongs to the same candidate.

    Rules:
    1. If no existing profile or blank name -> INSUFFICIENT_IDENTITY_EVIDENCE (proceed).
    2. If name similarity is strongly high (>= 0.80) -> SAME_CANDIDATE.
    3. A radically different name (< 0.5 similarity) always triggers POSSIBLE_MISMATCH;
       shared education or employer history cannot override a strong name contradiction.
    4. Moderate name similarity (0.5 to < 0.80) may be rescued by meaningful education
       or employer overlap.
    5. Moderate name similarity without independent background overlap triggers a
       confirmation-only POSSIBLE_MISMATCH rather than silent destructive replacement.
    6. Missing background history never suppresses a candidate identity warning.
    """
    if (
        not existing_profile
        or not existing_profile.full_name
        or not existing_profile.full_name.strip()
    ):
        return IdentityComparisonResult(
            verdict=IdentityVerdict.INSUFFICIENT_IDENTITY_EVIDENCE,
            reason="No existing candidate profile or name to compare against.",
            confidence=1.0,
            details={"is_new_candidate": True},
        )

    existing_name = existing_profile.full_name.strip()
    extracted_name = extracted.full_name.strip() if extracted.full_name else ""

    if not extracted_name:
        return IdentityComparisonResult(
            verdict=IdentityVerdict.INSUFFICIENT_IDENTITY_EVIDENCE,
            reason="Extracted profile contains no candidate name.",
            confidence=1.0,
            details={"extracted_name_empty": True},
        )

    name_sim = _calculate_name_similarity(existing_name, extracted_name)

    # Only a strongly similar name is sufficient by itself.
    # Moderate similarity must be supported by independent background evidence.
    if name_sim >= 0.80:
        return IdentityComparisonResult(
            verdict=IdentityVerdict.SAME_CANDIDATE,
            reason="Candidate names match or exhibit acceptable similarity.",
            confidence=float(name_sim),
            details={
                "existing_name": existing_name,
                "extracted_name": extracted_name,
                "name_similarity": round(name_sim, 3),
            },
        )

    # A radically different candidate name is sufficient identity evidence by itself.
    # Do this before background DB lookups so unavailable history can never bypass
    # a strong contradictory-name warning.
    if name_sim < 0.50:
        existing_name_tokens = _extract_meaningful_tokens(existing_name)
        extracted_name_tokens = _extract_meaningful_tokens(extracted_name)
        name_token_overlap = existing_name_tokens.intersection(extracted_name_tokens)

        return IdentityComparisonResult(
            verdict=IdentityVerdict.POSSIBLE_MISMATCH,
            reason=(
                "The candidate name in this CV is significantly different "
                "from your existing candidate profile."
            ),
            confidence=0.9,
            details={
                "existing_name": existing_name,
                "extracted_name": extracted_name,
                "name_similarity": round(name_sim, 3),
                "name_token_overlap": sorted(name_token_overlap),
            },
        )

    # Name similarity was not strong enough to establish identity alone.
    # Inspect independent background signals before deciding anything.
    existing_institutions: Set[str] = set()
    existing_companies: Set[str] = set()

    if db is not None and isinstance(existing_profile.id, UUID):
        try:
            edu_rows = MatchingDataRepository.get_education_for_student(db, existing_profile.id)
            for e in edu_rows:
                tokens = _extract_meaningful_tokens(e.institution, min_length=3)
                existing_institutions.update(tokens)

            exp_rows = MatchingDataRepository.get_experience_for_student(db, existing_profile.id)
            for ex in exp_rows:
                tokens = _extract_meaningful_tokens(ex.company, min_length=3)
                existing_companies.update(tokens)
        except Exception:
            # If DB lookup fails for any reason, do not block the user
            return IdentityComparisonResult(
                verdict=IdentityVerdict.INSUFFICIENT_IDENTITY_EVIDENCE,
                reason="Secondary history check unavailable; allowing replacement.",
                confidence=0.5,
                details={"db_lookup_failed": True},
            )

    extracted_institutions: Set[str] = set()
    for e in (extracted.education or []):
        if e.institution:
            extracted_institutions.update(_extract_meaningful_tokens(e.institution, min_length=3))

    extracted_companies: Set[str] = set()
    for ex in (extracted.experience or []):
        if ex.company:
            extracted_companies.update(_extract_meaningful_tokens(ex.company, min_length=3))

    has_existing_history = bool(existing_institutions or existing_companies)
    has_extracted_history = bool(extracted_institutions or extracted_companies)

    edu_overlap = existing_institutions.intersection(extracted_institutions)
    exp_overlap = existing_companies.intersection(extracted_companies)

    existing_name_tokens = _extract_meaningful_tokens(existing_name)
    extracted_name_tokens = _extract_meaningful_tokens(extracted_name)
    name_token_overlap = existing_name_tokens.intersection(extracted_name_tokens)

    # For moderate name variation, independent background overlap can connect
    # the two profiles and avoid an unnecessary confirmation prompt.
    if edu_overlap or exp_overlap:
        return IdentityComparisonResult(
            verdict=IdentityVerdict.SAME_CANDIDATE,
            reason="Background history overlap connects candidate to existing profile.",
            confidence=0.85,
            details={
                "name_similarity": round(name_sim, 3),
                "name_token_overlap": sorted(name_token_overlap),
                "edu_overlap": sorted(edu_overlap),
                "exp_overlap": sorted(exp_overlap),
            },
        )

    # The names are not similar enough to establish identity and there is no
    # independent background connection. Confirmation is safer than silently
    # replacing the existing candidate profile.
    return IdentityComparisonResult(
        verdict=IdentityVerdict.POSSIBLE_MISMATCH,
        reason=(
            "The identity information in this CV does not clearly match "
            "your existing candidate profile."
        ),
        confidence=0.75,
        details={
            "existing_name": existing_name,
            "extracted_name": extracted_name,
            "name_similarity": round(name_sim, 3),
            "name_token_overlap": sorted(name_token_overlap),
            "has_existing_history": has_existing_history,
            "has_extracted_history": has_extracted_history,
            "edu_overlap": sorted(edu_overlap),
            "exp_overlap": sorted(exp_overlap),
        },
    )
