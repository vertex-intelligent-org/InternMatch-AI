"""Employer Free published-listing limit tests."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

import app.services.employer_product_policy as policy_module
from app.repositories.internship import InternshipRepository
from app.services.employer_product_policy import (
    EmployerListingLimitError,
    require_employer_listing_capacity,
)


def test_free_employer_with_no_published_listing_has_capacity(
    monkeypatch,
):
    user_id = uuid4()

    monkeypatch.setattr(
        policy_module,
        "get_employer_product_policy",
        lambda db, user_id: SimpleNamespace(
            plan="free",
            active_listing_limit=1,
        ),
    )

    monkeypatch.setattr(
        InternshipRepository,
        "count_published_by_employer",
        lambda db, employer_user_id,
        exclude_internship_id=None: 0,
    )

    result = require_employer_listing_capacity(
        MagicMock(),
        user_id=user_id,
    )

    assert result.plan == "free"
    assert result.active_listing_limit == 1


def test_free_employer_with_one_published_listing_is_blocked(
    monkeypatch,
):
    user_id = uuid4()

    monkeypatch.setattr(
        policy_module,
        "get_employer_product_policy",
        lambda db, user_id: SimpleNamespace(
            plan="free",
            active_listing_limit=1,
        ),
    )

    monkeypatch.setattr(
        InternshipRepository,
        "count_published_by_employer",
        lambda db, employer_user_id,
        exclude_internship_id=None: 1,
    )

    with pytest.raises(
        EmployerListingLimitError
    ) as exc_info:
        require_employer_listing_capacity(
            MagicMock(),
            user_id=user_id,
        )

    assert exc_info.value.plan == "free"
    assert exc_info.value.limit == 1
    assert exc_info.value.published_count == 1


def test_employer_pro_is_unlimited_and_skips_count(
    monkeypatch,
):
    user_id = uuid4()

    monkeypatch.setattr(
        policy_module,
        "get_employer_product_policy",
        lambda db, user_id: SimpleNamespace(
            plan="employer_pro",
            active_listing_limit=None,
        ),
    )

    def fail_if_counted(*args, **kwargs):
        raise AssertionError(
            "Pro listing capacity must not query a limit count."
        )

    monkeypatch.setattr(
        InternshipRepository,
        "count_published_by_employer",
        fail_if_counted,
    )

    result = require_employer_listing_capacity(
        MagicMock(),
        user_id=user_id,
    )

    assert result.plan == "employer_pro"
    assert result.active_listing_limit is None


def test_repository_count_is_owner_and_publication_scoped():
    db = MagicMock()
    db.scalar.return_value = 2

    employer_user_id = uuid4()
    excluded_id = uuid4()

    count = (
        InternshipRepository
        .count_published_by_employer(
            db,
            employer_user_id,
            exclude_internship_id=excluded_id,
        )
    )

    assert count == 2

    statement = str(
        db.scalar.call_args.args[0]
    )

    assert "employer_user_id" in statement
    assert "listing_source" in statement
    assert "publication_status" in statement
    assert "internship_listings.id" in statement


def test_create_and_admin_reopen_wiring_are_serialized():
    employer_source = Path(
        "backend/app/api/v1/endpoints/internships.py"
    ).read_text(
        encoding="utf-8"
    )

    admin_source = Path(
        "backend/app/api/v1/endpoints/admin_internships.py"
    ).read_text(
        encoding="utf-8"
    )

    create_start = employer_source.index(
        "def create_internship("
    )
    create_end = employer_source.index(
        '@router.get("",',
        create_start,
    )
    create_block = employer_source[
        create_start:create_end
    ]

    create_lock = create_block.index(
        "lock_for_update=True"
    )
    create_capacity = create_block.index(
        "require_employer_listing_capacity("
    )
    create_write = create_block.index(
        "create_employer_listing("
    )

    assert (
        create_lock
        < create_capacity
        < create_write
    )

    reopen_start = admin_source.index(
        "def reopen_admin_internship("
    )
    reopen_block = admin_source[
        reopen_start:
    ]

    org_lock = reopen_block.index(
        "get_by_id_for_update("
    )
    capacity = reopen_block.index(
        "require_employer_listing_capacity("
    )
    reopen_write = reopen_block.index(
        "reopen_listing("
    )

    assert (
        org_lock
        < capacity
        < reopen_write
    )


def test_admin_reopen_excludes_listing_being_reopened():
    source = Path(
        "backend/app/api/v1/endpoints/admin_internships.py"
    ).read_text(
        encoding="utf-8"
    )

    reopen_start = source.index(
        "def reopen_admin_internship("
    )
    block = source[reopen_start:]

    assert (
        "exclude_internship_id=snapshot.id"
        in block
    )
