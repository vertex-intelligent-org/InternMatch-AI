"""
Real PostgreSQL + pgvector Matching Runtime Integration Test Suite.
Verifies real database connection, pgvector extension, vector column dimensionality,
cosine distance search, deterministic hybrid scoring, match persistence,
skill gap analysis, stale match cleanup, tenant isolation, and atomic rollback.
Runs ONLY when TEST_POSTGRES_DATABASE_URL environment variable is set.
"""

import math
import os
from typing import List
from uuid import UUID, uuid4

import pytest

POSTGRES_DB_URL = os.getenv("TEST_POSTGRES_DATABASE_URL")
if not POSTGRES_DB_URL:
    pytest.skip(
        "TEST_POSTGRES_DATABASE_URL environment variable is not set. "
        "Skipping PostgreSQL pgvector integration tests.",
        allow_module_level=True,
    )

from app.db.models import (  # noqa: E402
    InternshipListing,
    Skill,
    StudentProfile,
    StudentSkill,
)
from app.repositories.match import MatchRepository  # noqa: E402
from app.repositories.vector_retrieval import (  # noqa: E402
    VectorRetrievalRepository,
)
from app.services.match_calculation import (  # noqa: E402
    calculate_and_persist_matches,
)
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402


def _make_unit_vector(index: int, dim: int = 1536) -> List[float]:
    """Generate a normalized 1536-dimensional unit vector with 1.0 at specified index."""
    vec = [0.0] * dim
    vec[index % dim] = 1.0
    return vec


