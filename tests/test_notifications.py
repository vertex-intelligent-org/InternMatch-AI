
"""Gate 6 durable notification platform contracts."""

from uuid import uuid4

import pytest
from app.db.models import (
    PushDevice,
    UserNotification,
)
from app.repositories.notification import (
    NotificationRepository,
)
from fastapi.testclient import TestClient

from tests.db import TestingSessionLocal

pytestmark = pytest.mark.usefixtures(
    "mock_supabase_auth"
)


@pytest.fixture(autouse=True)
def clean_notifications():
    db = TestingSessionLocal()

    try:
        db.query(PushDevice).delete()
        db.query(UserNotification).delete()
        db.commit()
    finally:
        db.close()

    yield

    db = TestingSessionLocal()

    try:
        db.query(PushDevice).delete()
        db.query(UserNotification).delete()
        db.commit()
    finally:
        db.close()


def test_notification_inbox_is_tenant_scoped(
    client: TestClient,
):
    user_a = uuid4()
    user_b = uuid4()

    db = TestingSessionLocal()

    try:
        NotificationRepository.create(
            db,
            recipient_user_id=user_a,
            event_type="application_status_changed",
            data={"status": "accepted"},
        )

        NotificationRepository.create(
            db,
            recipient_user_id=user_b,
            event_type="listing_published",
            data={},
        )

        db.commit()
    finally:
        db.close()

    response = client.get(
        "/api/v1/notifications",
        headers={
            "Authorization":
            f"Bearer valid-user-{user_a}"
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 1
    assert body["unread_count"] == 1
    assert len(body["items"]) == 1
    assert (
        body["items"][0]["event_type"]
        == "application_status_changed"
    )


def test_notification_read_boundary_hides_other_user(
    client: TestClient,
):
    owner = uuid4()
    attacker = uuid4()

    db = TestingSessionLocal()

    try:
        notification = NotificationRepository.create(
            db,
            recipient_user_id=owner,
            event_type="listing_published",
        )

        db.commit()
        notification_id = notification.id
    finally:
        db.close()

    denied = client.post(
        (
            "/api/v1/notifications/"
            f"{notification_id}/read"
        ),
        headers={
            "Authorization":
            f"Bearer valid-user-{attacker}"
        },
    )

    assert denied.status_code == 404

    allowed = client.post(
        (
            "/api/v1/notifications/"
            f"{notification_id}/read"
        ),
        headers={
            "Authorization":
            f"Bearer valid-user-{owner}"
        },
    )

    assert allowed.status_code == 200
    assert allowed.json()["read_at"] is not None


def test_mark_all_notifications_read_is_user_scoped(
    client: TestClient,
):
    user_id = uuid4()
    other_user = uuid4()

    db = TestingSessionLocal()

    try:
        for index in range(2):
            NotificationRepository.create(
                db,
                recipient_user_id=user_id,
                event_type="test_event",
                dedupe_key=f"user:{user_id}:{index}",
            )

        NotificationRepository.create(
            db,
            recipient_user_id=other_user,
            event_type="other_event",
        )

        db.commit()
    finally:
        db.close()

    response = client.post(
        "/api/v1/notifications/read-all",
        headers={
            "Authorization":
            f"Bearer valid-user-{user_id}"
        },
    )

    assert response.status_code == 200
    assert response.json()["updated"] == 2

    other = client.get(
        "/api/v1/notifications/unread-count",
        headers={
            "Authorization":
            f"Bearer valid-user-{other_user}"
        },
    )

    assert other.status_code == 200
    assert other.json()["unread_count"] == 1


def test_push_token_registration_is_authenticated_and_reassignable(
    client: TestClient,
):
    first_user = uuid4()
    second_user = uuid4()
    token = (
        "ExponentPushToken["
        "gate6-device-token"
        "]"
    )

    first = client.post(
        "/api/v1/notifications/devices",
        json={
            "expo_push_token": token,
            "platform": "android",
            "locale": "tr",
        },
        headers={
            "Authorization":
            f"Bearer valid-user-{first_user}"
        },
    )

    assert first.status_code == 200

    second = client.post(
        "/api/v1/notifications/devices",
        json={
            "expo_push_token": token,
            "platform": "ios",
            "locale": "en",
        },
        headers={
            "Authorization":
            f"Bearer valid-user-{second_user}"
        },
    )

    assert second.status_code == 200

    db = TestingSessionLocal()

    try:
        rows = db.query(PushDevice).all()

        assert len(rows) == 1
        assert rows[0].user_id == second_user
        assert rows[0].platform == "ios"
        assert rows[0].enabled is True
    finally:
        db.close()


def test_notification_dedupe_is_idempotent():
    user_id = uuid4()

    db = TestingSessionLocal()

    try:
        first = NotificationRepository.create(
            db,
            recipient_user_id=user_id,
            event_type="same_event",
            dedupe_key="gate6:dedupe:test",
        )

        second = NotificationRepository.create(
            db,
            recipient_user_id=user_id,
            event_type="same_event",
            dedupe_key="gate6:dedupe:test",
        )

        db.commit()

        assert first.id == second.id
        assert (
            db.query(UserNotification).count()
            == 1
        )
    finally:
        db.close()


def test_notification_routes_require_authentication(
    client: TestClient,
):
    assert (
        client.get(
            "/api/v1/notifications"
        ).status_code
        == 401
    )

    assert (
        client.get(
            "/api/v1/notifications/unread-count"
        ).status_code
        == 401
    )
