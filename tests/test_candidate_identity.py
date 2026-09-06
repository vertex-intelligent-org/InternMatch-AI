"""
Unit Tests for Candidate Identity Guard Service.
Verifies conservative, multi-signal identity evaluation between existing profiles
and newly extracted CVs to avoid false positives and block cross-candidate replacements.
"""

from uuid import uuid4

from app.db.models import (
    EducationEntry,
    ExperienceEntry,
    StudentProfile,
)
from app.services.candidate_identity import (
    IdentityVerdict,
    evaluate_candidate_identity,
)
from app.services.cv_profile_extraction import (
    ExtractedCandidateProfile,
    ExtractedEducation,
    ExtractedExperience,
    ExtractedSkill,
)

from tests.db import TestingSessionLocal


def test_new_candidate_returns_insufficient_evidence():
    """Test 1: No prior profile returns INSUFFICIENT_IDENTITY_EVIDENCE allowing replacement."""
    extracted = ExtractedCandidateProfile(
        full_name="Alex Morgan",
        skills=[ExtractedSkill(name="Python")],
    )
    result = evaluate_candidate_identity(existing_profile=None, extracted=extracted)
    assert result.verdict == IdentityVerdict.INSUFFICIENT_IDENTITY_EVIDENCE


def test_exact_name_match_returns_same_candidate():
    """Test 2: Exact matching names return SAME_CANDIDATE."""
    existing = StudentProfile(
        id=uuid4(),
        user_id=uuid4(),
        full_name="Sarah Connor",
    )
    extracted = ExtractedCandidateProfile(
        full_name="Sarah Connor",
        skills=[ExtractedSkill(name="Security")],
    )
    result = evaluate_candidate_identity(existing_profile=existing, extracted=extracted)
    assert result.verdict == IdentityVerdict.SAME_CANDIDATE
    assert result.confidence == 1.0


def test_name_variation_middle_initial_returns_same_candidate():
    """Test 3: Name with middle initial or token subset returns SAME_CANDIDATE."""
    existing = StudentProfile(
        id=uuid4(),
        user_id=uuid4(),
        full_name="Mohamad Barakat",
    )
    extracted = ExtractedCandidateProfile(
        full_name="Mohamad A. Barakat",
        skills=[ExtractedSkill(name="Python")],
    )
    result = evaluate_candidate_identity(existing_profile=existing, extracted=extracted)
    assert result.verdict == IdentityVerdict.SAME_CANDIDATE
    assert result.confidence >= 0.9


def test_minor_name_typo_returns_same_candidate():
    """Test 4: Minor typo / transliteration in name returns SAME_CANDIDATE."""
    existing = StudentProfile(
        id=uuid4(),
        user_id=uuid4(),
        full_name="Mohammed Al-Mansoor",
    )
    extracted = ExtractedCandidateProfile(
        full_name="Mohamad Al Mansoor",
        skills=[ExtractedSkill(name="Python")],
    )
    result = evaluate_candidate_identity(existing_profile=existing, extracted=extracted)
    assert result.verdict == IdentityVerdict.SAME_CANDIDATE


def test_radically_different_name_without_background_history_requires_confirmation():
    """
    Test 5: A radically different candidate name must require confirmation even
    when structured education/experience history is unavailable.
    """
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        existing = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="John Doe",
        )
        db.add(existing)
        db.commit()

        # Extracted has a different name but no education or experience history either
        extracted = ExtractedCandidateProfile(
            full_name="Jonathan Miller",
            skills=[ExtractedSkill(name="Java")],
        )

        result = evaluate_candidate_identity(
            existing_profile=existing,
            extracted=extracted,
            db=db,
        )
        assert result.verdict == IdentityVerdict.POSSIBLE_MISMATCH
    finally:
        db.close()


def test_legacy_profile_with_different_candidate_name_requires_confirmation():
    """Legacy profiles must not be silently replaced by a clearly different person."""
    existing = StudentProfile(
        id=uuid4(),
        user_id=uuid4(),
        full_name="Legacy Candidate",
        cv_storage_path="legacy/cv.pdf",
    )
    extracted = ExtractedCandidateProfile(
        full_name="Completely Different Person",
        skills=[ExtractedSkill(name="Python")],
    )

    result = evaluate_candidate_identity(
        existing_profile=existing,
        extracted=extracted,
    )

    assert result.verdict == IdentityVerdict.POSSIBLE_MISMATCH
    assert result.details["existing_name"] == "Legacy Candidate"
    assert result.details["extracted_name"] == "Completely Different Person"


