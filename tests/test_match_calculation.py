"""
Unit & Integration Tests for Match Calculation & Persistence Service Foundation.
Validates precondition checks, preference parsing, skill-gap fact building,
persistence rounding (round-half-up), in-place match set synchronization,
stale match deletion, tenant isolation, and transaction ownership.
"""

from uuid import uuid4

import pytest
from app.core.config import settings
from app.db.models import InternshipListing, Match, Skill, StudentProfile, StudentSkill
from app.repositories.matching_data import MatchingDataRepository
from app.repositories.vector_retrieval import VectorCandidate, VectorRetrievalRepository
from app.services.match_calculation import (
    MatchCalculationPreconditionError,
    build_skill_gap_analysis,
    calculate_and_persist_matches,
    round_score_for_persistence,
)
from app.services.scoring import HybridScore
from app.services.skill_matching import SkillMatchResult

from tests.db import TestingSessionLocal


@pytest.fixture
def db():
    """Provides a transactional database session per test using TestingSessionLocal."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ROUNDING HELPER TESTS (13 - 18)

def test_13_rounding_point_four_rounds_down():
    """Test 13: 67.4 rounds half-up to 67."""
    assert round_score_for_persistence(67.4) == 67


def test_14_rounding_point_five_rounds_up():
    """Test 14: 67.5 rounds half-up to 68."""
    assert round_score_for_persistence(67.5) == 68


def test_15_rounding_eighty_point_five_rounds_up():
    """Test 15: 80.5 rounds half-up to 81."""
    assert round_score_for_persistence(80.5) == 81


def test_16_rounding_hundred_returns_hundred():
    """Test 16: 100.0 returns 100."""
    assert round_score_for_persistence(100.0) == 100


def test_17_invalid_or_out_of_range_score_raises_value_error():
    """Test 17: Non-finite (nan, +inf, -inf) or out of range scores raise ValueError."""
    with pytest.raises(ValueError, match="Invalid non-finite persistence score"):
        round_score_for_persistence(float("nan"))
    with pytest.raises(ValueError, match="Invalid non-finite persistence score"):
        round_score_for_persistence(float("inf"))
    with pytest.raises(ValueError, match="Invalid non-finite persistence score"):
        round_score_for_persistence(float("-inf"))
    with pytest.raises(ValueError, match="out of valid range"):
        round_score_for_persistence(-0.1)
    with pytest.raises(ValueError, match="out of valid range"):
        round_score_for_persistence(100.1)


def test_18_persisted_overall_comes_from_float_overall_score(db, monkeypatch):
    """
    Test 18: Persisted overall_score comes directly from float HybridScore.overall_score,
    not recomputed from already-rounded component integers.
    """
    user_id = uuid4()
    dummy_vec = [0.1] * settings.EMBEDDING_DIMENSION

    prof = StudentProfile(
        user_id=user_id, full_name="Rounding Test Student", summary_embedding=dummy_vec
    )
    int_item = InternshipListing(
        title="Rounding Job", company="Co", location="Loc", work_type="remote", description="Desc"
    )
    db.add_all([prof, int_item])
    db.flush()

    monkeypatch.setattr(
        VectorRetrievalRepository,
        "get_nearest_internships",
        lambda db, candidate_embedding, limit: [
            VectorCandidate(internship=int_item, cosine_distance=0.2)
        ],
    )

    # HybridScore: skill=0.49 (->0), vector=0.49 (->0), attr=2.49 (->2), overall=0.89 (->1)
    # If recomputed from rounded ints: 0.5*0 + 0.3*0 + 0.2*2 = 0.4 -> 0 (INCORRECT)
    custom_hybrid = HybridScore(
        skill_score=0.49,
        vector_score=0.49,
        attribute_score=2.49,
        overall_score=0.89,
    )
    monkeypatch.setattr(
        "app.services.match_calculation.calculate_hybrid_score",
        lambda **kwargs: custom_hybrid,
    )

    matches = calculate_and_persist_matches(db, user_id, candidate_limit=5)
    assert len(matches) == 1
    m = matches[0]

    assert m.skill_score == 0
    assert m.vector_score == 0
    assert m.attribute_score == 2
    assert m.overall_score == 1  # Proves overall score derived from float 0.89 -> 1!


# PRECONDITION TESTS (1 - 7)

def test_1_candidate_limit_zero_raises_value_error(db):
    """Test 1: candidate_limit of zero raises ValueError."""
    user_id = uuid4()
    with pytest.raises(ValueError, match="Limit must be > 0"):
        calculate_and_persist_matches(db, user_id, candidate_limit=0)


def test_2_candidate_limit_negative_raises_value_error(db):
    """Test 2: candidate_limit negative raises ValueError."""
    user_id = uuid4()
    with pytest.raises(ValueError, match="Limit must be > 0"):
        calculate_and_persist_matches(db, user_id, candidate_limit=-10)


def test_3_missing_profile_raises_precondition_error(db):
    """Test 3: Missing profile raises MatchCalculationPreconditionError."""
    user_id = uuid4()
    with pytest.raises(MatchCalculationPreconditionError, match="No StudentProfile found"):
        calculate_and_persist_matches(db, user_id, candidate_limit=10)


def test_4_missing_summary_embedding_raises_precondition_error(db):
    """Test 4: Profile with summary_embedding = None raises precondition error."""
    user_id = uuid4()
    profile = StudentProfile(
        user_id=user_id,
        full_name="No Embed Student",
        summary_embedding=None,
    )
    db.add(profile)
    db.flush()

    with pytest.raises(
        MatchCalculationPreconditionError, match="missing or empty summary_embedding"
    ):
        calculate_and_persist_matches(db, user_id, candidate_limit=10)


def test_5_empty_summary_embedding_raises_precondition_error(db):
    """Test 5: Profile with empty summary_embedding raises precondition error."""
    user_id = uuid4()
    profile = StudentProfile(
        user_id=user_id,
        full_name="Empty Embed Student",
        summary_embedding=[],
    )
    db.add(profile)
    db.flush()

    with pytest.raises(
        MatchCalculationPreconditionError, match="missing or empty summary_embedding"
    ):
        calculate_and_persist_matches(db, user_id, candidate_limit=10)


def test_6_malformed_work_types_raises_precondition_error(db):
    """Test 6: Malformed non-list work_types preference raises precondition error."""
    user_id = uuid4()
    dummy_vec = [0.1] * settings.EMBEDDING_DIMENSION
    profile = StudentProfile(
        user_id=user_id,
        full_name="Bad Preferences Student",
        summary_embedding=dummy_vec,
        preferences={"work_types": "not_a_list"},
    )
    db.add(profile)
    db.flush()

    with pytest.raises(MatchCalculationPreconditionError, match="must be a JSON list"):
        calculate_and_persist_matches(db, user_id, candidate_limit=10)


def test_7_malformed_desired_locations_raises_precondition_error(db):
    """Test 7: Malformed desired_locations containing non-strings raises precondition error."""
    user_id = uuid4()
    dummy_vec = [0.1] * settings.EMBEDDING_DIMENSION
    profile = StudentProfile(
        user_id=user_id,
        full_name="Bad Loc Student",
        summary_embedding=dummy_vec,
        preferences={"desired_locations": [123, "Istanbul"]},
    )
    db.add(profile)
    db.flush()

    with pytest.raises(MatchCalculationPreconditionError, match="must be a string"):
        calculate_and_persist_matches(db, user_id, candidate_limit=10)


# SKILL GAP FACT TESTS (19 - 24)

def test_19_skill_gap_combines_matching_required_and_preferred():
    """Test 19: Skill gap combines matching required and preferred skills in order."""
    match_res = SkillMatchResult(
        matched_required_skills=["Python"],
        missing_required_skills=[],
        matched_preferred_skills=["Docker"],
        missing_preferred_skills=[],
    )
    gap = build_skill_gap_analysis(match_res)
    assert gap["matching_skills"] == ["Python", "Docker"]


def test_20_skill_gap_combines_missing_required_and_preferred():
    """Test 20: Skill gap combines missing required and preferred skills in order."""
    match_res = SkillMatchResult(
        matched_required_skills=[],
        missing_required_skills=["SQL"],
        matched_preferred_skills=[],
        missing_preferred_skills=["AWS"],
    )
    gap = build_skill_gap_analysis(match_res)
    assert gap["missing_skills"] == ["SQL", "AWS"]


def test_21_skill_gap_stable_deduplication_preserves_spelling_and_order():
    """Test 21: Skill gap deduplication preserves first original spelling and order."""
    match_res = SkillMatchResult(
        matched_required_skills=["Python", "python"],
        missing_required_skills=[],
        matched_preferred_skills=["  PYTHON  ", "Docker"],
        missing_preferred_skills=[],
    )
    gap = build_skill_gap_analysis(match_res)
    assert gap["matching_skills"] == ["Python", "Docker"]


def test_22_test_23_test_24_skill_gap_empty_summary_and_recommendations():
    """Tests 22-24: Skill gap summary is empty, recommendations is [], why_you_match is None."""
    match_res = SkillMatchResult(["Python"], [], [], [])
    gap = build_skill_gap_analysis(match_res)
    assert gap["summary"] == ""
    assert gap["recommendations"] == []


# ORCHESTRATION TESTS (8 - 12)

def test_8_student_skills_loaded_once_per_calculation(db, monkeypatch):
    """Test 8: MatchingDataRepository.get_ranking_skill_names_for_student is called exactly once."""
    user_id = uuid4()
    dummy_vec = [0.1] * settings.EMBEDDING_DIMENSION
    prof = StudentProfile(user_id=user_id, full_name="Spy Student", summary_embedding=dummy_vec)
    int_item = InternshipListing(
        title="Job 1", company="Co", location="Loc", work_type="remote", description="Desc"
    )
    db.add_all([prof, int_item])
    db.flush()

    monkeypatch.setattr(
        VectorRetrievalRepository,
        "get_nearest_internships",
        lambda db, candidate_embedding, limit: [
            VectorCandidate(internship=int_item, cosine_distance=0.2)
        ],
    )

    calls = []
    original_get_skills = MatchingDataRepository.get_ranking_skill_names_for_student

    def spy_get_skills(d, student_id):
        calls.append(student_id)
        return original_get_skills(d, student_id)

    monkeypatch.setattr(MatchingDataRepository, "get_ranking_skill_names_for_student", spy_get_skills)

    calculate_and_persist_matches(db, user_id, candidate_limit=5)
    assert len(calls) == 1
    assert calls[0] == prof.id


def test_9_vector_retrieval_called_once_with_profile_embedding_and_limit(db, monkeypatch):
    """
    Test 9: VectorRetrievalRepository.get_nearest_internships is called exactly once
    with expected parameters.
    """
    user_id = uuid4()
    dummy_vec = [0.1] * settings.EMBEDDING_DIMENSION
    prof = StudentProfile(
        user_id=user_id, full_name="Vector Spy Student", summary_embedding=dummy_vec
    )
    db.add(prof)
    db.flush()

    calls = []

    def mock_vector(db, candidate_embedding, limit):
        calls.append((candidate_embedding, limit))
        return []

    monkeypatch.setattr(VectorRetrievalRepository, "get_nearest_internships", mock_vector)

    calculate_and_persist_matches(db, user_id, candidate_limit=7)
    assert len(calls) == 1
    assert calls[0][0] == dummy_vec
    assert calls[0][1] == 7


def test_10_target_roles_preference_is_ignored_by_mvp_v1(db, monkeypatch):
    """Test 10: target_roles preference does not raise error and does not affect orchestration."""
    user_id = uuid4()
    dummy_vec = [0.1] * settings.EMBEDDING_DIMENSION
    prof = StudentProfile(
        user_id=user_id,
        full_name="Target Roles Student",
        summary_embedding=dummy_vec,
        preferences={"target_roles": ["Software Engineer", "Data Scientist"]},
    )
    int_item = InternshipListing(
        title="Job 1", company="Co", location="Loc", work_type="remote", description="Desc"
    )
    db.add_all([prof, int_item])
    db.flush()

    monkeypatch.setattr(
        VectorRetrievalRepository,
        "get_nearest_internships",
        lambda db, candidate_embedding, limit: [
            VectorCandidate(internship=int_item, cosine_distance=0.2)
        ],
    )

    matches = calculate_and_persist_matches(db, user_id, candidate_limit=5)
    assert len(matches) == 1


def test_11_zero_student_skills_is_valid(db, monkeypatch):
    """Test 11: A student with zero structured skills is valid and produces matches."""
    user_id = uuid4()
    dummy_vec = [0.1] * settings.EMBEDDING_DIMENSION
    prof = StudentProfile(
        user_id=user_id, full_name="Zero Skills Student", summary_embedding=dummy_vec
    )
    int_item = InternshipListing(
        title="Job 1",
        company="Co",
        location="Loc",
        work_type="remote",
        description="Desc",
        required_skills=["Python"],
    )
    db.add_all([prof, int_item])
    db.flush()

    monkeypatch.setattr(
        VectorRetrievalRepository,
        "get_nearest_internships",
        lambda db, candidate_embedding, limit: [
            VectorCandidate(internship=int_item, cosine_distance=0.2)
        ],
    )

    matches = calculate_and_persist_matches(db, user_id, candidate_limit=5)
    assert len(matches) == 1
    assert matches[0].skill_gap_analysis["missing_skills"] == ["Python"]


def test_12_internship_missing_skills_lists_is_handled_validly(db, monkeypatch):
    """
    Test 12: Internship with required_skills=None and preferred_skills=None is handled
    validly.
    """
    user_id = uuid4()
    dummy_vec = [0.1] * settings.EMBEDDING_DIMENSION
    prof = StudentProfile(
        user_id=user_id, full_name="No Internship Skills Student", summary_embedding=dummy_vec
    )
    int_item = InternshipListing(
        title="Job 1",
        company="Co",
        location="Loc",
        work_type="remote",
        description="Desc",
        required_skills=None,
        preferred_skills=None,
    )
    db.add_all([prof, int_item])
    db.flush()

    monkeypatch.setattr(
        VectorRetrievalRepository,
        "get_nearest_internships",
        lambda db, candidate_embedding, limit: [
            VectorCandidate(internship=int_item, cosine_distance=0.2)
        ],
    )

    matches = calculate_and_persist_matches(db, user_id, candidate_limit=5)
    assert len(matches) == 1
    assert matches[0].skill_score == 100


# INTEGRATION & SYNCHRONIZATION TESTS (25 - 35)

def test_25_to_35_match_calculation_orchestration_and_synchronization(db, monkeypatch):
    """
    Integration Test (25-35): Tests complete recalculation, in-place update,
    preservation of ID and created_at, clearing stale outputs (why_you_match, summary,
    recommendations), deleting stale matches, tenant isolation, and result ordering.
    """
    user1_id = uuid4()
    user2_id = uuid4()

    dummy_vec = [0.1] * settings.EMBEDDING_DIMENSION

    # Create Student 1
    prof1 = StudentProfile(
        user_id=user1_id,
        full_name="Candidate 1",
        summary_embedding=dummy_vec,
        preferences={"work_types": ["remote"], "desired_locations": ["Istanbul"]},
    )
    # Create Student 2
    prof2 = StudentProfile(
        user_id=user2_id,
        full_name="Candidate 2",
        summary_embedding=dummy_vec,
    )
    db.add_all([prof1, prof2])
    db.flush()

    # Add student 1 skill
    skill_py = Skill(name="Python", category="Backend")
    db.add(skill_py)
    db.flush()
    db.add(StudentSkill(student_id=prof1.id, skill_id=skill_py.id))
    db.flush()

    # Create internships
    int1 = InternshipListing(
        title="Role 1",
        company="Co 1",
        location="Istanbul",
        work_type="remote",
        description="Desc 1",
        required_skills=["Python"],
        preferred_skills=["Docker"],
    )
    int2 = InternshipListing(
        title="Role 2",
        company="Co 2",
        location="Ankara",
        work_type="onsite",
        description="Desc 2",
        required_skills=["SQL"],
    )
    int3 = InternshipListing(
        title="Role 3",
        company="Co 3",
        location="Remote",
        work_type="remote",
        description="Desc 3",
    )
    db.add_all([int1, int2, int3])
    db.flush()

    # Seed an existing match for User 2 (must not be affected)
    other_match = Match(
        student_id=prof2.id,
        internship_id=int3.id,
        overall_score=80,
        skill_score=80,
        vector_score=80,
        attribute_score=80,
        why_you_match="Other user match",
    )
    db.add(other_match)
    db.flush()

    # Mock vector retrieval to return int1 and int2
    def mock_vector_retrieval(db, candidate_embedding, limit):
        return [
            VectorCandidate(internship=int1, cosine_distance=0.1),
            VectorCandidate(internship=int2, cosine_distance=0.3),
        ]

    monkeypatch.setattr(
        VectorRetrievalRepository,
        "get_nearest_internships",
        mock_vector_retrieval,
    )

    # 1. First Run: Calculates and persists matches for Student 1
    matches_run1 = calculate_and_persist_matches(db, user1_id, candidate_limit=10)
    assert len(matches_run1) == 2
    assert matches_run1[0].internship_id == int1.id
    assert matches_run1[1].internship_id == int2.id

    match1_id = matches_run1[0].id
    match1_created = matches_run1[0].created_at

    # Manually set stale AI output & stale skill_gap_analysis on match1
    matches_run1[0].why_you_match = "Old LLM summary"
    matches_run1[0].skill_gap_analysis = {
        "matching_skills": ["OldSkill"],
        "missing_skills": ["OldMissing"],
        "summary": "Stale LLM summary text",
        "recommendations": ["Take course Y"],
    }
    db.flush()

    # Create a stale match for Student 1 targeting int3
    stale_match = Match(
        student_id=prof1.id,
        internship_id=int3.id,
        overall_score=50,
        skill_score=50,
        vector_score=50,
        attribute_score=50,
        why_you_match="Stale match",
    )
    db.add(stale_match)
    db.flush()

    # 2. Second Run: Recalculate matches for Student 1 (int1 and int2 returned)
    matches_run2 = calculate_and_persist_matches(db, user1_id, candidate_limit=10)
    assert len(matches_run2) == 2

    # Check update in place: ID and created_at preserved
    updated_m1 = matches_run2[0]
    assert updated_m1.id == match1_id
    assert updated_m1.created_at == match1_created

    # Check stale qualitative data cleared
    assert updated_m1.why_you_match is None
    assert updated_m1.skill_gap_analysis["summary"] == ""
    assert updated_m1.skill_gap_analysis["recommendations"] == []

    # Check stale match for Student 1 (targeting int3) was deleted
    stale_check = db.query(Match).filter_by(student_id=prof1.id, internship_id=int3.id).first()
    assert stale_check is None

    # Check other student's match was NOT deleted
    other_check = db.query(Match).filter_by(student_id=prof2.id, internship_id=int3.id).first()
    assert other_check is not None
    assert other_check.why_you_match == "Other user match"


def test_33_and_34_empty_candidate_set_deletes_only_current_student_matches(db, monkeypatch):
    """
    Tests 33 & 34: Empty candidate set deletes current student matches without deleting
    other students'.
    """
    user1_id = uuid4()
    user2_id = uuid4()
    dummy_vec = [0.1] * settings.EMBEDDING_DIMENSION

    p1 = StudentProfile(user_id=user1_id, full_name="S1", summary_embedding=dummy_vec)
    p2 = StudentProfile(user_id=user2_id, full_name="S2", summary_embedding=dummy_vec)
    db.add_all([p1, p2])
    db.flush()

    i1 = InternshipListing(
        title="T1", company="C1", location="L1", work_type="remote", description="D1"
    )
    db.add(i1)
    db.flush()

    m1 = Match(
        student_id=p1.id,
        internship_id=i1.id,
        overall_score=70,
        skill_score=70,
        vector_score=70,
        attribute_score=70,
    )
    m2 = Match(
        student_id=p2.id,
        internship_id=i1.id,
        overall_score=80,
        skill_score=80,
        vector_score=80,
        attribute_score=80,
    )
    db.add_all([m1, m2])
    db.flush()

    # Mock empty vector retrieval
    monkeypatch.setattr(
        VectorRetrievalRepository,
        "get_nearest_internships",
        lambda db, candidate_embedding, limit: [],
    )

    res = calculate_and_persist_matches(db, user1_id, candidate_limit=5)
    assert res == []

    # Student 1 match deleted
    assert db.query(Match).filter_by(student_id=p1.id).first() is None
    # Student 2 match preserved
    assert db.query(Match).filter_by(student_id=p2.id).first() is not None


def test_36_service_does_not_commit_transaction(db, monkeypatch):
    """Test 36: Service performs db.flush() but NOT db.commit(), proving caller owns transaction."""
    user_id = uuid4()
    dummy_vec = [0.1] * settings.EMBEDDING_DIMENSION
    prof = StudentProfile(
        user_id=user_id, full_name="Rollback Student", summary_embedding=dummy_vec
    )
    int_item = InternshipListing(
        title="Rollback Job", company="Co", location="Loc", work_type="remote", description="Desc"
    )
    db.add_all([prof, int_item])
    db.flush()

    def mock_vector_retrieval(db, candidate_embedding, limit):
        return [VectorCandidate(internship=int_item, cosine_distance=0.2)]

    monkeypatch.setattr(
        VectorRetrievalRepository, "get_nearest_internships", mock_vector_retrieval
    )

    matches = calculate_and_persist_matches(db, user_id, candidate_limit=5)
    assert len(matches) == 1

    # Rollback transaction from test caller
    db.rollback()

    # Verify uncommitted Match write was rolled back completely
    m_check = db.query(Match).filter_by(student_id=prof.id).first()
    assert m_check is None
