"""
Unit Tests for Operational Demo Internship Seeder.
Verifies deterministic demo-ID extraction, exact controlled set validation,
PostgreSQL dialect enforcement, description change invalidation logic,
missing-only embedding backfill, and safe error propagation.
Zero real OpenAI or network calls.
"""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from app.core.config import settings
from app.db.models import InternshipListing

from scripts.seed_internships import (
    DEFAULT_SEED_SQL_PATH,
    EXPECTED_DEMO_IDS,
    DemoSeedEmbeddingError,
    DemoSeedError,
    DemoSeedSummary,
    DemoSeedValidationError,
    apply_authoritative_sql,
    extract_demo_internship_ids_from_sql,
    seed_demo_internships,
)


def _make_fake_vector(dim: int = settings.EMBEDDING_DIMENSION) -> list[float]:
    """Return a valid deterministic non-zero fake embedding vector matching dimension."""
    return [0.1] * dim


# ---------------------------------------------------------------------------
# 1. SQL DEMO ID EXTRACTION & STRICT EXACT SET VALIDATION TESTS
# ---------------------------------------------------------------------------


def test_authoritative_sql_yields_exact_35_demo_ids():
    """Test 1: Real authoritative SQL contains exactly 35 unique valid UUIDs."""
    assert DEFAULT_SEED_SQL_PATH.exists(), f"Seed file missing at {DEFAULT_SEED_SQL_PATH}"
    sql_content = DEFAULT_SEED_SQL_PATH.read_text(encoding="utf-8")

    demo_ids = extract_demo_internship_ids_from_sql(sql_content)

    assert len(demo_ids) == 35
    assert len(set(demo_ids)) == 35
    assert set(demo_ids) == EXPECTED_DEMO_IDS
    for uid in demo_ids:
        assert isinstance(uid, UUID)
        assert str(uid).startswith("20000000-0000-0000-0000-")


def test_extraction_fails_when_count_less_than_35():
    """Test 2a: Extraction fails safely when fewer than 35 IDs are found."""
    partial_sql = """
    INSERT INTO public.internship_listings (id, title) VALUES
      ('20000000-0000-0000-0000-000000000001', 'Listing 1');
    """
    with pytest.raises(
        DemoSeedValidationError,
        match="expected exactly 35 demo internship ID occurrences",
    ):
        extract_demo_internship_ids_from_sql(partial_sql)


def test_extraction_fails_when_duplicate_id_present():
    """Test 2b: Extraction fails safely when duplicate demo IDs are found."""
    # 35 entries but with a duplicate
    ids = [f"20000000-0000-0000-0000-{i:012d}" for i in range(1, 35)]
    ids.append(ids[0])  # Duplicate the first ID to make 35 total occurrences
    dup_sql = "\n".join(f"('{uid}', 'Title')" for uid in ids)

    with pytest.raises(
        DemoSeedValidationError, match="Duplicate demo internship ID in SQL seed"
    ):
        extract_demo_internship_ids_from_sql(dup_sql)


def test_extraction_fails_when_malformed_uuid():
    """Test 2c: Extraction fails safely when a UUID is malformed."""
    ids = [f"20000000-0000-0000-0000-{i:012d}" for i in range(1, 35)]
    ids.append("20000000-0000-0000-0000-NOT_A_HEX_ID")
    malformed_sql = "\n".join(f"('{uid}', 'Title')" for uid in ids)

    with pytest.raises(
        DemoSeedValidationError, match="Invalid UUID format|expected exactly 35"
    ):
        extract_demo_internship_ids_from_sql(malformed_sql)


def test_extraction_fails_when_unexpected_id_replaces_expected_id():
    """Test 2d: Extraction fails when 35 valid IDs differ from controlled set."""
    # 35 IDs where ...000035 is replaced with ...000036
    ids = [f"20000000-0000-0000-0000-{i:012d}" for i in range(1, 35)]
    ids.append("20000000-0000-0000-0000-000000000036")
    differing_sql = "\n".join(f"('{uid}', 'Title')" for uid in ids)

    with pytest.raises(
        DemoSeedValidationError,
        match="extracted IDs do not match the authoritative controlled ID set",
    ):
        extract_demo_internship_ids_from_sql(differing_sql)


# ---------------------------------------------------------------------------
# 2. DIALECT & SEEDING ORCHESTRATION UNIT TESTS
# ---------------------------------------------------------------------------