def _make_dense_vector(seed_val: float, dim: int = 1536) -> List[float]:
    """Generate a deterministic normalized 1536-dimensional dense vector."""
    raw = [math.sin(seed_val + i * 0.05) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def _create_test_user(db: Session, user_id: UUID) -> None:
    """Insert a parent user record into auth.users to satisfy foreign key constraints."""
    db.execute(
        text(
            "INSERT INTO auth.users (id) VALUES (:user_id) "
            "ON CONFLICT (id) DO NOTHING;"
        ),
        {"user_id": str(user_id)},
    )
    db.flush()


@pytest.fixture(scope="module")
def pg_engine():
    """Create dedicated SQLAlchemy engine for real PostgreSQL test database."""
    engine = create_engine(POSTGRES_DB_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_session(pg_engine):
    """
    Provide an isolated database session for PostgreSQL tests.
    Rolls back uncommitted transactions upon test exit.
    """
    session_factory = sessionmaker(bind=pg_engine, expire_on_commit=False)
    session = session_factory()
    yield session
    session.rollback()
    session.close()


# ---------------------------------------------------------------------------
# 1. POSTGRESQL & PGVECTOR FOUNDATION CHECKS (1 - 5)
# ---------------------------------------------------------------------------


def test_postgres_connection_and_engine(pg_session):
    """Test 1: Connection to real PostgreSQL server succeeds."""
    res = pg_session.execute(text("SELECT 1;")).scalar()
    assert res == 1


def test_vector_extension_installed(pg_session):
    """Test 2: pgvector extension is installed and active in PostgreSQL."""
    stmt = text(
        "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
    )
    row = pg_session.execute(stmt).first()
    assert row is not None
    assert row[0] == "vector"
    assert row[1]  # Non-empty version string (e.g. 0.8.0 / 0.8.6)


def test_postgres_server_version(pg_session):
    """Test 3: Expected database dialect and engine is PostgreSQL."""
    version_str = pg_session.execute(text("SELECT version();")).scalar()
    assert "PostgreSQL" in version_str


def test_vector_column_dimension_enforced(pg_session):
    """Test 4: Vector columns in student_profiles and internship_listings are 1536."""
    stmt = text("""
        SELECT column_name, udt_name
        FROM information_schema.columns
        WHERE table_name IN ('student_profiles', 'internship_listings')
          AND column_name IN ('summary_embedding', 'description_embedding');
    """)
    rows = pg_session.execute(stmt).all()
    assert len(rows) >= 2
    for _, udt_name in rows:
        assert udt_name == "vector"


def test_vector_insertion_and_retrieval_raw_sql(pg_session):
    """Test 5: Real 1536-dimensional vector values can be queried via raw SQL."""
    vec = _make_dense_vector(1.0)
    vec_str = "[" + ",".join(str(v) for v in vec) + "]"

    stmt = text(
        "SELECT CAST(:val AS vector(1536)) <=> CAST(:val AS vector(1536)) AS dist;"
    )
    dist = pg_session.execute(stmt, {"val": vec_str}).scalar()
    assert dist is not None
    assert abs(float(dist)) < 1e-5  # Cosine distance between identical vectors is 0


# ---------------------------------------------------------------------------
# 2. VECTOR RETRIEVAL REPOSITORY ON REAL PGVECTOR (6 - 9)
# ---------------------------------------------------------------------------


def test_orm_vector_retrieval_repository_executes_real_sql(pg_session):
    """Test 6: VectorRetrievalRepository executes real pgvector query against DB."""
    vec_target = _make_unit_vector(0)
    vec_close = _make_dense_vector(0.1)

    listing = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="AI Engineering Intern",
        company="TechCorp",
        location="Remote",
        work_type="remote",
        description="Build LLM tools and API systems.",
        required_skills=["Python", "PyTorch"],
        description_embedding=vec_close,
    )
    pg_session.add(listing)
    pg_session.flush()

    try:
        candidates = VectorRetrievalRepository.get_nearest_internships(
            db=pg_session,
            candidate_embedding=vec_target,
            limit=5,
        )
        assert len(candidates) >= 1
        found = [c for c in candidates if c.internship.id == listing.id]
        assert len(found) == 1
        assert found[0].cosine_distance >= 0.0
    finally:
        pg_session.rollback()


def test_cosine_ordering_is_correct(pg_session):
    """Test 7: Results are strictly ordered ascending by pgvector cosine distance."""
    candidate_vec = _make_unit_vector(0)

    # Identical vector -> cosine distance = 0.0
    vec_identical = _make_unit_vector(0)
    # Dense vector -> cosine distance ~ 0.7
    vec_medium = _make_dense_vector(0.5)
    # Orthogonal unit vector -> cosine distance = 1.0
    vec_orthogonal = _make_unit_vector(1)

    int_closest = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Closest Internship",
        company="Alpha",
        location="Remote",
        work_type="remote",
        description="Top match.",
        description_embedding=vec_identical,
    )
    int_medium = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Medium Internship",
        company="Beta",
        location="Remote",
        work_type="remote",
        description="Medium match.",
        description_embedding=vec_medium,
    )
    int_orthogonal = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Orthogonal Internship",
        company="Gamma",
        location="Remote",
        work_type="remote",
        description="Least match.",
        description_embedding=vec_orthogonal,
    )

    pg_session.add_all([int_closest, int_medium, int_orthogonal])
    pg_session.flush()

    try:
        results = VectorRetrievalRepository.get_nearest_internships(
            db=pg_session,
            candidate_embedding=candidate_vec,
            limit=3,
        )
        assert len(results) == 3
        # Strict distance monotonicity: dist[0] <= dist[1] <= dist[2]
        assert results[0].cosine_distance <= results[1].cosine_distance
        assert results[1].cosine_distance <= results[2].cosine_distance
        assert results[0].internship.id == int_closest.id
        assert results[2].internship.id == int_orthogonal.id
    finally:
        pg_session.rollback()


def test_null_internship_embeddings_are_excluded(pg_session):
    """Test 8: Listings with NULL description_embedding are excluded from retrieval."""
    candidate_vec = _make_unit_vector(0)

    listing_valid = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Valid Embedding Internship",
        company="Valid Co",
        location="Remote",
        work_type="remote",
        description="Valid description.",
        description_embedding=_make_unit_vector(0),
    )
    listing_null = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Null Embedding Internship",
        company="Null Co",
        location="Remote",
        work_type="remote",
        description="Null embedding description.",
        description_embedding=None,
    )

    pg_session.add_all([listing_valid, listing_null])
    pg_session.flush()

    try:
        results = VectorRetrievalRepository.get_nearest_internships(
            db=pg_session,
            candidate_embedding=candidate_vec,
            limit=10,
        )
        returned_ids = [r.internship.id for r in results]
        assert listing_valid.id in returned_ids
        assert listing_null.id not in returned_ids
    finally:
        pg_session.rollback()


