"""
Employer organization trust repository.

Repository methods enforce owner-scoped reads and provide transaction-safe
persistence primitives. Lifecycle authorization remains owned by endpoint/
service layers so public employers can never self-assign verified state.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app.db.models import EmployerOrganization, EmployerVerificationEvent
from sqlalchemy import select
from sqlalchemy.orm import Session


class EmployerOrganizationRepository:
    """Database access for canonical employer organizations."""

    @staticmethod
    def get_by_owner_user_id(
        db: Session,
        owner_user_id: UUID,
    ) -> Optional[EmployerOrganization]:
        stmt = select(EmployerOrganization).where(
            EmployerOrganization.owner_user_id == owner_user_id
        )
        return db.scalar(stmt)

    @staticmethod
    def get_by_id(
        db: Session,
        organization_id: UUID,
    ) -> Optional[EmployerOrganization]:
        return db.get(EmployerOrganization, organization_id)

    @staticmethod
    def create(
        db: Session,
        *,
        owner_user_id: UUID,
        legal_name: str,
        display_name: str,
        website_url: str,
        normalized_domain: str,
        business_email: str,
        country_code: str,
        registration_number: Optional[str],
        tax_number: Optional[str],
        representative_name: str,
        representative_role: str,
    ) -> EmployerOrganization:
        """
        Create one canonical organization in the unverified state.

        Verification/reviewer fields are intentionally not accepted here.
        Database uniqueness on owner_user_id is the race-safety barrier.
        """
        now = datetime.now(timezone.utc)

        organization = EmployerOrganization(
            owner_user_id=owner_user_id,
            legal_name=legal_name,
            display_name=display_name,
            website_url=website_url,
            normalized_domain=normalized_domain,
            business_email=business_email,
            country_code=country_code,
            registration_number=registration_number,
            tax_number=tax_number,
            representative_name=representative_name,
            representative_role=representative_role,
            verification_status="unverified",
            submitted_at=None,
            reviewed_at=None,
            reviewed_by=None,
            rejection_reason_code=None,
            created_at=now,
            updated_at=now,
        )

        db.add(organization)
        db.flush()
        return organization

    @staticmethod
    def record_event(
        db: Session,
        *,
        organization_id: UUID,
        action: str,
        new_status: str,
        previous_status: Optional[str] = None,
        reviewer_user_id: Optional[UUID] = None,
        reason_code: Optional[str] = None,
        internal_note: Optional[str] = None,
    ) -> EmployerVerificationEvent:
        """Append one immutable verification lifecycle audit event."""
        event = EmployerVerificationEvent(
            organization_id=organization_id,
            reviewer_user_id=reviewer_user_id,
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
