"""
InternMatch AI ? Internal Database Heartbeat

Server-only operational endpoint used by the scheduled keep-alive.
It performs exactly one database read: SELECT 1.

No application data is inserted, updated, deleted, or schema-modified.
"""

import hmac
from time import perf_counter

import psycopg2
from app.core.config import settings
from app.core.logging import get_logger
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

logger = get_logger()

router = APIRouter(
    prefix="/api/v1/internal",
)


def _response(
    *,
    status_code: int,
    payload: dict,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
    )


@router.post(
    "/database-heartbeat",
    include_in_schema=False,
)
def database_heartbeat(
    x_heartbeat_secret: str | None = Header(
        default=None,
        alias="X-Heartbeat-Secret",
    ),
) -> JSONResponse:
    """
    Verify the shared secret, then execute SELECT 1 against
    the configured production PostgreSQL database.
    """

    expected_secret = (
        settings.HEARTBEAT_SECRET or ""
    ).strip()

    provided_secret = (
        x_heartbeat_secret or ""
    ).strip()

    if not expected_secret:
        logger.error(
            "database_heartbeat_unavailable"
        )
        return _response(
            status_code=503,
            payload={
                "status": "unavailable",
                "database": "unavailable",
            },
        )

    if (
        not provided_secret
        or not hmac.compare_digest(
            provided_secret,
            expected_secret,
        )
    ):
        return _response(
            status_code=401,
            payload={
                "status": "unauthorized",
            },
        )

    started_at = perf_counter()
    connection = None

    try:
        connection = psycopg2.connect(
            settings.DATABASE_URL,
            connect_timeout=5,
            options="-c statement_timeout=5000",
        )

        connection.autocommit = True

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

        if result != (1,):
            raise RuntimeError(
                "Unexpected heartbeat query result."
            )

        duration_ms = (
            perf_counter() - started_at
        ) * 1000

        logger.info(
            "database_heartbeat_success duration_ms=%.2f",
            duration_ms,
        )

        return _response(
            status_code=200,
            payload={
                "status": "ok",
                "database": "connected",
            },
        )

    except Exception:
        duration_ms = (
            perf_counter() - started_at
        ) * 1000

        logger.warning(
            "database_heartbeat_failed duration_ms=%.2f",
            duration_ms,
        )

        return _response(
            status_code=503,
            payload={
                "status": "unavailable",
                "database": "unavailable",
            },
        )

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
