"""Regression tests for RQ-safe notification job IDs."""

import re
from uuid import uuid4

from app.services import notification_enqueue


def test_notification_job_ids_are_rq_safe(
    monkeypatch,
):
    captured = []

    class FakeQueue:
        def __init__(
            self,
            *args,
            **kwargs,
        ):
            pass

        def enqueue(
            self,
            *args,
            **kwargs,
        ):
            captured.append(
                kwargs["job_id"]
            )
            return object()

    monkeypatch.setattr(
        notification_enqueue,
        "Queue",
        FakeQueue,
    )

    monkeypatch.setattr(
        notification_enqueue.Redis,
        "from_url",
        lambda *args, **kwargs: object(),
    )

    notification_id = uuid4()

    notification_enqueue.enqueue_notification_delivery(
        notification_id
    )

    notification_enqueue.enqueue_admin_alert_email_delivery(
        notification_id
    )

    notification_enqueue.enqueue_user_notification_email_delivery(
        notification_id
    )

    assert len(captured) == 3

    assert captured[0].startswith(
        "notification-"
    )

    assert captured[1].startswith(
        "notification-email-"
    )

    assert captured[2].startswith(
        "user-notification-email-"
    )

    for job_id in captured:
        assert re.fullmatch(
            r"[A-Za-z0-9_-]+",
            job_id,
        )
