
"""Authenticated notification inbox and device registration API."""

from __future__ import annotations

import json
from uuid import UUID

from app.core.security import (
    AuthenticatedUser,
    get_current_user,
)
from app.db.session import get_db
from app.repositories.notification import (
    NotificationRepository,
)
from app.repositories.student_profile import (
    StudentProfileRepository,
)
from app.schemas.notification import (
    MarkAllNotificationsReadResponse,
    NotificationListResponse,
    NotificationResponse,
    NotificationUnreadResponse,
    OpportunityAlertPreferenceRequest,
    OpportunityAlertPreferenceResponse,
    PushDeviceDisableRequest,
    PushDeviceRegisterRequest,
    PushDeviceResponse,
)
from app.services.opportunity_alerts import (
    NEW_OPPORTUNITY_ALERT_PREFERENCE,
)
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

router = APIRouter()


def _response(model) -> NotificationResponse:
    try:
        data = json.loads(
            model.data_json or "{}"
        )
    except (TypeError, ValueError):
        data = {}

    if not isinstance(data, dict):
        data = {}

    return NotificationResponse(
        id=model.id,
        event_type=model.event_type,
        entity_type=model.entity_type,
        entity_id=model.entity_id,
        data=data,
        read_at=model.read_at,
        created_at=model.created_at,
    )


@router.get(
    "",
    response_model=NotificationListResponse,
)
def list_my_notifications(
    limit: int = Query(
        default=30,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    items, total = (
        NotificationRepository.list_for_user(
            db,
            user_id=current_user.user_id,
            limit=limit,
            offset=offset,
        )
    )

    unread = (
        NotificationRepository.unread_count(
            db,
            user_id=current_user.user_id,
        )
    )

    return NotificationListResponse(
        items=[
            _response(item)
            for item in items
        ],
        total=total,
        unread_count=unread,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/unread-count",
    response_model=NotificationUnreadResponse,
)
def get_my_unread_count(
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    return NotificationUnreadResponse(
        unread_count=(
            NotificationRepository.unread_count(
                db,
                user_id=current_user.user_id,
            )
        )
    )


@router.get(
    "/preferences/opportunity-alerts",
    response_model=OpportunityAlertPreferenceResponse,
)
def get_opportunity_alert_preference(
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    profile = (
        StudentProfileRepository.get_by_user_id(
            db,
            user_id=current_user.user_id,
        )
    )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student profile not found.",
        )

    preferences = dict(
        profile.preferences or {}
    )

    return OpportunityAlertPreferenceResponse(
        enabled=(
            preferences.get(
                NEW_OPPORTUNITY_ALERT_PREFERENCE
            )
            is True
        )
    )


@router.put(
    "/preferences/opportunity-alerts",
    response_model=OpportunityAlertPreferenceResponse,
)
def update_opportunity_alert_preference(
    payload: OpportunityAlertPreferenceRequest,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    profile = (
        StudentProfileRepository.get_by_user_id(
            db,
            user_id=current_user.user_id,
        )
    )

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student profile not found.",
        )

    preferences = dict(
        profile.preferences or {}
    )

    preferences[
        NEW_OPPORTUNITY_ALERT_PREFERENCE
    ] = payload.enabled

    StudentProfileRepository.upsert_by_user_id(
        db=db,
        user_id=current_user.user_id,
        full_name=profile.full_name,
        headline=profile.headline,
        preferences=preferences,
    )

    db.commit()

    return OpportunityAlertPreferenceResponse(
        enabled=payload.enabled
    )


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
)
def mark_notification_read(
    notification_id: UUID,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    notification = (
        NotificationRepository.mark_read(
            db,
            user_id=current_user.user_id,
            notification_id=notification_id,
        )
    )

    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )

    db.commit()
    db.refresh(notification)
    return _response(notification)


@router.post(
    "/read-all",
    response_model=MarkAllNotificationsReadResponse,
)
def mark_all_notifications_read(
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    updated = (
        NotificationRepository.mark_all_read(
            db,
            user_id=current_user.user_id,
        )
    )

    db.commit()

    return MarkAllNotificationsReadResponse(
        updated=updated,
        unread_count=0,
    )


@router.post(
    "/devices",
    response_model=PushDeviceResponse,
)
def register_push_device(
    payload: PushDeviceRegisterRequest,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    token = payload.expo_push_token.strip()

    if not (
        token.startswith("ExponentPushToken[")
        or token.startswith("ExpoPushToken[")
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid Expo push token.",
        )

    NotificationRepository.register_device(
        db,
        user_id=current_user.user_id,
        expo_push_token=token,
        platform=payload.platform,
        locale=payload.locale.lower(),
    )

    db.commit()

    return PushDeviceResponse(
        registered=True
    )


@router.delete(
    "/devices",
    response_model=PushDeviceResponse,
)
def disable_push_device(
    payload: PushDeviceDisableRequest,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    NotificationRepository.disable_device(
        db,
        user_id=current_user.user_id,
        expo_push_token=(
            payload.expo_push_token.strip()
        ),
    )

    db.commit()

    # Idempotent device logout/unregister.
    return PushDeviceResponse(
        registered=False
    )
