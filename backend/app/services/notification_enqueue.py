
"""Redis/RQ enqueue boundary for Expo notification delivery."""

from uuid import UUID

from redis import Redis
from rq import Queue

from app.core.config import settings


def enqueue_notification_delivery(
    notification_id: UUID | str,
):
    """
    Enqueue one durable notification delivery job.

    Notification creation is committed before this function is invoked.
    Push failure must never roll back the user-facing durable inbox event.
    """
    normalized_id = str(
        notification_id
    )

    queue_name = (
        getattr(
            settings,
            "RQ_QUEUE_NAME",
            None,
        )
        or "default"
    )

    redis_connection = Redis.from_url(
        settings.REDIS_URL
    )

    queue = Queue(
        queue_name,
        connection=redis_connection,
    )

    return queue.enqueue(
        (
            "tasks.notification_delivery."
            "run_notification_delivery"
        ),
        normalized_id,
        job_id=(
            "notification:"
            + normalized_id
        ),
        job_timeout=30,
        result_ttl=300,
        failure_ttl=86400,
    )
