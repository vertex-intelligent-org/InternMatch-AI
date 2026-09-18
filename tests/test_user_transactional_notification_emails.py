"""User-facing transactional notification email contracts."""

from __future__ import annotations

import json
from uuid import uuid4

from app.core.config import settings
from app.db.models import (
    PushDevice,
    UserNotification,
)
from app.repositories.notification import (
    NotificationRepository,
)
from app.services import (
    notification_user_email_delivery as email_delivery,
)

from tests.db import TestingSessionLocal


class _FakeSMTP:
    sent_messages = []

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        pass

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        return False

    def ehlo(self):
        return None

    def starttls(
        self,
        *,
        context,
    ):
        return None

    def login(
        self,
        username,
        password,
    ):
        return None

    def send_message(
        self,
        message,
        *,
        from_addr,
        to_addrs,
    ):
        self.__class__.sent_messages.append(
            (
                message,
                from_addr,
                to_addrs,
            )
        )


def _enable_email(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "USER_NOTIFICATION_EMAILS_ENABLED",
        True,
    )
    monkeypatch.setattr(
        settings,
        "SMTP_HOST",
        "smtp.example.com",
    )
    monkeypatch.setattr(
        settings,
        "SMTP_PORT",
        587,
    )
    monkeypatch.setattr(
        settings,
        "SMTP_USERNAME",
        "",
    )
    monkeypatch.setattr(
        settings,
        "SMTP_PASSWORD",
        "",
    )
    monkeypatch.setattr(
        settings,
        "SMTP_FROM_EMAIL",
        "notifications@example.com",
    )
    monkeypatch.setattr(
        settings,
        "SMTP_FROM_NAME",
        "InternMatch AI",
    )
    monkeypatch.setattr(
        settings,
        "SMTP_SECURITY",
        "starttls",
    )


def test_user_email_event_filter():
    assert email_delivery.is_user_notification_email_event(
        event_type="application_submitted",
        data={},
    )

    assert email_delivery.is_user_notification_email_event(
        event_type="application_status_changed",
        data={
            "status": "accepted",
        },
    )

    assert not email_delivery.is_user_notification_email_event(
        event_type="application_status_changed",
        data={
            "status": "saved",
        },
    )

    assert not email_delivery.is_user_notification_email_event(
        event_type="listing_review_requested",
        data={},
    )


def test_user_email_is_branded_html_with_text_fallback(
    monkeypatch,
):
    _enable_email(
        monkeypatch
    )

    _FakeSMTP.sent_messages = []

    monkeypatch.setattr(
        email_delivery.smtplib,
        "SMTP",
        _FakeSMTP,
    )

    monkeypatch.setattr(
        email_delivery,
        "_recipient_email",
        lambda user_id:
            "student@example.com",
    )

    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        db.add(
            PushDevice(
                user_id=user_id,
                expo_push_token=(
                    "ExponentPushToken[user-email-test]"
                ),
                platform="ios",
                locale="en",
                enabled=True,
            )
        )

        notification = UserNotification(
            recipient_user_id=user_id,
            event_type=(
                "application_status_changed"
            ),
            entity_type="application",
            entity_id=uuid4(),
            data_json=json.dumps(
                {
                    "status": "accepted",
                    "listing_title":
                        "AI Engineering Internship",
                    "company":
                        "Example Labs",
                }
            ),
        )

        db.add(notification)
        db.commit()
        db.refresh(notification)

        result = (
            email_delivery
            .deliver_user_notification_email(
                db,
                notification_id=notification.id,
            )
        )

        assert result.attempted == 1
        assert result.sent == 1
        assert len(
            _FakeSMTP.sent_messages
        ) == 1

        message, from_addr, recipients = (
            _FakeSMTP.sent_messages[0]
        )

        assert (
            message["To"]
            == "student@example.com"
        )
        assert (
            "accepted"
            in message["Subject"].lower()
        )
        assert (
            from_addr
            == "notifications@example.com"
        )
        assert recipients == [
            "student@example.com"
        ]

        plain = message.get_body(
            preferencelist=("plain",)
        )

        html = message.get_body(
            preferencelist=("html",)
        )

        assert plain is not None
        assert html is not None

        assert (
            "AI Engineering Internship"
            in plain.get_content()
        )

        assert (
            "InternMatch AI"
            in html.get_content()
        )

        assert (
            "#0B5F70"
            in html.get_content()
        )
    finally:
        db.close()


def test_user_email_queue_runs_only_after_commit(
    monkeypatch,
):
    _enable_email(
        monkeypatch
    )

    enqueued = []

    monkeypatch.setattr(
        (
            "app.services.notification_enqueue."
            "enqueue_user_notification_email_delivery"
        ),
        lambda notification_id:
            enqueued.append(
                str(notification_id)
            ),
    )

    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        notification = (
            NotificationRepository.create(
                db,
                recipient_user_id=user_id,
                event_type=(
                    "application_status_changed"
                ),
                entity_type="application",
                entity_id=uuid4(),
                data={
                    "status": "accepted",
                },
                dedupe_key=(
                    "user-email-after-commit:"
                    + str(uuid4())
                ),
            )
        )

        assert enqueued == []

        notification_id = str(
            notification.id
        )

        db.commit()

        assert enqueued == [
            notification_id
        ]
    finally:
        db.close()


def test_user_email_queue_is_cleared_on_rollback(
    monkeypatch,
):
    _enable_email(
        monkeypatch
    )

    enqueued = []

    monkeypatch.setattr(
        (
            "app.services.notification_enqueue."
            "enqueue_user_notification_email_delivery"
        ),
        lambda notification_id:
            enqueued.append(
                str(notification_id)
            ),
    )

    db = TestingSessionLocal()

    try:
        NotificationRepository.create(
            db,
            recipient_user_id=uuid4(),
            event_type=(
                "application_status_changed"
            ),
            entity_type="application",
            entity_id=uuid4(),
            data={
                "status": "rejected",
            },
        )

        db.rollback()

        assert enqueued == []
    finally:
        db.close()
