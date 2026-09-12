"""
PostgreSQL Vector Candidate Retrieval Repository
Provides PostgreSQL pgvector nearest-neighbor candidate retrieval for internship matching.
"""

from dataclasses import dataclass
from typing import List, Sequence

from app.core.config import settings
from app.db.models import InternshipListing
from app.repositories.internship import public_internship_visibility_condition
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select


@dataclass(frozen=True)
class VectorCandidate:
    """Internal candidate representation pairing an InternshipListing with raw cosine distance."""

    internship: InternshipListing
    cosine_distance: float


def build_nearest_internships_statement(
    candidate_embedding: Sequence[float],
    limit: int,
) -> Select:
    """
    Construct SQLAlchemy Select statement for retrieving nearest internship listings
    by vector cosine distance.
    Validates input parameters before statement construction.
    """
    expected_dim = settings.EMBEDDING_DIMENSION
    if len(candidate_embedding) != expected_dim:
        raise ValueError(
            f"Invalid candidate_embedding dimension {len(candidate_embedding)}. "
            f"Expected dimension {expected_dim}."
        )

    if limit <= 0:
        raise ValueError(f"Invalid limit {limit}. Limit must be a positive integer > 0.")

    distance_expr = InternshipListing.description_embedding.cosine_distance(
        candidate_embedding
    ).label("cosine_distance")

    stmt = (
        select(InternshipListing, distance_expr)
        .where(
            InternshipListing.description_embedding.is_not(None),
            public_internship_visibility_condition(),
        )
        .order_by(distance_expr.asc())
        .limit(limit)
    )

    return stmt


class VectorRetrievalRepository:
    """Repository boundary for PostgreSQL pgvector nearest-neighbor candidate retrieval."""

    @staticmethod
    def get_nearest_internships(
        db: Session,
        candidate_embedding: Sequence[float],
        limit: int,
    ) -> List[VectorCandidate]:
        """
        Retrieve up to `limit` InternshipListing candidates nearest to `candidate_embedding`
        by PostgreSQL vector cosine distance ASC.
        Returns typed List[VectorCandidate] holding internship listing and raw float distance.
        """
        stmt = build_nearest_internships_statement(
            candidate_embedding=candidate_embedding, limit=limit
        )

        rows = db.execute(stmt).all()
        return [
            VectorCandidate(
                internship=internship,
                cosine_distance=float(dist),
            )
            for internship, dist in rows
        ]
