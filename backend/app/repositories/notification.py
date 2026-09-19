
"""Durable notification inbox and push-device repository."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.config import settings
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

PENDING_ADMIN_EMAIL_IDS_KEY = (
    "internmatch_pending_admin_email_ids"
)

PENDING_USER_EMAIL_IDS_KEY = (
    "internmatch_pending_user_email_ids"
)


def _configured_admin_user_ids() -> list[UUID]:
    values: list[UUID] = []

    for raw_value in (
        settings.ADMIN_USER_IDS
        or ""
    ).split(","):
        candidate = raw_value.strip()

        if not candidate:
            continue

        try:
            value = UUID(candidate)
        except (
            TypeError,
            ValueError,
        ):
            # Administrative authorization itself fails closed
            # elsewhere. Alert creation must never break the
            # user's successful business transaction.
            continue

        if value not in values:
            values.append(value)

    return sorted(
        values,
        key=str,
    )


@event.listens_for(
    Session,
    "after_commit",
)
def _enqueue_committed_notification_deliveries(
    session: Session,
) -> None:
    """
    Dispatch asynchronous notification work only after commit.

    Push/email transport failures must never roll back a successful
    application, organization submission, listing submission, or
    compliance submission.
    """
    pending_push = list(
        session.info.pop(
            PENDING_PUSH_IDS_KEY,
            [],
        )
    )

    pending_email = list(
        session.info.pop(
            PENDING_ADMIN_EMAIL_IDS_KEY,
            [],
        )
    )

    pending_user_email = list(
        session.info.pop(
            PENDING_USER_EMAIL_IDS_KEY,
            [],
        )
    )

    if not (
        pending_push
        or pending_email
        or pending_user_email
    ):
        return

    from app.services.notification_enqueue import (
        enqueue_admin_alert_email_delivery,
        enqueue_notification_delivery,
        enqueue_user_notification_email_delivery,
    )

    for notification_id in pending_push:
        try:
            enqueue_notification_delivery(
                notification_id
            )
        except Exception:
            continue

    for notification_id in pending_email:
        try:
            enqueue_admin_alert_email_delivery(
                notification_id
            )
        except Exception:
            continue

    for notification_id in pending_user_email:
        try:
            enqueue_user_notification_email_delivery(
                notification_id
            )
        except Exception:
            continue


@event.listens_for(
    Session,
    "after_rollback",
)
def _clear_rolled_back_notification_deliveries(
    session: Session,
) -> None:
    session.info.pop(
        PENDING_PUSH_IDS_KEY,
        None,
    )
    session.info.pop(
        PENDING_ADMIN_EMAIL_IDS_KEY,
        None,
    )
    session.info.pop(
        PENDING_USER_EMAIL_IDS_KEY,
        None,
    )


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
    def create_for_admins(
        db: Session,
        *,
        event_type: str,
        entity_type: str,
        entity_id: UUID,
        data: dict[str, Any],
        dedupe_key: str,
    ) -> list[UserNotification]:
        """
        Create one durable inbox notification for every configured admin.

        Exactly one deterministic admin notification is selected as the
        email-delivery anchor so multiple ADMIN_USER_IDS never cause
        duplicate operational emails to ADMIN_ALERT_EMAILS.
        """
        admin_user_ids = (
            _configured_admin_user_ids()
        )

        if not admin_user_ids:
            return []

        notifications: list[
            UserNotification
        ] = []

        primary_was_created = False

        for index, admin_user_id in enumerate(
            admin_user_ids
        ):
            admin_dedupe_key = (
                f"{dedupe_key}:admin:"
                f"{admin_user_id}"
            )

            existing = db.scalar(
                select(UserNotification).where(
                    UserNotification.dedupe_key
                    == admin_dedupe_key
                )
            )

            if existing is not None:
                notifications.append(
                    existing
                )
                continue

            created = (
                NotificationRepository.create(
                    db,
                    recipient_user_id=(
                        admin_user_id
                    ),
                    event_type=event_type,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    data=data,
                    dedupe_key=(
                        admin_dedupe_key
                    ),
                )
            )

            notifications.append(created)

            if index == 0:
                primary_was_created = True

        if (
            primary_was_created
            and notifications
        ):
            pending = db.info.setdefault(
                PENDING_ADMIN_EMAIL_IDS_KEY,
                [],
            )

            primary_id = str(
                notifications[0].id
            )

            if primary_id not in pending:
                pending.append(primary_id)

        return notifications

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

        from app.services.notification_user_email_delivery import (
            is_user_notification_email_event,
            user_email_delivery_configured,
        )

        if (
            user_email_delivery_configured()
            and is_user_notification_email_event(
                event_type=event_type,
                data=data or {},
            )
        ):
            pending_email = db.info.setdefault(
                PENDING_USER_EMAIL_IDS_KEY,
                [],
            )

            email_notification_id = str(
                notification.id
            )

            if (
                email_notification_id
                not in pending_email
            ):
                pending_email.append(
                    email_notification_id
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
    def mark_unread(
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

        if notification.read_at is not None:
            notification.read_at = None
            db.flush()

        return notification

    @staticmethod
    def delete_for_user(
        db: Session,
        *,
        user_id: UUID,
        notification_id: UUID,
    ) -> bool:
        notification = db.scalar(
            select(UserNotification).where(
                UserNotification.id
                == notification_id,
                UserNotification.recipient_user_id
                == user_id,
            )
        )

        if notification is None:
            return False

        db.delete(notification)
        db.flush()

        return True

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

            if (
                listing is not None
                and recipient is None
                and listing.listing_source
                == "curated"
                and listing.employer_organization_id
                is None
            ):
                metadata = (
                    listing.metadata_json
                    if isinstance(
                        listing.metadata_json,
                        dict,
                    )
                    else {}
                )

                if (
                    metadata.get(
                        "created_via"
                    )
                    == "admin_console"
                ):
                    profile = db.get(
                        StudentProfile,
                        application.student_id,
                    )

                    notifications = (
                        NotificationRepository
                        .create_for_admins(
                            db,
                            event_type=(
                                "admin_curated_"
                                "application_submitted"
                            ),
                            entity_type=(
                                "application"
                            ),
                            entity_id=(
                                application.id
                            ),
                            data={
                                "application_id": str(
                                    application.id
                                ),
                                "internship_id": str(
                                    listing.id
                                ),
                                "listing_title":
                                    listing.title,
                                "company":
                                    listing.company,
                                "candidate_name": (
                                    profile.full_name
                                    if profile
                                    is not None
                                    else "Candidate"
                                ),
                                "candidate_user_id": (
                                    str(
                                        profile.user_id
                                    )
                                    if profile
                                    is not None
                                    else None
                                ),
                                "status": status,
                            },
                            dedupe_key=(
                                f"application:"
                                f"{application.id}:"
                                "admin-submitted"
                            ),
                        )
                    )

                    return (
                        notifications[0]
                        if notifications
                        else None
                    )

            if recipient is None:
                return None

            profile = db.get(
                StudentProfile,
                application.student_id,
            )

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
                    "listing_title": (
                        listing.title
                        if listing is not None
                        else ""
                    ),
                    "company": (
                        listing.company
                        if listing is not None
                        else ""
                    ),
                    "candidate_name": (
                        profile.full_name
                        if profile is not None
                        else "Candidate"
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

        listing = (
            db.get(
                InternshipListing,
                application.internship_id,
            )
            if application.internship_id
            is not None
            else None
        )

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
                "listing_title": (
                    listing.title
                    if listing is not None
                    else ""
                ),
                "company": (
                    listing.company
                    if listing is not None
                    else ""
                ),
                "status": status,
            },
            dedupe_key=(
                f"application:{application.id}:"
                f"status:{status}"
            ),
        )
