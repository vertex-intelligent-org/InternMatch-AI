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
            result=model.result,
            error=model.error,
            updated_at=model.updated_at,
        )
