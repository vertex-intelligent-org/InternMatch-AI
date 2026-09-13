"""
Employer compliance evidence repository.

Organization identity verification and compliance claims are separate trust
domains. Repository methods provide transaction-safe persistence primitives
without granting legal or verification authority to public clients.
"""

from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from app.db.models import (
    EmployerComplianceClaim,
    EmployerComplianceEvidence,
    EmployerComplianceEvent,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


class EmployerComplianceRepository:
    """Database access for employer compliance claims and evidence."""

    @staticmethod
    def get_claim(
        db: Session,
        claim_id: UUID,
    ) -> Optional[EmployerComplianceClaim]:
        return db.get(
            EmployerComplianceClaim,
            claim_id,
        )

    @staticmethod
    def get_claim_for_update(
        db: Session,
        claim_id: UUID,
    ) -> Optional[EmployerComplianceClaim]:
        stmt = (
            select(EmployerComplianceClaim)
            .where(
                EmployerComplianceClaim.id == claim_id
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

        return db.scalar(stmt)

    @staticmethod
    def get_claim_by_scope(
        db: Session,
        *,
        organization_id: UUID,
        claim_type: str,
        jurisdiction_country_code: str,
        scope_key: str,
    ) -> Optional[EmployerComplianceClaim]:
        stmt = select(
            EmployerComplianceClaim
        ).where(
            EmployerComplianceClaim.organization_id
            == organization_id,
            EmployerComplianceClaim.claim_type
            == claim_type,
            EmployerComplianceClaim.jurisdiction_country_code
            == jurisdiction_country_code,
            EmployerComplianceClaim.scope_key
            == scope_key,
        )

        return db.scalar(stmt)

    @staticmethod
    def list_claims_for_organization(
        db: Session,
        organization_id: UUID,
    ) -> list[EmployerComplianceClaim]:
        stmt = (
            select(EmployerComplianceClaim)
            .where(
                EmployerComplianceClaim.organization_id
                == organization_id
            )
            .order_by(
                EmployerComplianceClaim.created_at.asc()
            )
        )

        return list(
            db.scalars(stmt).all()
        )

    @staticmethod
    def list_claims_by_status(
        db: Session,
        status: str,
    ) -> list[EmployerComplianceClaim]:
        stmt = (
            select(EmployerComplianceClaim)
            .where(
                EmployerComplianceClaim.status == status
            )
            .order_by(
                EmployerComplianceClaim.submitted_at.asc(),
                EmployerComplianceClaim.created_at.asc(),
            )
        )

        return list(
            db.scalars(stmt).all()
        )

    @staticmethod
    def create_claim(
        db: Session,
        *,
        organization_id: UUID,
        claim_type: str,
        jurisdiction_country_code: str,
        scope_key: str,
        scope_label: Optional[str] = None,
        statement: Optional[str] = None,
        valid_from: Optional[date] = None,
        valid_until: Optional[date] = None,
    ) -> EmployerComplianceClaim:
        """
        Create one draft claim.

        The unique organization/type/jurisdiction/scope constraint is the
        database race-safety barrier for duplicate concurrent creation.
        """
        now = datetime.now(timezone.utc)

        claim = EmployerComplianceClaim(
            organization_id=organization_id,
            claim_type=claim_type,
            jurisdiction_country_code=(
                jurisdiction_country_code
            ),
            scope_key=scope_key,
            scope_label=scope_label,
            statement=statement,
            status="draft",
            version=1,
            submitted_at=None,
            reviewed_at=None,
            reviewed_by=None,
            rejection_reason_code=None,
            valid_from=valid_from,
            valid_until=valid_until,
            created_at=now,
            updated_at=now,
        )

        db.add(claim)
        db.flush()

        return claim

    @staticmethod
    def update_claim_details(
        db: Session,
        claim: EmployerComplianceClaim,
        *,
        scope_label: Optional[str],
        statement: Optional[str],
        valid_from: Optional[date],
        valid_until: Optional[date],
    ) -> EmployerComplianceClaim:
        claim.scope_label = scope_label
        claim.statement = statement
        claim.valid_from = valid_from
        claim.valid_until = valid_until
        claim.version += 1
        claim.updated_at = datetime.now(timezone.utc)

        db.flush()

        return claim

    @staticmethod
    def transition_status(
        db: Session,
        claim: EmployerComplianceClaim,
        *,
        new_status: str,
        submitted_at: Optional[datetime] = None,
        reviewed_at: Optional[datetime] = None,
        reviewed_by: Optional[UUID] = None,
        rejection_reason_code: Optional[str] = None,
    ) -> EmployerComplianceClaim:
        """
        Persist one status transition on a claim already locked by caller.
        """
        claim.status = new_status
        claim.reviewed_by = reviewed_by
        claim.rejection_reason_code = (
            rejection_reason_code
        )

        if submitted_at is not None:
            claim.submitted_at = submitted_at

        if reviewed_at is not None:
            claim.reviewed_at = reviewed_at

        claim.version += 1
        claim.updated_at = datetime.now(timezone.utc)

        db.flush()

        return claim

    @staticmethod
    def add_evidence(
        db: Session,
        *,
        claim_id: UUID,
        storage_path: str,
        original_filename: str,
        content_type: str,
        size_bytes: int,
        sha256_hex: str,
        uploaded_by_user_id: UUID,
    ) -> EmployerComplianceEvidence:
        evidence = EmployerComplianceEvidence(
            claim_id=claim_id,
            storage_path=storage_path,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256_hex=sha256_hex,
            uploaded_by_user_id=uploaded_by_user_id,
            created_at=datetime.now(timezone.utc),
        )

        db.add(evidence)
        db.flush()

        return evidence

    @staticmethod
    def list_evidence_for_claim(
        db: Session,
        claim_id: UUID,
    ) -> list[EmployerComplianceEvidence]:
        stmt = (
            select(EmployerComplianceEvidence)
            .where(
                EmployerComplianceEvidence.claim_id
                == claim_id
            )
            .order_by(
                EmployerComplianceEvidence.created_at.asc()
            )
        )

        return list(
            db.scalars(stmt).all()
        )

    @staticmethod
    def record_event(
        db: Session,
        *,
        claim_id: UUID,
        actor_user_id: Optional[UUID],
        actor_role: str,
        action: str,
        new_status: str,
        previous_status: Optional[str] = None,
        reason_code: Optional[str] = None,
        internal_note: Optional[str] = None,
    ) -> EmployerComplianceEvent:
        event = EmployerComplianceEvent(
            claim_id=claim_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action=action,
            previous_status=previous_status,
            new_status=new_status,
            reason_code=reason_code,
            internal_note=internal_note,
            created_at=datetime.now(timezone.utc),
        )

        db.add(event)
        db.flush()

        return event


    @staticmethod
    def get_evidence(
        db: Session,
        evidence_id: UUID,
    ) -> Optional[EmployerComplianceEvidence]:
        return db.get(
            EmployerComplianceEvidence,
            evidence_id,
        )

    @staticmethod
    def list_evidence_for_claim_ids(
        db: Session,
        claim_ids: list[UUID],
    ) -> list[EmployerComplianceEvidence]:
        if not claim_ids:
            return []

        stmt = (
            select(EmployerComplianceEvidence)
            .where(
                EmployerComplianceEvidence.claim_id.in_(
                    claim_ids
                )
            )
            .order_by(
                EmployerComplianceEvidence.created_at.asc()
            )
        )

        return list(
            db.scalars(stmt).all()
        )

    @staticmethod
    def bump_claim_version(
        db: Session,
        claim: EmployerComplianceClaim,
    ) -> EmployerComplianceClaim:
        claim.version += 1
        claim.updated_at = datetime.now(
            timezone.utc
        )

        db.flush()

        return claim
