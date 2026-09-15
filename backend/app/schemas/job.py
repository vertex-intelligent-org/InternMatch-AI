"""
Processing Job API Response Schemas
Provides Pydantic response schema for job status tracking.
"""

from datetime import datetime
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AIJobAcceptedResponse(BaseModel):
    """Accepted response for a durable asynchronous AI operation."""

    job_id: UUID
    status: Literal["queued"]
    message: str

    model_config = ConfigDict(from_attributes=True)



_PRIVATE_JOB_RESULT_KEYS = frozenset(
    {
        "storage_path",
        "cv_storage_path",
        "avatar_storage_path",
        "evidence_storage_path",
        "extracted_profile",
    }
)

_CV_PUBLIC_RESULT_KEYS = frozenset(
    {
        "requires_confirmation",
        "confirmed",
        "reason",
        "profile_id",
        "cancelled",
        "cancel_requested",
        "cancel_reason",
        "error",
    }
)


def _strip_private_job_result_value(
    value: Any,
) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}

        for raw_key, raw_value in value.items():
            key = str(raw_key)

            if (
                key in _PRIVATE_JOB_RESULT_KEYS
                or key.endswith("_storage_path")
            ):
                continue

            sanitized[key] = (
                _strip_private_job_result_value(
                    raw_value
                )
            )

        return sanitized

    if isinstance(value, list):
        return [
            _strip_private_job_result_value(
                item
            )
            for item in value
        ]

    return value


def _sanitize_public_processing_job_result(
    *,
    job_type: Any,
    result: Any,
) -> Optional[Dict[str, Any]]:
    """
    Convert durable internal job metadata into the public polling contract.

    Storage object paths and extracted CV payloads are server-only data.
    CV extraction uses a strict allowlist because confirmation needs only
    state markers, never the pending storage object or extracted profile.
    """
    if not isinstance(result, dict):
        return None

    sanitized = (
        _strip_private_job_result_value(
            result
        )
    )

    if not isinstance(
        sanitized,
        dict,
    ):
        return None

    if job_type == "cv_extraction":
        return {
            key: sanitized[key]
            for key in _CV_PUBLIC_RESULT_KEYS
            if key in sanitized
        }

    return sanitized


class ProcessingJobResponse(BaseModel):
    """Response schema for GET /api/v1/jobs/{job_id} endpoint."""

    job_id: UUID
    status: Literal["queued", "processing", "completed", "failed"]
    progress_percent: int = Field(..., ge=0, le=100)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, model: Any) -> "ProcessingJobResponse":
        """Explicit mapping factory method converting ProcessingJob model to response schema."""
        return cls(
            job_id=model.id,
            status=model.status,
            progress_percent=model.progress_percent,
            result=_sanitize_public_processing_job_result(
                job_type=getattr(model, "job_type", None),
                result=model.result,
            ),
            error=model.error,
            updated_at=model.updated_at,
        )
