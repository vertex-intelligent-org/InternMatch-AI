
"""Redis/RQ enqueue boundary for Expo notification delivery."""

from uuid import UUID

from redis import Redis
from rq import Queue, Retry

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
            "notification-"
            + normalized_id
        ),
        job_timeout=30,
        result_ttl=300,
        failure_ttl=86400,
    )


def enqueue_admin_alert_email_delivery(
    notification_id: UUID | str,
):
    """
    Enqueue one administrative email alert.

    The durable UserNotification already committed before this is called.
    SMTP errors are retried by RQ and never affect the original user action.
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
            "tasks.notification_email_delivery."
            "run_notification_email_delivery"
        ),
        normalized_id,
        job_id=(
            "notification-email-"
            + normalized_id
        ),
        job_timeout=30,
        result_ttl=300,
        failure_ttl=86400,
        retry=Retry(
            max=3,
            interval=[
                30,
                120,
                300,
            ],
        ),
    )


def enqueue_user_notification_email_delivery(
    notification_id: UUID | str,
):
    """
    Enqueue one user-facing transactional notification email.

    Delivery happens only after the durable notification transaction commits.
    SMTP/Auth failures are retried asynchronously and never roll back the
    originating product action.
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
            "tasks.notification_user_email_delivery."
            "run_user_notification_email_delivery"
        ),
        normalized_id,
        job_id=(
            "user-notification-email-"
            + normalized_id
        ),
        job_timeout=30,
        result_ttl=300,
        failure_ttl=86400,
        retry=Retry(
            max=3,
            interval=[
                30,
                120,
                300,
            ],
        ),
    )
