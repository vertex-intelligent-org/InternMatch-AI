"""
Rebuild every persisted InternMatch vector after changing
the canonical embedding provider/model.

Run only after EMBEDDING_PROVIDER is configured to the desired
canonical provider. This script intentionally performs no
cross-provider fallback.
"""

from sqlalchemy import select

from app.core.config import settings
from app.db.models import (
    InternshipListing,
    StudentProfile,
)
from app.db.session import SessionLocal
from app.services.candidate_embedding import (
    CandidateEmbeddingPreconditionError,
    generate_and_persist_candidate_embedding,
)
from app.services.embeddings import generate_embedding


def main() -> None:
    provider = (
        settings.EMBEDDING_PROVIDER or ""
    ).strip().lower()

    if provider != "openai":
        raise RuntimeError(
            "This migration expects "
            "EMBEDDING_PROVIDER=openai."
        )

    db = SessionLocal()

    try:
        listings = list(
            db.scalars(
                select(InternshipListing)
                .order_by(
                    InternshipListing.id.asc()
                )
            ).all()
        )

        profiles = list(
            db.scalars(
                select(StudentProfile)
                .order_by(
                    StudentProfile.id.asc()
                )
            ).all()
        )

        print(
            "INTERNSHIPS_TO_REEMBED=",
            len(listings),
        )
        print(
            "PROFILES_TO_REVIEW=",
            len(profiles),
        )

        # Invalidate old candidate vectors first so a mixed
        # vector space can never be committed accidentally.
        for profile in profiles:
            profile.summary_embedding = None

        db.flush()

        # Rebuild every internship description vector.
        for index, listing in enumerate(
            listings,
            start=1,
        ):
            vector = generate_embedding(
                listing.description
            )

            if (
                len(vector)
                != settings.EMBEDDING_DIMENSION
            ):
                raise RuntimeError(
                    "Internship embedding dimension mismatch."
                )

            listing.description_embedding = vector

            print(
                f"INTERNSHIP_EMBEDDED={index}/"
                f"{len(listings)}"
            )

        db.flush()

        candidate_count = 0
        skipped_count = 0

        for profile in profiles:
            preferences = (
                profile.preferences
                if isinstance(
                    profile.preferences,
                    dict,
                )
                else {}
            )

            if (
                preferences.get(
                    "account_type"
                )
                == "employer"
            ):
                continue

            try:
                vector = (
                    generate_and_persist_candidate_embedding(
                        db=db,
                        user_id=profile.user_id,
                    )
                )

                if (
                    len(vector)
                    != settings.EMBEDDING_DIMENSION
                ):
                    raise RuntimeError(
                        "Candidate embedding dimension mismatch."
                    )

                candidate_count += 1

            except CandidateEmbeddingPreconditionError:
                # A profile with no usable ranking context is
                # intentionally left with NULL embedding.
                profile.summary_embedding = None
                skipped_count += 1

        db.commit()

        print("")
        print(
            "CANONICAL_PROVIDER=",
            provider,
        )
        print(
            "CANONICAL_MODEL=",
            settings.OPENAI_EMBEDDING_MODEL_NAME,
        )
        print(
            "DIMENSION=",
            settings.EMBEDDING_DIMENSION,
        )
        print(
            "INTERNSHIPS_REEMBEDDED=",
            len(listings),
        )
        print(
            "CANDIDATES_REEMBEDDED=",
            candidate_count,
        )
        print(
            "CANDIDATES_WITHOUT_CONTEXT=",
            skipped_count,
        )
        print(
            "VECTOR SPACE REBUILD = PASS"
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
