
"""Notification API schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    id: UUID
    event_type: str
    entity_type: str | None = None
    entity_id: UUID | None = None
    data: dict[str, Any] = Field(
        default_factory=dict
    )
    read_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread_count: int
    limit: int
    offset: int


class NotificationUnreadResponse(BaseModel):
    unread_count: int


class MarkAllNotificationsReadResponse(BaseModel):
    updated: int
    unread_count: int


class PushDeviceRegisterRequest(BaseModel):
    expo_push_token: str = Field(
        ...,
        min_length=10,
        max_length=512,
    )
    platform: Literal[
        "ios",
        "android",
    ]
    locale: str = Field(
        default="en",
        min_length=2,
        max_length=16,
    )


class PushDeviceDisableRequest(BaseModel):
    expo_push_token: str = Field(
        ...,
        min_length=10,
        max_length=512,
    )


class PushDeviceResponse(BaseModel):
    registered: bool