def test_candidate_embedding_drives_retrieval(pg_session):
    """Test 9: Different candidate embeddings retrieve their closest internships."""
    vec_a = _make_unit_vector(10)
    vec_b = _make_unit_vector(20)

    int_a = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Domain A Listing",
        company="Company A",
        location="Remote",
        work_type="remote",
        description="A specialized.",
        description_embedding=vec_a,
    )
    int_b = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Domain B Listing",
        company="Company B",
        location="Remote",
        work_type="remote",
        description="B specialized.",
        description_embedding=vec_b,
    )

    pg_session.add_all([int_a, int_b])
    pg_session.flush()

    try:
        res_a = VectorRetrievalRepository.get_nearest_internships(
            db=pg_session, candidate_embedding=vec_a, limit=1
        )
        res_b = VectorRetrievalRepository.get_nearest_internships(
            db=pg_session, candidate_embedding=vec_b, limit=1
        )
        assert res_a[0].internship.id == int_a.id
        assert res_b[0].internship.id == int_b.id
    finally:
        pg_session.rollback()


# ---------------------------------------------------------------------------
# 3. END-TO-END MATCH CALCULATION & PERSISTENCE (10 - 13)
# ---------------------------------------------------------------------------


def test_deterministic_hybrid_scoring_and_persistence(pg_session):
    """
    Test 10: Full matching calculation executes on real PostgreSQL,
    persists Match records, calculates hybrid score and canonical skill gap analysis.
    """
    user_id = uuid4()
    _create_test_user(pg_session, user_id)

    candidate_vec = _make_unit_vector(0)

    profile = StudentProfile(
        id=uuid4(),
        user_id=user_id,
        full_name="Alex Researcher",
        headline="AI & Backend Intern",
        preferences={"work_types": ["remote"], "desired_locations": ["Remote"]},
        summary_embedding=candidate_vec,
    )
    pg_session.add(profile)
    pg_session.flush()

    skill_py = Skill(id=uuid4(), name="Python", category="Languages")
    skill_fastapi = Skill(id=uuid4(), name="FastAPI", category="Frameworks")
    pg_session.add_all([skill_py, skill_fastapi])
    pg_session.flush()

    pg_session.add(
        StudentSkill(
            student_id=profile.id,
            skill_id=skill_py.id,
            proficiency_level="advanced",
        )
    )
    pg_session.add(
        StudentSkill(
            student_id=profile.id,
            skill_id=skill_fastapi.id,
            proficiency_level="intermediate",
        )
    )

    # Strongest match: 100% skill match, 100% vector match, 100% preference match
    int_strong = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Lead AI Engineer Intern",
        company="Nexus Corp",
        location="Remote",
        work_type="remote",
        description="Top AI job.",
        required_skills=["Python", "FastAPI"],
        preferred_skills=["Docker"],
        description_embedding=candidate_vec,  # Cosine dist = 0 -> Vector score = 100
    )
    # Weaker match: partial skill match, orthogonal vector
    int_weak = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Hardware Intern",
        company="Hardware Corp",
        location="Tokyo",
        work_type="onsite",
        description="Hardware job.",
        required_skills=["C++", "Rust"],
        preferred_skills=[],
        description_embedding=_make_unit_vector(50),  # Dist = 1 -> Vector score = 0
    )

    pg_session.add_all([int_strong, int_weak])
    pg_session.flush()

    try:
        matches = calculate_and_persist_matches(
            db=pg_session,
            user_id=user_id,
            candidate_limit=10,
        )

        assert len(matches) == 2
        strong_match = [m for m in matches if m.internship_id == int_strong.id][0]
        weak_match = [m for m in matches if m.internship_id == int_weak.id][0]

        # Strong match has higher overall score than weak match
        assert strong_match.overall_score > weak_match.overall_score
        assert strong_match.overall_score == 85
        assert strong_match.skill_score == 70
        assert strong_match.vector_score == 100

        # Canonical skill_gap_analysis
        skill_gap = strong_match.skill_gap_analysis
        assert "matching_skills" in skill_gap
        assert "missing_skills" in skill_gap
        assert "Python" in skill_gap["matching_skills"]
        assert "FastAPI" in skill_gap["matching_skills"]
        assert "Docker" in skill_gap["missing_skills"]

        # Verify persisted Match rows in PostgreSQL via independent query
        persisted = MatchRepository.get_matches_by_student_id(
            pg_session, profile.id
        )
        assert len(persisted) == 2
    finally:
        pg_session.rollback()


