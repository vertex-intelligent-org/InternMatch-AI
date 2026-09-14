"""Employer compliance evidence foundation tests."""

from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.models import (
    EmployerComplianceClaim,
    EmployerComplianceEvent,
    EmployerComplianceEvidence,
    EmployerOrganization,
)
from app.repositories.employer_compliance import (
    EmployerComplianceRepository,
)
from sqlalchemy.exc import IntegrityError

from tests.db import TestingSessionLocal


def _create_organization():
    db = TestingSessionLocal()

    try:
        organization = EmployerOrganization(
            owner_user_id=uuid4(),
            legal_name=(
                "Acme Teknoloji Anonim Sirketi"
            ),
            display_name="Acme",
            website_url="https://acme.example",
            normalized_domain="acme.example",
            business_email="hr@acme.example",
            country_code="TR",
            registration_number="TR-123456",
            tax_number="1234567890",
            representative_name="Ada Recruiter",
            representative_role="HR Manager",
            verification_status="verified",
            organization_type="company",
            verification_method="standard_company",
            submitted_at=datetime.now(timezone.utc),
            reviewed_at=datetime.now(timezone.utc),
            reviewed_by=uuid4(),
            rejection_reason_code=None,
        )

        db.add(organization)
        db.commit()
        db.refresh(organization)

        return organization.id
    finally:
        db.close()


def test_claim_is_separate_from_organization_verification():
    organization_id = _create_organization()

    db = TestingSessionLocal()

    try:
        claim = (
            EmployerComplianceRepository.create_claim(
                db,
                organization_id=organization_id,
                claim_type="insurance_arrangement",
                jurisdiction_country_code="TR",
                scope_key="organization",
                statement=(
                    "Employer states that an insurance "
                    "arrangement may be available."
                ),
            )
        )

        EmployerComplianceRepository.record_event(
            db,
            claim_id=claim.id,
            actor_user_id=uuid4(),
            actor_role="employer",
            action="created",
            previous_status=None,
            new_status="draft",
        )

        db.commit()

        organization = db.get(
            EmployerOrganization,
            organization_id,
        )

        assert organization is not None
        assert (
            organization.verification_status
            == "verified"
        )

        persisted = db.get(
            EmployerComplianceClaim,
            claim.id,
        )

        assert persisted is not None
        assert persisted.status == "draft"
        assert persisted.version == 1

        events = (
            db.query(EmployerComplianceEvent)
            .filter(
                EmployerComplianceEvent.claim_id
                == claim.id
            )
            .all()
        )

        assert len(events) == 1
        assert events[0].action == "created"
    finally:
        db.close()


def test_claim_scope_is_unique_race_safety_barrier():
    organization_id = _create_organization()

    db = TestingSessionLocal()

    try:
        EmployerComplianceRepository.create_claim(
            db,
            organization_id=organization_id,
            claim_type="completion_certificate",
            jurisdiction_country_code="TR",
            scope_key="organization",
        )

        db.commit()

        with pytest.raises(IntegrityError):
            EmployerComplianceRepository.create_claim(
                db,
                organization_id=organization_id,
                claim_type="completion_certificate",
                jurisdiction_country_code="TR",
                scope_key="organization",
            )

        db.rollback()
    finally:
        db.close()


def test_claim_scope_supports_specific_university_agreement():
    organization_id = _create_organization()

    db = TestingSessionLocal()

    try:
        first = EmployerComplianceRepository.create_claim(
            db,
            organization_id=organization_id,
            claim_type="university_agreement",
            jurisdiction_country_code="TR",
            scope_key="uskudar-university",
            scope_label="Üsküdar University",
        )

        second = (
            EmployerComplianceRepository.create_claim(
                db,
                organization_id=organization_id,
                claim_type="university_agreement",
                jurisdiction_country_code="TR",
                scope_key="itu",
                scope_label=(
                    "Istanbul Technical University"
                ),
            )
        )

        db.commit()

        assert first.id != second.id

        claims = (
            EmployerComplianceRepository
            .list_claims_for_organization(
                db,
                organization_id,
            )
        )

        assert len(claims) == 2
    finally:
        db.close()


