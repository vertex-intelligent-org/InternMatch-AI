"""
Session-specific recent reauthentication guard for destructive account deletion.

The normal authentication dependency must verify the same bearer token before
this guard is called. This guard then binds the verified token to its Supabase
session_id and requires that exact auth.sessions row to be recently created.

Refreshing an access token does not create a new session_id, so token refresh
alone cannot satisfy this destructive-action reauthentication boundary.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

ACCOUNT_DELETION_REAUTH_MAX_AGE = timedelta(minutes=10)
ACCOUNT_DELETION_REAUTH_CLOCK_SKEW = timedelta(minutes=1)


class AccountReauthenticationRequired(Exception):
    """Raised when a destructive account action needs a fresh login."""


class AccountReauthenticationUnavailable(Exception):
    """Raised when the server cannot validate the authoritative auth session."""


def _bearer_token(authorization: str | None) -> str:
    if not isinstance(authorization, str):
        raise AccountReauthenticationRequired()

    parts = authorization.strip().split(None, 1)

    if (
        len(parts) != 2
        or parts[0].lower() != "bearer"
        or not parts[1].strip()
    ):
        raise AccountReauthenticationRequired()

    return parts[1].strip()


def _verified_token_identity(
    token: str,
) -> tuple[UUID, UUID]:
    """
    Read sub/session_id only after the normal authentication dependency has
    already cryptographically authenticated this exact Authorization token.
    """
    segments = token.split(".")

    if len(segments) != 3:
        raise AccountReauthenticationRequired()

    payload_segment = segments[1]
    padding = "=" * (
        (-len(payload_segment)) % 4
    )

    try:
        payload = json.loads(
            base64.urlsafe_b64decode(
                payload_segment + padding
            ).decode("utf-8")
        )

        user_id = UUID(
            str(payload["sub"])
        )

        session_id = UUID(
            str(payload["session_id"])
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise AccountReauthenticationRequired() from exc

    return user_id, session_id


def _utc_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        normalized = value.strip()

        if normalized.endswith("Z"):
            normalized = (
                normalized[:-1]
                + "+00:00"
            )

        try:
            result = datetime.fromisoformat(
                normalized
            )
        except ValueError as exc:
            raise AccountReauthenticationRequired() from exc
    else:
        raise AccountReauthenticationRequired()

    if result.tzinfo is None:
        result = result.replace(
            tzinfo=timezone.utc
        )

    return result.astimezone(
        timezone.utc
    )


def require_recent_account_reauthentication(
    *,
    db: Session,
    authorization: str | None,
    expected_user_id: UUID,
    now: datetime | None = None,
) -> None:
    """
    Require a recently-created Supabase session for permanent account deletion.

    Security invariants:
    - authenticated user UUID must equal JWT sub
    - session_id must exist in auth.sessions for the same user
    - session creation must be <= 10 minutes old
    - refresh-token activity alone cannot satisfy the check
    """
    token = _bearer_token(
        authorization
    )

    token_user_id, session_id = (
        _verified_token_identity(
            token
        )
    )

    if token_user_id != expected_user_id:
        raise AccountReauthenticationRequired()

    try:
        row = (
            db.execute(
                text(
                    """
                    SELECT created_at
                    FROM auth.sessions
                    WHERE id = CAST(:session_id AS uuid)
                      AND user_id = CAST(:user_id AS uuid)
                    LIMIT 1
                    """
                ),
                {
                    "session_id": str(
                        session_id
                    ),
                    "user_id": str(
                        expected_user_id
                    ),
                },
            )
            .mappings()
            .first()
        )
    except Exception as exc:
        raise AccountReauthenticationUnavailable() from exc

    if row is None:
        raise AccountReauthenticationRequired()

    created_at = _utc_datetime(
        row.get("created_at")
    )

    current_time = (
        now.astimezone(timezone.utc)
        if now is not None
        else datetime.now(timezone.utc)
    )

    age = current_time - created_at

    if (
        age < -ACCOUNT_DELETION_REAUTH_CLOCK_SKEW
        or age > ACCOUNT_DELETION_REAUTH_MAX_AGE
    ):
        raise AccountReauthenticationRequired()
