
"""Durable notification inbox and push-device repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.db.models import (
    EmployerOrganization,
    InternshipListing,
    PushDevice,
    StudentProfile,
    UserNotification,
)
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

PENDING_PUSH_IDS_KEY = (
    "internmatch_pending_notification_push_ids"
)


@event.listens_for(
    Session,
    "after_commit",
)
def _enqueue_committed_notification_pushes(
    session: Session,
) -> None:
    """
    Dispatch push work only after the notification transaction committed.

    Redis/RQ failure is deliberately isolated from the already-committed
    durable inbox event.
    """
    pending = list(
        session.info.pop(
            PENDING_PUSH_IDS_KEY,
            [],
        )
    )

    if not pending:
        return

    from app.services.notification_enqueue import (
        enqueue_notification_delivery,
    )

    for notification_id in pending:
        try:
            enqueue_notification_delivery(
                notification_id
            )
        except Exception:
            # Durable inbox remains authoritative even if
            # transient queue delivery is unavailable.
            continue


class NotificationRepository:
    @staticmethod
    def create_for_organization_owner(
        db: Session,
        *,
        organization_id: UUID,
        event_type: str,
        entity_type: str,
        entity_id: UUID,
        data: dict[str, Any],
        dedupe_key: str,
    ) -> UserNotification | None:
        """
        Create one durable notification for the authoritative organization owner.

        The caller supplies only non-sensitive user-facing event metadata.
        Private compliance evidence, internal notes, and admin-only review data
        must never enter this notification contract.
        """
        organization = db.get(
            EmployerOrganization,
            organization_id,
        )

        if organization is None:
            return None

        return NotificationRepository.create(
            db,
            recipient_user_id=(
                organization.owner_user_id
            ),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            data=data,
            dedupe_key=dedupe_key,
        )

    @staticmethod
    def create(
        db: Session,
        *,
        recipient_user_id: UUID,
        event_type: str,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        data: dict[str, Any] | None = None,
        dedupe_key: str | None = None,
    ) -> UserNotification:
        if dedupe_key:
            existing = db.scalar(
                select(UserNotification).where(
                    UserNotification.dedupe_key
                    == dedupe_key
                )
            )

            if existing is not None:
                return existing

        notification = UserNotification(
            recipient_user_id=recipient_user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            data_json=json.dumps(
                data or {},
                separators=(",", ":"),
                sort_keys=True,
            ),
        )

        if dedupe_key:
            notification.dedupe_key = dedupe_key

        db.add(notification)
        db.flush()

        push_device_exists = db.scalar(
            select(PushDevice.id)
            .where(
                PushDevice.user_id
                == recipient_user_id,
                PushDevice.enabled.is_(True),
            )
            .limit(1)
        )

        if push_device_exists is not None:
            pending = db.info.setdefault(
                PENDING_PUSH_IDS_KEY,
                [],
            )

            notification_id = str(
                notification.id
            )

            if notification_id not in pending:
                pending.append(
                    notification_id
                )

        return notification

    @staticmethod
    def list_for_user(
        db: Session,
        *,
        user_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[UserNotification], int]:
        predicate = (
            UserNotification.recipient_user_id
            == user_id
        )

        total = int(
            db.scalar(
                select(func.count())
                .select_from(UserNotification)
                .where(predicate)
            )
            or 0
        )

        items = list(
            db.scalars(
                select(UserNotification)
                .where(predicate)
                .order_by(
                    UserNotification.created_at.desc(),
                    UserNotification.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            ).all()
        )

        return items, total

    @staticmethod
    def unread_count(
        db: Session,
        *,
        user_id: UUID,
    ) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(UserNotification)
                .where(
                    UserNotification.recipient_user_id
                    == user_id,
                    UserNotification.read_at.is_(None),
                )
            )
            or 0
        )

    @staticmethod
    def mark_read(
        db: Session,
        *,
        user_id: UUID,
        notification_id: UUID,
    ) -> UserNotification | None:
        notification = db.scalar(
            select(UserNotification).where(
                UserNotification.id
                == notification_id,
                UserNotification.recipient_user_id
                == user_id,
            )
        )

        if notification is None:
            return None

        if notification.read_at is None:
            notification.read_at = datetime.now(
                timezone.utc
            )
            db.flush()

        return notification

    @staticmethod
    def mark_all_read(
        db: Session,
        *,
        user_id: UUID,
    ) -> int:
        unread = list(
            db.scalars(
                select(UserNotification).where(
                    UserNotification.recipient_user_id
                    == user_id,
                    UserNotification.read_at.is_(None),
                )
            ).all()
        )

        now = datetime.now(
            timezone.utc
        )

        for notification in unread:
            notification.read_at = now

        db.flush()
        return len(unread)

    @staticmethod
    def register_device(
        db: Session,
        *,
        user_id: UUID,
        expo_push_token: str,
        platform: str,
        locale: str,
    ) -> PushDevice:
        device = db.scalar(
            select(PushDevice).where(
                PushDevice.expo_push_token
                == expo_push_token
            )
        )

        now = datetime.now(
            timezone.utc
        )

        if device is None:
            device = PushDevice(
                user_id=user_id,
                expo_push_token=expo_push_token,
                platform=platform,
                locale=locale,
                enabled=True,
                created_at=now,
                updated_at=now,
            )
            db.add(device)
        else:
            # A token can move between authenticated accounts on a shared
            # device; the most recent authenticated registration owns it.
            device.user_id = user_id
            device.platform = platform
            device.locale = locale
            device.enabled = True
            device.updated_at = now

        db.flush()
        return device

    @staticmethod
    def disable_device(
        db: Session,
        *,
        user_id: UUID,
        expo_push_token: str,
    ) -> bool:
        device = db.scalar(
            select(PushDevice).where(
                PushDevice.user_id == user_id,
                PushDevice.expo_push_token
                == expo_push_token,
            )
        )

        if device is None:
            return False

        device.enabled = False
        device.updated_at = datetime.now(
            timezone.utc
        )
        db.flush()
        return True

    @staticmethod
    def emit_application_status(
        db: Session,
        *,
        application,
        status: str,
    ) -> UserNotification | None:
        if status == "applied":
            if application.internship_id is None:
                return None

            listing = db.get(
                InternshipListing,
                application.internship_id,
            )

            recipient = (
                listing.employer_user_id
                if listing is not None
                else None
            )

            if recipient is None:
                return None

            return NotificationRepository.create(
                db,
                recipient_user_id=recipient,
                event_type="application_submitted",
                entity_type="application",
                entity_id=application.id,
                data={
                    "application_id": str(
                        application.id
                    ),
                    "internship_id": str(
                        application.internship_id
                    ),
                    "status": status,
                },
                dedupe_key=(
                    f"application:{application.id}:"
                    "submitted"
                ),
            )

        if status not in {
            "interviewing",
            "accepted",
            "rejected",
        }:
            return None

        profile = db.get(
            StudentProfile,
            application.student_id,
        )

        if profile is None:
            return None

        recipient = profile.user_id

        return NotificationRepository.create(
            db,
            recipient_user_id=recipient,
            event_type=(
                "application_status_changed"
            ),
            entity_type="application",
            entity_id=application.id,
            data={
                "application_id": str(
                    application.id
                ),
                "internship_id": str(
                    application.internship_id
                ),
                "status": status,
            },
            dedupe_key=(
                f"application:{application.id}:"
                f"status:{status}"
            ),
        )
