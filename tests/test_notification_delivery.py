
"""Gate 6C server-side Expo push delivery tests."""

from __future__ import annotations

import json
from uuid import uuid4

from app.db.models import (
    PushDevice,
    UserNotification,
)
from app.repositories.notification import (
    NotificationRepository,
)
from app.services.notification_delivery import (
    deliver_notification,
)

from tests.db import TestingSessionLocal


class _FakeResponse:
    def __init__(
        self,
        payload,
    ):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        return False

    def read(self):
        return json.dumps(
            self.payload
        ).encode(
            "utf-8"
        )


def test_delivery_localizes_and_sends_registered_device(
    monkeypatch,
):
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        device = PushDevice(
            user_id=user_id,
            expo_push_token=(
                "ExponentPushToken["
                "gate6-delivery-tr]"
            ),
            platform="android",
            locale="tr",
            enabled=True,
        )

        notification = UserNotification(
            recipient_user_id=user_id,
            event_type="listing_published",
            entity_type="internship",
            entity_id=uuid4(),
            data_json="{}",
        )

        db.add_all(
            [
                device,
                notification,
            ]
        )
        db.commit()

        notification_id = (
            notification.id
        )
    finally:
        db.close()

    captured = {}

    def fake_urlopen(
        request,
        timeout,
    ):
        captured["timeout"] = timeout
        captured["body"] = json.loads(
            request.data.decode(
                "utf-8"
            )
        )

        return _FakeResponse(
            {
                "data": [
                    {
                        "status": "ok",
                        "id":
                            "expo-ticket-1",
                    }
                ]
            }
        )

    monkeypatch.setattr(
        (
            "app.services.notification_delivery."
            "request.urlopen"
        ),
        fake_urlopen,
    )

    db = TestingSessionLocal()

    try:
        result = deliver_notification(
            db,
            notification_id=notification_id,
        )

        db.commit()
    finally:
        db.close()

    assert result.attempted == 1
    assert result.accepted == 1
    assert result.disabled == 0

    message = captured["body"][0]

    assert (
        message["title"]
        == "Fırsat yayınlandı"
    )

    assert (
        message["data"][
            "notification_id"
        ]
        == str(notification_id)
    )

    assert captured["timeout"] == 10


def test_device_not_registered_is_disabled(
    monkeypatch,
):
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        device = PushDevice(
            user_id=user_id,
            expo_push_token=(
                "ExponentPushToken["
                "gate6-dead-device]"
            ),
            platform="ios",
            locale="en",
            enabled=True,
        )

        notification = UserNotification(
            recipient_user_id=user_id,
            event_type=(
                "application_status_changed"
            ),
            data_json=json.dumps(
                {
                    "status":
                        "accepted",
                }
            ),
        )

        db.add_all(
            [
                device,
                notification,
            ]
        )

        db.commit()

        notification_id = (
            notification.id
        )
        device_id = device.id
    finally:
        db.close()

    monkeypatch.setattr(
        (
            "app.services.notification_delivery."
            "request.urlopen"
        ),
        lambda request, timeout: _FakeResponse(
            {
                "data": [
                    {
                        "status": "error",
                        "details": {
                            "error":
                                "DeviceNotRegistered"
                        },
                    }
                ]
            }
        ),
    )

    db = TestingSessionLocal()

    try:
        result = deliver_notification(
            db,
            notification_id=notification_id,
        )

        db.commit()

        refreshed = db.get(
            PushDevice,
            device_id,
        )

        assert refreshed is not None
        assert refreshed.enabled is False
    finally:
        db.close()

    assert result.attempted == 1
    assert result.accepted == 0
    assert result.disabled == 1


def test_notification_enqueues_only_after_commit_when_device_exists(
    monkeypatch,
):
    user_id = uuid4()
    queued = []

    monkeypatch.setattr(
        (
            "app.services.notification_enqueue."
            "enqueue_notification_delivery"
        ),
        lambda notification_id: queued.append(
            str(notification_id)
        ),
    )

    db = TestingSessionLocal()

    try:
        db.add(
            PushDevice(
                user_id=user_id,
                expo_push_token=(
                    "ExponentPushToken["
                    "gate6-commit-device]"
                ),
                platform="android",
                locale="en",
                enabled=True,
            )
        )

        db.commit()

        notification = (
            NotificationRepository.create(
                db,
                recipient_user_id=user_id,
                event_type=(
                    "listing_changes_requested"
                ),
            )
        )

        notification_id = str(
            notification.id
        )

        # flush/create alone must not enqueue before commit.
        assert queued == []

        db.commit()

        assert queued == [
            notification_id
        ]
    finally:
        db.close()


def test_notification_without_device_does_not_enqueue(
    monkeypatch,
):
    user_id = uuid4()
    queued = []

    monkeypatch.setattr(
        (
            "app.services.notification_enqueue."
            "enqueue_notification_delivery"
        ),
        lambda notification_id: queued.append(
            str(notification_id)
        ),
    )

    db = TestingSessionLocal()

    try:
        NotificationRepository.create(
            db,
            recipient_user_id=user_id,
            event_type="test_event",
        )

        db.commit()
    finally:
        db.close()

    assert queued == []