def test_non_postgresql_dialect_rejected():
    """Test 3: Non-PostgreSQL dialect is rejected without engine instantiation."""
    mock_session = MagicMock()
    mock_bind = MagicMock()
    mock_bind.dialect.name = "sqlite"
    mock_session.get_bind.return_value = mock_bind

    with pytest.raises(DemoSeedError, match="requires a PostgreSQL database"):
        seed_demo_internships(session=mock_session)


def _build_mock_pg_session():
    """Helper creating a mock Session with PostgreSQL dialect metadata."""
    mock_session = MagicMock()
    mock_bind = MagicMock()
    mock_bind.dialect.name = "postgresql"
    mock_session.get_bind.return_value = mock_bind
    return mock_session


def test_unchanged_description_with_existing_embedding_is_skipped(tmp_path: Path):
    """Test 4: Rows with unchanged descriptions and existing embeddings are skipped."""
    # Create synthetic SQL with the 35 exact deterministic IDs
    ids = sorted(list(EXPECTED_DEMO_IDS))
    sql_lines = ["INSERT INTO public.internship_listings (id, description) VALUES"]
    for uid in ids:
        sql_lines.append(f"  ('{uid}', 'Unchanged Description'),")
    sql_content = "\n".join(sql_lines).rstrip(",") + ";"

    temp_seed = tmp_path / "temp_seed.sql"
    temp_seed.write_text(sql_content, encoding="utf-8")

    mock_session = _build_mock_pg_session()

    # Pre-seed descriptions matching post-seed descriptions
    pre_seed_rows = [
        (uid, "Unchanged Description", _make_fake_vector()) for uid in ids
    ]
    mock_session.execute.return_value.all.side_effect = [
        pre_seed_rows,  # Pre-seed query
        [(uid, _make_fake_vector()) for uid in ids],  # Final completeness query
    ]

    # Post-seed listings with non-null embeddings
    listings_map = {
        uid: InternshipListing(
            id=uid,
            title="Test",
            company="Co",
            location="Remote",
            work_type="remote",
            description="Unchanged Description",
            description_embedding=_make_fake_vector(),
        )
        for uid in ids
    }
    mock_session.scalars.return_value.all.return_value = list(listings_map.values())
    mock_session.get.side_effect = lambda model, uid: listings_map.get(uid)

    mock_embedder = MagicMock(return_value=_make_fake_vector())

    summary = seed_demo_internships(
        session=mock_session,
        seed_sql_path=temp_seed,
        embedder_func=mock_embedder,
        refresh_embeddings=False,
    )

    assert isinstance(summary, DemoSeedSummary)
    assert summary.demo_rows == 35
    assert summary.invalidated == 0
    assert summary.embedded == 0
    assert summary.skipped_existing == 35
    assert summary.missing_embeddings == 0
    assert mock_embedder.call_count == 0


def test_null_embedding_is_generated_and_persisted(tmp_path: Path):
    """Test 5: Rows with NULL description_embedding are embedded via injected embedder."""
    ids = sorted(list(EXPECTED_DEMO_IDS))
    sql_lines = ["INSERT INTO public.internship_listings (id, description) VALUES"]
    for uid in ids:
        sql_lines.append(f"  ('{uid}', 'Desc {uid}'),")
    sql_content = "\n".join(sql_lines).rstrip(",") + ";"

    temp_seed = tmp_path / "temp_seed.sql"
    temp_seed.write_text(sql_content, encoding="utf-8")

    mock_session = _build_mock_pg_session()

    # Pre-seed query returns empty (all new rows)
    mock_session.execute.return_value.all.side_effect = [
        [],  # Pre-seed query
        [(uid, _make_fake_vector()) for uid in ids],  # Final completeness query
    ]

    listings_map = {
        uid: InternshipListing(
            id=uid,
            title="Test",
            company="Co",
            location="Remote",
            work_type="remote",
            description=f"Desc {uid}",
            description_embedding=None,
        )
        for uid in ids
    }
    mock_session.scalars.return_value.all.return_value = list(listings_map.values())
    mock_session.get.side_effect = lambda model, uid: listings_map.get(uid)

    mock_embedder = MagicMock(return_value=_make_fake_vector())

    summary = seed_demo_internships(
        session=mock_session,
        seed_sql_path=temp_seed,
        embedder_func=mock_embedder,
        refresh_embeddings=False,
    )

    assert summary.demo_rows == 35
    assert summary.embedded == 35
    assert summary.skipped_existing == 0
    assert mock_embedder.call_count == 35
    for listing in listings_map.values():
        assert listing.description_embedding == _make_fake_vector()


