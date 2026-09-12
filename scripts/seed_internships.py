"""
InternMatch AI — Operational Demo Internship Data Seeder
Executes authoritative synthetic demo SQL seed and populates pgvector description embeddings
idempotently and safely.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence
from uuid import UUID

# Ensure backend modules can be imported when running `python scripts/seed_internships.py`
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

# Default path to the single source of truth SQL seed
DEFAULT_SEED_SQL_PATH = REPO_ROOT / "database" / "seeds" / "001_demo_internships.sql"
EXPECTED_DEMO_COUNT = 35
EXPECTED_DEMO_IDS = {
    UUID(f"20000000-0000-0000-0000-{i:012d}")
    for i in range(1, EXPECTED_DEMO_COUNT + 1)
}


class DemoSeedError(Exception):
    """Base safe exception for demo seeder failures."""

    pass


class DemoSeedValidationError(DemoSeedError):
    """Raised when the demo SQL seed fails deterministic ID validation."""

    pass


class DemoSeedEmbeddingError(DemoSeedError):
    """Safe exception raised when embedding generation fails for a demo row."""

    def __init__(
        self, listing_id: UUID, message: str = "Embedding generation failed."
    ) -> None:
        self.listing_id = listing_id
        super().__init__(
            f"SafeSeederError: Failed to generate/persist embedding for "
            f"internship ID {listing_id}. {message}"
        )


@dataclass(frozen=True)
class DemoSeedSummary:
    """Summary of demo data seeding execution."""

    demo_rows: int
    invalidated: int
    embedded: int
    skipped_existing: int
    missing_embeddings: int

    def __str__(self) -> str:
        return (
            f"demo_rows={self.demo_rows}\n"
            f"invalidated={self.invalidated}\n"
            f"embedded={self.embedded}\n"
            f"skipped_existing={self.skipped_existing}\n"
            f"missing_embeddings={self.missing_embeddings}"
        )


def extract_demo_internship_ids_from_sql(sql_content: str) -> List[UUID]:
    """
    Extract and validate deterministic demo internship UUIDs (20000000-...) from SQL.
    Must contain exactly EXPECTED_DEMO_COUNT unique valid UUIDs matching controlled set.
    """
    # Pattern matching 20000000-0000-0000-0000-0000000000xx demo internship UUID range
    raw_matches = re.findall(
        r"'(20000000-0000-0000-0000-[0-9a-fA-F]{12})'", sql_content
    )

    if len(raw_matches) != EXPECTED_DEMO_COUNT:
        raise DemoSeedValidationError(
            f"Invalid demo SQL seed: expected exactly {EXPECTED_DEMO_COUNT} demo "
            f"internship ID occurrences, found {len(raw_matches)}."
        )

    parsed_ids: List[UUID] = []
    seen = set()
    for raw_id in raw_matches:
        try:
            val = UUID(raw_id)
        except ValueError:
            raise DemoSeedValidationError(
                f"Invalid UUID format in demo SQL seed: {raw_id}"
            )
        if val in seen:
            raise DemoSeedValidationError(
                f"Duplicate demo internship ID in SQL seed: {val}"
            )
        seen.add(val)
        parsed_ids.append(val)

    if len(parsed_ids) != EXPECTED_DEMO_COUNT:
        raise DemoSeedValidationError(
            f"Invalid demo SQL seed: expected exactly {EXPECTED_DEMO_COUNT} "
            f"unique demo internship IDs, got {len(parsed_ids)}."
        )

    extracted_set = set(parsed_ids)
    if extracted_set != EXPECTED_DEMO_IDS:
        missing = sorted(str(u) for u in (EXPECTED_DEMO_IDS - extracted_set))
        extra = sorted(str(u) for u in (extracted_set - EXPECTED_DEMO_IDS))
        raise DemoSeedValidationError(
            "Invalid demo SQL seed: extracted IDs do not match the authoritative "
            f"controlled ID set. Missing IDs: {missing}, Extra IDs: {extra}."
        )

    return parsed_ids


def apply_authoritative_sql(session: Session, sql_content: str) -> None:
    """
    Execute authoritative SQL seed as raw driver SQL without manual statement splitting.
    Uses raw DBAPI cursor with no parameters argument to safely support literal '%' characters.
    """
    sqlalchemy_connection = session.connection()
    dbapi_connection = sqlalchemy_connection.connection
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(sql_content)
    finally:
        cursor.close()


def seed_demo_internships(
    session: Session,
    seed_sql_path: Path = DEFAULT_SEED_SQL_PATH,
    embedder_func: Optional[Callable[[str], Sequence[float]]] = None,
    refresh_embeddings: bool = False,
) -> DemoSeedSummary:
    """
    Idempotently seeds authoritative demo internship listings and backfills embeddings.
    Accepts an explicit SQLAlchemy Session for database isolation and testability.
    """
    # 1. Enforce PostgreSQL dialect
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        raise DemoSeedError(
            "seed_demo_internships requires a PostgreSQL database with pgvector, "
            f"got dialect: {bind.dialect.name}"
        )

    # 2. Read authoritative SQL seed
    if not seed_sql_path.exists():
        raise DemoSeedError(f"Authoritative SQL seed not found at {seed_sql_path}")

    sql_content = seed_sql_path.read_text(encoding="utf-8")

    # 3. Extract and validate deterministic demo IDs before modifying DB
    demo_ids = extract_demo_internship_ids_from_sql(sql_content)

    # Import InternshipListing dynamically/safely
    from app.db.models import InternshipListing

    # 4. Capture pre-seed state for ONLY the 35 deterministic demo IDs
    pre_seed_stmt = select(
        InternshipListing.id,
        InternshipListing.description,
        InternshipListing.description_embedding,
    ).where(InternshipListing.id.in_(demo_ids))
    pre_seed_rows = session.execute(pre_seed_stmt).all()
    pre_seed_descriptions: Dict[UUID, str] = {
        row[0]: row[1] for row in pre_seed_rows
    }

    # 5. Apply authoritative SQL seed
    apply_authoritative_sql(session, sql_content)

    # 6. Reload the 35 rows and handle invalidation
    post_seed_stmt = select(InternshipListing).where(
        InternshipListing.id.in_(demo_ids)
    )
    post_seed_listings = {
        listing.id: listing for listing in session.scalars(post_seed_stmt).all()
    }

    if len(post_seed_listings) != EXPECTED_DEMO_COUNT:
        raise DemoSeedError(
            f"Post-seed row count mismatch: expected {EXPECTED_DEMO_COUNT} "
            f"demo listings, found {len(post_seed_listings)}"
        )

    invalidated_count = 0
    for demo_id, listing in post_seed_listings.items():
        # These 35 deterministic IDs are the only authoritative curated
        # demo listings. Never infer curated provenance from a NULL owner.
        listing.listing_source = "curated"
        listing.employer_organization_id = None
        listing.publication_status = "published"
        listing.is_active = True

        if refresh_embeddings:
            if listing.description_embedding is not None:
                listing.description_embedding = None
                invalidated_count += 1
        else:
            # Check if authoritative description changed from pre-seed state
            pre_desc = pre_seed_descriptions.get(demo_id)
            if pre_desc is not None and pre_desc != listing.description:
                if listing.description_embedding is not None:
                    listing.description_embedding = None
                    invalidated_count += 1

    # Commit SQL seed + any invalidations before calling embedding API
    session.commit()

    # 7. Embedding backfill (missing-only)
    if embedder_func is None:
        from app.services.embeddings import generate_embedding

        embedder_func = generate_embedding

    embedded_count = 0
    skipped_existing = 0

    for demo_id in demo_ids:
        listing = session.get(InternshipListing, demo_id)
        if listing is None:
            raise DemoSeedError(f"Demo listing {demo_id} not found in database")

        if listing.description_embedding is not None:
            skipped_existing += 1
            continue

        # Generate embedding
        try:
            vector = embedder_func(listing.description)
        except Exception:
            session.rollback()
            raise DemoSeedEmbeddingError(
                demo_id, "Embedding provider call failed."
            ) from None

        try:
            listing.description_embedding = list(vector)
            session.commit()
            embedded_count += 1
        except Exception:
            session.rollback()
            raise DemoSeedEmbeddingError(
                demo_id, "Failed to persist embedding to database."
            ) from None

    # 8. Final completeness assertions
    final_stmt = select(
        InternshipListing.id, InternshipListing.description_embedding
    ).where(InternshipListing.id.in_(demo_ids))
    final_rows = session.execute(final_stmt).all()

    if len(final_rows) != EXPECTED_DEMO_COUNT:
        raise DemoSeedError(
            f"Final completeness check failed: expected {EXPECTED_DEMO_COUNT} "
            f"rows, found {len(final_rows)}"
        )

    missing_count = sum(1 for row in final_rows if row[1] is None)
    if missing_count != 0:
        raise DemoSeedError(
            f"Final completeness check failed: {missing_count} demo listings "
            "have NULL description_embedding"
        )

    return DemoSeedSummary(
        demo_rows=EXPECTED_DEMO_COUNT,
        invalidated=invalidated_count,
        embedded=embedded_count,
        skipped_existing=skipped_existing,
        missing_embeddings=missing_count,
    )


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for running the demo internships seeder."""
    parser = argparse.ArgumentParser(
        description=(
            "Seed authoritative synthetic demo internships and backfill "
            "pgvector embeddings.\n"
            "Default behavior skips already-valid unchanged embeddings.\n"
            "Use --refresh-embeddings to force regeneration.\n"
            "If interrupted during a refresh, rerunning without "
            "--refresh-embeddings resumes only remaining NULL rows."
        )
    )
    parser.add_argument(
        "--refresh-embeddings",
        action="store_true",
        help=(
            "Force invalidation and regeneration of description embeddings "
            "for all 35 demo internships."
        ),
    )

    args = parser.parse_args(argv)

    try:
        from app.db.session import SessionLocal

        with SessionLocal() as session:
            summary = seed_demo_internships(
                session=session,
                seed_sql_path=DEFAULT_SEED_SQL_PATH,
                refresh_embeddings=args.refresh_embeddings,
            )
            print(summary)
            return 0
    except DemoSeedError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(
            "Error: An unexpected error occurred during demo data seeding: "
            f"{e.__class__.__name__}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