def test_locked_status_transition_increments_version():
    organization_id = _create_organization()

    db = TestingSessionLocal()

    try:
        claim = EmployerComplianceRepository.create_claim(
            db,
            organization_id=organization_id,
            claim_type=(
                "legal_internship_eligibility"
            ),
            jurisdiction_country_code="TR",
            scope_key="organization",
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31),
        )

        db.commit()

        locked = (
            EmployerComplianceRepository
            .get_claim_for_update(
                db,
                claim.id,
            )
        )

        assert locked is not None
        assert locked.version == 1

        submitted_at = datetime.now(timezone.utc)

        EmployerComplianceRepository.transition_status(
            db,
            locked,
            new_status="pending",
            submitted_at=submitted_at,
        )

        EmployerComplianceRepository.record_event(
            db,
            claim_id=locked.id,
            actor_user_id=uuid4(),
            actor_role="employer",
            action="submitted",
            previous_status="draft",
            new_status="pending",
        )

        db.commit()

        refreshed = db.get(
            EmployerComplianceClaim,
            claim.id,
        )

        assert refreshed is not None
        assert refreshed.status == "pending"
        assert refreshed.version == 2
        assert refreshed.submitted_at is not None
    finally:
        db.close()


def test_private_evidence_metadata_is_persisted():
    organization_id = _create_organization()
    uploader_id = uuid4()

    db = TestingSessionLocal()

    try:
        claim = EmployerComplianceRepository.create_claim(
            db,
            organization_id=organization_id,
            claim_type="completion_certificate",
            jurisdiction_country_code="TR",
            scope_key="organization",
        )

        evidence = EmployerComplianceRepository.add_evidence(
            db,
            claim_id=claim.id,
            storage_path=(
                f"{organization_id}/"
                f"{claim.id}/"
                "evidence-document.pdf"
            ),
            original_filename=(
                "certificate-policy.pdf"
            ),
            content_type="application/pdf",
            size_bytes=1024,
            sha256_hex="a" * 64,
            uploaded_by_user_id=uploader_id,
        )

        EmployerComplianceRepository.record_event(
            db,
            claim_id=claim.id,
            actor_user_id=uploader_id,
            actor_role="employer",
            action="evidence_attached",
            previous_status="draft",
            new_status="draft",
        )

        db.commit()

        stored = db.get(
            EmployerComplianceEvidence,
            evidence.id,
        )

        assert stored is not None
        assert stored.storage_path.endswith(".pdf")
        assert stored.sha256_hex == "a" * 64

        claim_evidence = (
            EmployerComplianceRepository
            .list_evidence_for_claim(
                db,
                claim.id,
            )
        )

        assert len(claim_evidence) == 1
    finally:
        db.close()


def test_evidence_organization_authority_is_claim_only():
    model_text = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "app"
        / "db"
        / "models.py"
    ).read_text(
        encoding="utf-8"
    )

    evidence_start = model_text.index(
        "class EmployerComplianceEvidence(Base):"
    )

    event_start = model_text.index(
        "class EmployerComplianceEvent(Base):"
    )

    evidence_block = model_text[
        evidence_start:event_start
    ]

    internship_start = model_text.index(
        "class InternshipListing(Base):",
        event_start,
    )

    event_block = model_text[
        event_start:internship_start
    ]

    assert "organization_id:" not in evidence_block
    assert "organization_id:" not in event_block


def test_migration_enforces_server_owned_security_contract():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "database"
        / "migrations"
        / "024_add_employer_compliance_evidence.sql"
    )

    sql = migration_path.read_text(
        encoding="utf-8"
    ).lower()

    assert "employer_compliance_claims" in sql
    assert "employer_compliance_evidence" in sql
    assert "employer_compliance_events" in sql

    assert "insurance_arrangement" in sql
    assert "completion_certificate" in sql
    assert "university_agreement" in sql
    assert "legal_internship_eligibility" in sql

    assert (
        sql.count("enable row level security")
        == 3
    )

    assert (
        "from public, anon, authenticated"
        in sql
    )

    assert sql.count("to service_role") == 3

    assert (
        "organization verification proves reviewed "
        "organization identity only"
        in sql
    )