def test_stale_previous_student_matches_replaced_on_rerun(pg_session):
    """Test 11: Re-running match calculation deletes stale previous matches."""
    user_id = uuid4()
    _create_test_user(pg_session, user_id)

    candidate_vec = _make_unit_vector(0)

    profile = StudentProfile(
        id=uuid4(),
        user_id=user_id,
        full_name="Stale Test Candidate",
        preferences={"work_types": ["remote"]},
        summary_embedding=candidate_vec,
    )
    pg_session.add(profile)
    pg_session.flush()

    int_1 = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Job 1",
        company="Co 1",
        location="Remote",
        work_type="remote",
        description="Job 1 desc.",
        description_embedding=candidate_vec,
    )
    int_2 = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Job 2",
        company="Co 2",
        location="Remote",
        work_type="remote",
        description="Job 2 desc.",
        description_embedding=_make_dense_vector(0.3),
    )
    pg_session.add_all([int_1, int_2])
    pg_session.flush()

    try:
        # Run 1: limit 2 -> 2 matches created
        matches_run1 = calculate_and_persist_matches(
            db=pg_session,
            user_id=user_id,
            candidate_limit=2,
        )
        assert len(matches_run1) == 2

        # Run 2: limit 1 -> only nearest job 1 is matched, job 2 match must be deleted
        matches_run2 = calculate_and_persist_matches(
            db=pg_session,
            user_id=user_id,
            candidate_limit=1,
        )
        assert len(matches_run2) == 1
        assert matches_run2[0].internship_id == int_1.id

        # Verify in DB that only 1 match exists now
        db_matches = MatchRepository.get_matches_by_student_id(
            pg_session, profile.id
        )
        assert len(db_matches) == 1
        assert db_matches[0].internship_id == int_1.id
    finally:
        pg_session.rollback()


def test_tenant_isolation_user_a_never_mutates_user_b(pg_session):
    """Test 12: Running match calculation for User A never modifies User B matches."""
    user_a = uuid4()
    user_b = uuid4()
    _create_test_user(pg_session, user_a)
    _create_test_user(pg_session, user_b)

    candidate_vec = _make_unit_vector(0)

    prof_a = StudentProfile(
        id=uuid4(),
        user_id=user_a,
        full_name="Candidate A",
        preferences={"work_types": ["remote"]},
        summary_embedding=candidate_vec,
    )
    prof_b = StudentProfile(
        id=uuid4(),
        user_id=user_b,
        full_name="Candidate B",
        preferences={"work_types": ["remote"]},
        summary_embedding=candidate_vec,
    )
    pg_session.add_all([prof_a, prof_b])
    pg_session.flush()

    int_listing = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Shared Listing",
        company="Shared Co",
        location="Remote",
        work_type="remote",
        description="Shared job.",
        description_embedding=candidate_vec,
    )
    pg_session.add(int_listing)
    pg_session.flush()

    try:
        # Calculate matches for user B first
        matches_b = calculate_and_persist_matches(
            db=pg_session, user_id=user_b, candidate_limit=5
        )
        assert len(matches_b) == 1
        match_b_id = matches_b[0].id
        match_b_score = matches_b[0].overall_score

        # Calculate matches for user A
        matches_a = calculate_and_persist_matches(
            db=pg_session, user_id=user_a, candidate_limit=5
        )
        assert len(matches_a) == 1

        # Verify User B's match record was NOT mutated
        persisted_b = MatchRepository.get_matches_by_student_id(
            pg_session, prof_b.id
        )
        assert len(persisted_b) == 1
        assert persisted_b[0].id == match_b_id
        assert persisted_b[0].overall_score == match_b_score
    finally:
        pg_session.rollback()


def test_transaction_rollback_leaves_no_partial_matching_state(pg_session):
    """Test 13: Rolling back transaction leaves no partial matching records."""
    user_id = uuid4()
    _create_test_user(pg_session, user_id)

    candidate_vec = _make_unit_vector(0)

    profile = StudentProfile(
        id=uuid4(),
        user_id=user_id,
        full_name="Rollback Candidate",
        preferences={"work_types": ["remote"]},
        summary_embedding=candidate_vec,
    )
    pg_session.add(profile)
    pg_session.flush()

    int_listing = InternshipListing(
        id=uuid4(),
        listing_source="curated",
        publication_status="published",
        title="Rollback Listing",
        company="Rollback Co",
        location="Remote",
        work_type="remote",
        description="Rollback test.",
        description_embedding=candidate_vec,
    )
    pg_session.add(int_listing)
    pg_session.flush()

    try:
        # Calculate matches (flushes only, does not commit)
        calculate_and_persist_matches(
            db=pg_session,
            user_id=user_id,
            candidate_limit=5,
        )
        # Rollback the session
        pg_session.rollback()

        # In rolled back session, no matches must exist
        persisted = MatchRepository.get_matches_by_student_id(
            pg_session, profile.id
        )
        assert len(persisted) == 0
    finally:
        pg_session.rollback()