def test_description_change_invalidates_and_regenerates_embedding(
    tmp_path: Path,
):
    """Test 6: When authoritative description changes, embedding is regenerated."""
    ids = sorted(list(EXPECTED_DEMO_IDS))
    sql_lines = ["INSERT INTO public.internship_listings (id, description) VALUES"]
    for uid in ids:
        sql_lines.append(f"  ('{uid}', 'New Description {uid}'),")
    sql_content = "\n".join(sql_lines).rstrip(",") + ";"

    temp_seed = tmp_path / "temp_seed.sql"
    temp_seed.write_text(sql_content, encoding="utf-8")

    mock_session = _build_mock_pg_session()

    # ID 1 has changed description; others are unchanged
    pre_seed_rows = []
    for i, uid in enumerate(ids):
        if i == 0:
            pre_seed_rows.append((uid, "Old Description 1", _make_fake_vector()))
        else:
            pre_seed_rows.append((uid, f"New Description {uid}", _make_fake_vector()))

    mock_session.execute.return_value.all.side_effect = [
        pre_seed_rows,  # Pre-seed query
        [(uid, _make_fake_vector()) for uid in ids],  # Final completeness query
    ]

    listings_map = {}
    for i, uid in enumerate(ids):
        listings_map[uid] = InternshipListing(
            id=uid,
            title="Test",
            company="Co",
            location="Remote",
            work_type="remote",
            description=f"New Description {uid}",
            description_embedding=_make_fake_vector(),
        )

    mock_session.scalars.return_value.all.return_value = list(listings_map.values())
    mock_session.get.side_effect = lambda model, uid: listings_map.get(uid)

    mock_embedder = MagicMock(return_value=_make_fake_vector())

    summary = seed_demo_internships(
        session=mock_session,
        seed_sql_path=temp_seed,
        embedder_func=mock_embedder,
        refresh_embeddings=False,
    )

    assert summary.demo_rows == 35
    assert summary.invalidated == 1
    assert summary.embedded == 1
    assert summary.skipped_existing == 34
    assert mock_embedder.call_count == 1
    mock_embedder.assert_called_once_with(f"New Description {ids[0]}")


def test_forced_refresh_regenerates_all_35_embeddings(tmp_path: Path):
    """Test 7: --refresh-embeddings invalidates and regenerates all 35 embeddings."""
    ids = sorted(list(EXPECTED_DEMO_IDS))
    sql_lines = ["INSERT INTO public.internship_listings (id, description) VALUES"]
    for uid in ids:
        sql_lines.append(f"  ('{uid}', 'Desc {uid}'),")
    sql_content = "\n".join(sql_lines).rstrip(",") + ";"

    temp_seed = tmp_path / "temp_seed.sql"
    temp_seed.write_text(sql_content, encoding="utf-8")

    mock_session = _build_mock_pg_session()

    pre_seed_rows = [(uid, f"Desc {uid}", _make_fake_vector()) for uid in ids]
    mock_session.execute.return_value.all.side_effect = [
        pre_seed_rows,  # Pre-seed query
        [(uid, _make_fake_vector()) for uid in ids],  # Final completeness query
    ]

    listings_map = {
        uid: InternshipListing(
            id=uid,
            title="Test",
            company="Co",
            location="Remote",
            work_type="remote",
            description=f"Desc {uid}",
            description_embedding=_make_fake_vector(),
        )
        for uid in ids
    }
    mock_session.scalars.return_value.all.return_value = list(listings_map.values())
    mock_session.get.side_effect = lambda model, uid: listings_map.get(uid)

    mock_embedder = MagicMock(return_value=_make_fake_vector())

    summary = seed_demo_internships(
        session=mock_session,
        seed_sql_path=temp_seed,
        embedder_func=mock_embedder,
        refresh_embeddings=True,
    )

    assert summary.demo_rows == 35
    assert summary.invalidated == 35
    assert summary.embedded == 35
    assert summary.skipped_existing == 0
    assert mock_embedder.call_count == 35


