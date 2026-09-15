from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.profile import (
    StudentProfileCreateUpdate,
    StudentProfileResponse,
)
from app.schemas.job import ProcessingJobResponse


def test_public_profile_write_rejects_client_cv_storage_path():
    with pytest.raises(ValidationError):
        StudentProfileCreateUpdate(
            full_name="Candidate",
            cv_storage_path=(
                "candidate-id/private.pdf"
            ),
        )


def test_profile_response_exposes_boolean_has_cv_only():
    response = StudentProfileResponse(
        id=uuid4(),
        user_id=uuid4(),
        full_name="Candidate",
        has_cv=True,
    )

    payload = response.model_dump()

    assert payload["has_cv"] is True
    assert "cv_storage_path" not in payload
    assert "cv_url" not in payload


def test_cv_processing_job_public_result_is_strictly_minimized():
    model = SimpleNamespace(
        id=uuid4(),
        job_type="cv_extraction",
        status="completed",
        progress_percent=100,
        result={
            "requires_confirmation": True,
            "confirmed": False,
            "reason": (
                "possible_identity_mismatch"
            ),
            "extracted_name": "Candidate B",
            "existing_name": "Candidate A",
            "cv_storage_path": (
                "user-id/resume.pdf"
            ),
            "extracted_profile": {
                "full_name": "Candidate B",
                "skills": ["Python"],
                "storage_path": (
                    "internal/other.pdf"
                ),
            },
        },
        error=None,
        updated_at=datetime.now(
            timezone.utc
        ),
    )

    response = (
        ProcessingJobResponse.from_orm_model(
            model
        )
    )

    assert response.result == {
        "requires_confirmation": True,
        "confirmed": False,
        "reason": (
            "possible_identity_mismatch"
        ),
    }


def test_confirmed_cv_job_keeps_only_public_reconciliation_fields():
    model = SimpleNamespace(
        id=uuid4(),
        job_type="cv_extraction",
        status="completed",
        progress_percent=100,
        result={
            "requires_confirmation": False,
            "confirmed": True,
            "profile_id": "profile-123",
            "confirmed_at": (
                "2026-09-15T00:00:00Z"
            ),
            "cv_storage_path": (
                "user/private.pdf"
            ),
            "extracted_profile": {
                "full_name": "Candidate",
            },
        },
        error=None,
        updated_at=datetime.now(
            timezone.utc
        ),
    )

    response = (
        ProcessingJobResponse.from_orm_model(
            model
        )
    )

    assert response.result == {
        "requires_confirmation": False,
        "confirmed": True,
        "profile_id": "profile-123",
    }


def test_non_cv_job_result_preserves_public_data_but_strips_storage_metadata():
    model = SimpleNamespace(
        id=uuid4(),
        job_type="match_calculation",
        status="completed",
        progress_percent=100,
        result={
            "match_count": 4,
            "storage_path": (
                "internal/debug.json"
            ),
            "debug": {
                "safe": "ok",
                "cv_storage_path": (
                    "private/resume.pdf"
                ),
            },
        },
        error=None,
        updated_at=datetime.now(
            timezone.utc
        ),
    )

    response = (
        ProcessingJobResponse.from_orm_model(
            model
        )
    )

    assert response.result == {
        "match_count": 4,
        "debug": {
            "safe": "ok",
        },
    }


def test_public_cv_job_response_never_serializes_internal_cv_payload():
    model = SimpleNamespace(
        id=uuid4(),
        job_type="cv_extraction",
        status="completed",
        progress_percent=100,
        result={
            "requires_confirmation": True,
            "cv_storage_path": (
                "secret/path.pdf"
            ),
            "extracted_profile": {
                "headline": (
                    "internal candidate data"
                ),
            },
        },
        error=None,
        updated_at=datetime.now(
            timezone.utc
        ),
    )

    serialized = (
        ProcessingJobResponse.from_orm_model(
            model
        ).model_dump_json()
    )

    assert "cv_storage_path" not in serialized
    assert "extracted_profile" not in serialized
    assert "secret/path.pdf" not in serialized
