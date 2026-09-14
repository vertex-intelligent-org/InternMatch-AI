"""Gate 2 employer trust and administrative authority foundation tests."""

from uuid import uuid4

import pytest
from app.core.config import settings
from app.core.security import AuthenticatedUser, require_admin_user
from app.db.models import EmployerOrganization
from app.repositories.employer_organization import EmployerOrganizationRepository
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from tests.db import TestingSessionLocal


def _authenticated_user(user_id):
    return AuthenticatedUser(
        user_id=user_id,
        email="admin-test@example.com",
        role="authenticated",
        token_claims={},
    )


def _create_organization(db, owner_user_id):
    return EmployerOrganizationRepository.create(
        db,
        owner_user_id=owner_user_id,
        legal_name="Acme Teknoloji Anonim Sirketi",
        display_name="Acme",
        website_url="https://acme.example",
        normalized_domain="acme.example",
        business_email="hr@acme.example",
        country_code="TR",
        registration_number="TR-123456",
        tax_number="1234567890",
        representative_name="Ada Recruiter",
        representative_role="HR Manager",
    )


def test_admin_authority_accepts_only_configured_user_uuid(monkeypatch):
    admin_user_id = uuid4()

    monkeypatch.setattr(
        settings,
        "ADMIN_USER_IDS",
        str(admin_user_id),
    )

    result = require_admin_user(
        current_user=_authenticated_user(admin_user_id)
    )

    assert result.user_id == admin_user_id


def test_admin_authority_denies_authenticated_non_admin(monkeypatch):
    admin_user_id = uuid4()
    regular_user_id = uuid4()

    monkeypatch.setattr(
        settings,
        "ADMIN_USER_IDS",
        str(admin_user_id),
    )

    with pytest.raises(HTTPException) as exc_info:
        require_admin_user(
            current_user=_authenticated_user(regular_user_id)
        )

    assert exc_info.value.status_code == 403


def test_admin_authority_empty_allowlist_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_USER_IDS", "")

    with pytest.raises(HTTPException) as exc_info:
        require_admin_user(
            current_user=_authenticated_user(uuid4())
        )

    assert exc_info.value.status_code == 403


def test_admin_authority_invalid_config_fails_closed(monkeypatch):
    monkeypatch.setattr(
        settings,
        "ADMIN_USER_IDS",
        "not-a-valid-uuid",
    )

    with pytest.raises(HTTPException) as exc_info:
        require_admin_user(
            current_user=_authenticated_user(uuid4())
        )

    assert exc_info.value.status_code == 500


def test_employer_organization_starts_unverified():
    owner_user_id = uuid4()

    db = TestingSessionLocal()
    try:
        organization = _create_organization(db, owner_user_id)
        db.commit()
        db.refresh(organization)

        assert organization.owner_user_id == owner_user_id
        assert organization.organization_type == "company"
        assert organization.verification_method is None
        assert organization.verification_status == "unverified"
        assert organization.reviewed_by is None
        assert organization.reviewed_at is None
        assert organization.rejection_reason_code is None
    finally:
        db.close()


def test_employer_organization_owner_is_unique():
    owner_user_id = uuid4()

    db = TestingSessionLocal()
    try:
        _create_organization(db, owner_user_id)
        db.commit()

        with pytest.raises(IntegrityError):
            _create_organization(db, owner_user_id)

        db.rollback()
    finally:
        db.close()


def test_invalid_employer_verification_status_rejected_by_database():
    db = TestingSessionLocal()
    try:
        organization = EmployerOrganization(
            owner_user_id=uuid4(),
            legal_name="Unsafe Company",
            display_name="Unsafe Company",
            website_url="https://unsafe.example",
            normalized_domain="unsafe.example",
            business_email="hr@unsafe.example",
            country_code="TR",
            representative_name="Unsafe User",
            representative_role="Recruiter",
            verification_status="self_verified",
        )

        db.add(organization)

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()
    finally:
        db.close()


def test_verification_audit_event_is_persisted():
    owner_user_id = uuid4()
    reviewer_user_id = uuid4()

    db = TestingSessionLocal()
    try:
        organization = _create_organization(db, owner_user_id)

        event = EmployerOrganizationRepository.record_event(
            db,
            organization_id=organization.id,
            reviewer_user_id=reviewer_user_id,
            action="approved",
            previous_status="pending",
            new_status="verified",
            verification_method="manual_admin",
            internal_note="Registry and domain manually reviewed.",
        )

        db.commit()
        db.refresh(event)

        assert event.organization_id == organization.id
        assert event.reviewer_user_id == reviewer_user_id
        assert event.action == "approved"
        assert event.previous_status == "pending"
        assert event.new_status == "verified"
        assert event.verification_method == "manual_admin"
    finally:
        db.close()


def test_migration_019_contains_server_authoritative_trust_constraints():
    migration = (
        __import__("pathlib")
        .Path(__file__)
        .resolve()
        .parents[1]
        / "database"
        / "migrations"
        / "019_add_employer_organization_verification.sql"
    ).read_text(encoding="utf-8")

    assert "REFERENCES auth.users(id) ON DELETE CASCADE" in migration
    assert "UNIQUE (owner_user_id)" in migration
    assert "'unverified'" in migration
    assert "'pending'" in migration
    assert "'verified'" in migration
    assert "'rejected'" in migration
    assert "'suspended'" in migration
    assert "employer_verification_events" in migration
    assert migration.count("DEFAULT uuid_generate_v4()") >= 2
    assert (
        "ALTER TABLE public.employer_organizations\n"
        "    ENABLE ROW LEVEL SECURITY"
    ) in migration
    assert (
        "ALTER TABLE public.employer_verification_events\n"
        "    ENABLE ROW LEVEL SECURITY"
    ) in migration
    assert (
        "ON TABLE public.employer_organizations\n"
        "FROM PUBLIC, anon, authenticated"
    ) in migration
    assert (
        "ON TABLE public.employer_verification_events\n"
        "FROM PUBLIC, anon, authenticated"
    ) in migration
    assert (
        "ON TABLE public.employer_organizations\n"
        "TO service_role"
    ) in migration
    assert (
        "ON TABLE public.employer_verification_events\n"
        "TO service_role"
    ) in migration


def test_invalid_employer_organization_type_rejected_by_database():
    db = TestingSessionLocal()
    try:
        organization = _create_organization(db, uuid4())
        organization.organization_type = "self_declared_lab"

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()
    finally:
        db.close()


def test_invalid_employer_verification_method_rejected_by_database():
    db = TestingSessionLocal()
    try:
        organization = _create_organization(db, uuid4())
        organization.verification_status = "verified"
        organization.verification_method = "self_verified"

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()
    finally:
        db.close()


def test_verified_employer_requires_verification_method():
    db = TestingSessionLocal()
    try:
        organization = _create_organization(db, uuid4())
        organization.verification_status = "verified"
        organization.verification_method = None

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()
    finally:
        db.close()


def test_non_company_cannot_use_standard_company_verification():
    db = TestingSessionLocal()
    try:
        organization = _create_organization(db, uuid4())
        organization.organization_type = "university_lab"
        organization.verification_status = "verified"
        organization.verification_method = "standard_company"

        with pytest.raises(IntegrityError):
            db.flush()

        db.rollback()
    finally:
        db.close()