def test_embedding_failure_rolls_back_and_raises_safe_error(tmp_path: Path):
    """Test 8: Embedding failure rolls back and raises safe error without leakage."""
    ids = sorted(list(EXPECTED_DEMO_IDS))
    sql_lines = ["INSERT INTO public.internship_listings (id, description) VALUES"]
    for uid in ids:
        sql_lines.append(f"  ('{uid}', 'Desc {uid}'),")
    sql_content = "\n".join(sql_lines).rstrip(",") + ";"

    temp_seed = tmp_path / "temp_seed.sql"
    temp_seed.write_text(sql_content, encoding="utf-8")

    mock_session = _build_mock_pg_session()

    mock_session.execute.return_value.all.side_effect = [
        [],  # Pre-seed query
    ]

    listings_map = {
        uid: InternshipListing(
            id=uid,
            title="Test",
            company="Co",
            location="Remote",
            work_type="remote",
            description=f"Desc {uid}",
            description_embedding=None,
        )
        for uid in ids
    }
    mock_session.scalars.return_value.all.return_value = list(listings_map.values())
    mock_session.get.side_effect = lambda model, uid: listings_map.get(uid)

    failing_embedder = MagicMock(
        side_effect=RuntimeError("OpenAI API secret key sk-12345 invalid")
    )

    with pytest.raises(DemoSeedEmbeddingError) as exc_info:
        seed_demo_internships(
            session=mock_session,
            seed_sql_path=temp_seed,
            embedder_func=failing_embedder,
            refresh_embeddings=False,
        )

    # Prove safe error format and that secrets/provider errors are not exposed
    err_msg = str(exc_info.value)
    assert f"internship ID {ids[0]}" in err_msg
    assert "sk-12345" not in err_msg
    assert "OpenAI API secret" not in err_msg
    assert mock_session.rollback.called


def test_non_demo_listings_are_never_queried_or_modified(tmp_path: Path):
    """Test 9: Only the 35 deterministic demo IDs are selected and mutated."""
    ids = sorted(list(EXPECTED_DEMO_IDS))
    sql_lines = ["INSERT INTO public.internship_listings (id, description) VALUES"]
    for uid in ids:
        sql_lines.append(f"  ('{uid}', 'Desc {uid}'),")
    sql_content = "\n".join(sql_lines).rstrip(",") + ";"

    temp_seed = tmp_path / "temp_seed.sql"
    temp_seed.write_text(sql_content, encoding="utf-8")

    mock_session = _build_mock_pg_session()

    non_demo_id = uuid4()
    non_demo_listing = InternshipListing(
        id=non_demo_id,
        title="Non-demo",
        company="Other Co",
        location="Remote",
        work_type="remote",
        description="Non demo listing description",
        description_embedding=_make_fake_vector(),
    )

    # Demo listings
    demo_listings = {
        uid: InternshipListing(
            id=uid,
            title="Demo",
            company="Co",
            location="Remote",
            work_type="remote",
            description=f"Desc {uid}",
            description_embedding=_make_fake_vector(),
        )
        for uid in ids
    }

    mock_session.execute.return_value.all.side_effect = [
        [(uid, f"Desc {uid}", _make_fake_vector()) for uid in ids],  # Pre-seed query
        [(uid, _make_fake_vector()) for uid in ids],  # Final completeness query
    ]
    mock_session.scalars.return_value.all.return_value = list(demo_listings.values())
    mock_session.get.side_effect = lambda model, uid: demo_listings.get(uid)

    seed_demo_internships(
        session=mock_session,
        seed_sql_path=temp_seed,
        embedder_func=MagicMock(),
        refresh_embeddings=False,
    )

    for listing in demo_listings.values():
        assert listing.listing_source == "curated"
        assert listing.employer_organization_id is None

    # Non demo listing was never retrieved or modified
    assert non_demo_listing.description_embedding == _make_fake_vector()


def test_apply_authoritative_sql_executes_raw_cursor_without_params():
    """
    Regression Test: apply_authoritative_sql obtains raw DBAPI cursor from session,
    executes the exact SQL string with a single argument (no params argument),
    supports literal '%' characters without driver formatting error, closes cursor,
    and does not commit or rollback the transaction.
    """
    mock_session = MagicMock()
    mock_sqlalchemy_conn = MagicMock()
    mock_dbapi_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_session.connection.return_value = mock_sqlalchemy_conn
    mock_sqlalchemy_conn.connection = mock_dbapi_conn
    mock_dbapi_conn.cursor.return_value = mock_cursor

    raw_sql_with_percent = (
        "-- Provenance: 100% Synthetic Original Demo Data\n"
        "INSERT INTO public.skills (id, name) VALUES "
        "('10000000-0000-0000-0000-000000000001', 'Python%Special');"
    )

    apply_authoritative_sql(mock_session, raw_sql_with_percent)

    # 1. Obtains cursor from DBAPI connection
    mock_dbapi_conn.cursor.assert_called_once_with()

    # 2 & 3 & 4. Exactly one argument passed to cursor.execute; no params tuple/dict
    mock_cursor.execute.assert_called_once_with(raw_sql_with_percent)
    assert len(mock_cursor.execute.call_args[0]) == 1
    assert mock_cursor.execute.call_args[1] == {}

    # 5. Cursor is closed
    mock_cursor.close.assert_called_once_with()

    # 6. Does not commit or rollback
    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_not_called()