def test_different_name_with_education_overlap_returns_same_candidate():
    """Test 6: Name variations with matching university education return SAME_CANDIDATE."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        existing = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="S. Jenkins",
        )
        db.add(existing)
        db.flush()

        db.add(
            EducationEntry(
                student_id=existing.id,
                institution="Stanford University",
                degree="B.S. Computer Science",
            )
        )
        db.commit()

        extracted = ExtractedCandidateProfile(
            full_name="Samantha Jenkins",
            education=[
                ExtractedEducation(
                    institution="Stanford University",
                    degree="Computer Science",
                )
            ],
            skills=[ExtractedSkill(name="Python")],
        )

        result = evaluate_candidate_identity(
            existing_profile=existing,
            extracted=extracted,
            db=db,
        )
        assert result.verdict == IdentityVerdict.SAME_CANDIDATE
    finally:
        db.close()


def test_different_name_with_experience_overlap_returns_same_candidate():
    """Test 7: Name variations with matching employer company return SAME_CANDIDATE."""
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        existing = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Dan Miller",
        )
        db.add(existing)
        db.flush()

        db.add(
            ExperienceEntry(
                student_id=existing.id,
                company="Spotify Technology",
                role="Backend Intern",
            )
        )
        db.commit()

        extracted = ExtractedCandidateProfile(
            full_name="Daniel Miller",
            experience=[
                ExtractedExperience(
                    company="Spotify Technology",
                    role="Software Engineer",
                )
            ],
            skills=[ExtractedSkill(name="Go")],
        )

        result = evaluate_candidate_identity(
            existing_profile=existing,
            extracted=extracted,
            db=db,
        )
        assert result.verdict == IdentityVerdict.SAME_CANDIDATE
    finally:
        db.close()



def test_shared_surname_does_not_force_same_candidate():
    """
    Regression: sharing one surname must not be enough to immediately classify
    two otherwise different names as the same candidate.
    """
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        existing = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="John Smith",
        )
        db.add(existing)
        db.flush()

        db.add(
            EducationEntry(
                student_id=existing.id,
                institution="Massachusetts Institute of Technology",
                degree="B.S. Physics",
            )
        )
        db.commit()

        extracted = ExtractedCandidateProfile(
            full_name="Jane Smith",
            education=[
                ExtractedEducation(
                    institution="University of Oxford",
                    degree="B.A. Economics",
                )
            ],
            skills=[ExtractedSkill(name="Excel")],
        )

        result = evaluate_candidate_identity(
            existing_profile=existing,
            extracted=extracted,
            db=db,
        )

        assert result.verdict == IdentityVerdict.POSSIBLE_MISMATCH
    finally:
        db.close()


def test_radically_different_name_same_university_requires_confirmation():
    """A shared university must not override a radically different candidate name."""
    user_id = uuid4()
    db = TestingSessionLocal()

    try:
        existing = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="John Doe",
        )
        db.add(existing)
        db.flush()

        db.add(
            EducationEntry(
                student_id=existing.id,
                institution="Stanford University",
                degree="Computer Science",
            )
        )
        db.commit()

        extracted = ExtractedCandidateProfile(
            full_name="Alice Brown",
            education=[
                ExtractedEducation(
                    institution="Stanford University",
                    degree="Economics",
                )
            ],
            skills=[ExtractedSkill(name="Finance")],
        )

        result = evaluate_candidate_identity(
            existing_profile=existing,
            extracted=extracted,
            db=db,
        )

        assert result.verdict == IdentityVerdict.POSSIBLE_MISMATCH
    finally:
        db.close()


def test_radically_different_name_same_employer_requires_confirmation():
    """A shared employer must not override a radically different candidate name."""
    user_id = uuid4()
    db = TestingSessionLocal()

    try:
        existing = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="Michael Reed",
        )
        db.add(existing)
        db.flush()

        db.add(
            ExperienceEntry(
                student_id=existing.id,
                company="Google",
                role="Software Engineer",
            )
        )
        db.commit()

        extracted = ExtractedCandidateProfile(
            full_name="Sophia Turner",
            experience=[
                ExtractedExperience(
                    company="Google",
                    role="Product Manager",
                )
            ],
            skills=[ExtractedSkill(name="Product Strategy")],
        )

        result = evaluate_candidate_identity(
            existing_profile=existing,
            extracted=extracted,
            db=db,
        )

        assert result.verdict == IdentityVerdict.POSSIBLE_MISMATCH
    finally:
        db.close()


def test_generic_university_token_does_not_count_as_background_overlap():
    """
    Regression: generic organization words such as 'university' must not create
    false background overlap between unrelated institutions.
    """
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        existing = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="John Doe",
        )
        db.add(existing)
        db.flush()

        db.add(
            EducationEntry(
                student_id=existing.id,
                institution="Stanford University",
                degree="Computer Science",
            )
        )
        db.commit()

        extracted = ExtractedCandidateProfile(
            full_name="Alice Brown",
            education=[
                ExtractedEducation(
                    institution="Oxford University",
                    degree="Economics",
                )
            ],
            skills=[ExtractedSkill(name="Finance")],
        )

        result = evaluate_candidate_identity(
            existing_profile=existing,
            extracted=extracted,
            db=db,
        )

        assert result.verdict == IdentityVerdict.POSSIBLE_MISMATCH
    finally:
        db.close()


def test_strong_multi_signal_mismatch_triggers_possible_mismatch():
    """
    Test 8: Distinct name AND established history with ZERO background overlap
    triggers POSSIBLE_MISMATCH.
    """
    user_id = uuid4()
    db = TestingSessionLocal()
    try:
        existing = StudentProfile(
            id=uuid4(),
            user_id=user_id,
            full_name="John Doe",
        )
        db.add(existing)
        db.flush()

        db.add(
            EducationEntry(
                student_id=existing.id,
                institution="Massachusetts Institute of Technology",
                degree="B.S. Physics",
            )
        )
        db.add(
            ExperienceEntry(
                student_id=existing.id,
                company="Google DeepMind",
                role="Research Intern",
            )
        )
        db.commit()

        # Completely different candidate: Alice Smith, Oxford, McKinsey
        extracted = ExtractedCandidateProfile(
            full_name="Alice Smith",
            education=[
                ExtractedEducation(
                    institution="University of Oxford",
                    degree="B.A. Economics",
                )
            ],
            experience=[
                ExtractedExperience(
                    company="McKinsey & Company",
                    role="Business Analyst",
                )
            ],
            skills=[ExtractedSkill(name="Excel")],
        )

        result = evaluate_candidate_identity(
            existing_profile=existing,
            extracted=extracted,
            db=db,
        )
        assert result.verdict == IdentityVerdict.POSSIBLE_MISMATCH
        assert "existing_name" in result.details
        assert result.details["existing_name"] == "John Doe"
        assert result.details["extracted_name"] == "Alice Smith"
    finally:
        db.close()

def test_radically_different_name_skips_background_db_lookup(monkeypatch):
    """Radical name contradiction must not depend on background DB availability."""
    existing = StudentProfile(
        id=uuid4(),
        user_id=uuid4(),
        full_name="John Doe",
    )
    extracted = ExtractedCandidateProfile(
        full_name="Alice Brown",
        skills=[ExtractedSkill(name="Finance")],
    )

    def fail_lookup(*args, **kwargs):
        raise AssertionError(
            "Background DB lookup must not run for a radical name mismatch."
        )

    monkeypatch.setattr(
        "app.services.candidate_identity."
        "MatchingDataRepository.get_education_for_student",
        fail_lookup,
    )
    monkeypatch.setattr(
        "app.services.candidate_identity."
        "MatchingDataRepository.get_experience_for_student",
        fail_lookup,
    )

    result = evaluate_candidate_identity(
        existing_profile=existing,
        extracted=extracted,
        db=object(),
    )

    assert result.verdict == IdentityVerdict.POSSIBLE_MISMATCH
    assert result.details["existing_name"] == "John Doe"
    assert result.details["extracted_name"] == "Alice Brown"
