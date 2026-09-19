"""RQ enqueue boundary for candidate opportunity alert fan-out."""

from uuid import UUID

from redis import Redis
from rq import Queue, Retry

from app.core.config import settings


def enqueue_new_opportunity_alert_fanout(
    internship_id: UUID | str,
):
    normalized_id = str(
        internship_id
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
            "tasks.opportunity_alert_fanout."
            "run_new_opportunity_alert_fanout"
        ),
        normalized_id,
        job_id=(
            "opportunity-alert-fanout-"
            + normalized_id
        ),
        job_timeout=120,
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
