from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from app.services.account_reauthentication import (
    AccountReauthenticationRequired,
    AccountReauthenticationUnavailable,
    require_recent_account_reauthentication,
)


class _FakeMappings:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class _FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return _FakeMappings(
            self.row
        )


class _FakeDb:
    def __init__(
        self,
        *,
        row=None,
        error=None,
    ):
        self.row = row
        self.error = error
        self.calls = []

    def execute(
        self,
        statement,
        params,
    ):
        self.calls.append(
            (
                str(statement),
                params,
            )
        )

        if self.error is not None:
            raise self.error

        return _FakeResult(
            self.row
        )


def _b64(value: dict) -> str:
    raw = json.dumps(
        value,
        separators=(",", ":"),
    ).encode("utf-8")

    return (
        base64.urlsafe_b64encode(raw)
        .decode("ascii")
        .rstrip("=")
    )


def _token(
    *,
    user_id,
    session_id,
) -> str:
    return (
        f"{_b64({'alg': 'none', 'typ': 'JWT'})}."
        f"{_b64({'sub': str(user_id), 'session_id': str(session_id)})}."
        "test-signature"
    )


def test_recent_exact_session_allows_account_deletion():
    user_id = uuid4()
    session_id = uuid4()

    now = datetime(
        2026,
        9,
        15,
        12,
        0,
        tzinfo=timezone.utc,
    )

    db = _FakeDb(
        row={
            "created_at": (
                now
                - timedelta(minutes=2)
            )
        }
    )

    require_recent_account_reauthentication(
        db=db,
        authorization=(
            "Bearer "
            + _token(
                user_id=user_id,
                session_id=session_id,
            )
        ),
        expected_user_id=user_id,
        now=now,
    )

    assert len(db.calls) == 1
    assert (
        db.calls[0][1]["session_id"]
        == str(session_id)
    )


def test_refresh_of_old_session_cannot_satisfy_recent_reauth():
    user_id = uuid4()
    session_id = uuid4()

    now = datetime(
        2026,
        9,
        15,
        12,
        0,
        tzinfo=timezone.utc,
    )

    db = _FakeDb(
        row={
            "created_at": (
                now
                - timedelta(hours=2)
            )
        }
    )

    with pytest.raises(
        AccountReauthenticationRequired
    ):
        require_recent_account_reauthentication(
            db=db,
            authorization=(
                "Bearer "
                + _token(
                    user_id=user_id,
                    session_id=session_id,
                )
            ),
            expected_user_id=user_id,
            now=now,
        )


def test_mismatched_identity_is_rejected_before_session_query():
    expected_user_id = uuid4()

    db = _FakeDb(
        row={
            "created_at": datetime.now(
                timezone.utc
            )
        }
    )

    with pytest.raises(
        AccountReauthenticationRequired
    ):
        require_recent_account_reauthentication(
            db=db,
            authorization=(
                "Bearer "
                + _token(
                    user_id=uuid4(),
                    session_id=uuid4(),
                )
            ),
            expected_user_id=expected_user_id,
        )

    assert db.calls == []


def test_missing_bearer_token_is_rejected():
    with pytest.raises(
        AccountReauthenticationRequired
    ):
        require_recent_account_reauthentication(
            db=_FakeDb(),
            authorization=None,
            expected_user_id=uuid4(),
        )


def test_missing_authoritative_session_is_rejected():
    user_id = uuid4()

    with pytest.raises(
        AccountReauthenticationRequired
    ):
        require_recent_account_reauthentication(
            db=_FakeDb(
                row=None
            ),
            authorization=(
                "Bearer "
                + _token(
                    user_id=user_id,
                    session_id=uuid4(),
                )
            ),
            expected_user_id=user_id,
        )


def test_auth_session_store_failure_fails_closed():
    user_id = uuid4()

    with pytest.raises(
        AccountReauthenticationUnavailable
    ):
        require_recent_account_reauthentication(
            db=_FakeDb(
                error=RuntimeError(
                    "auth schema unavailable"
                )
            ),
            authorization=(
                "Bearer "
                + _token(
                    user_id=user_id,
                    session_id=uuid4(),
                )
            ),
            expected_user_id=user_id,
        )


def test_delete_endpoint_requires_recent_reauthentication():
    source = Path(
        "backend/app/api/v1/endpoints/auth.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "get_recently_reauthenticated_account_user"
        in source
    )

    assert (
        "ACCOUNT_REAUTH_REQUIRED"
        in source
    )

    assert (
        "require_recent_account_reauthentication("
        in source
    )


def test_account_deletion_purges_gate6_notification_state():
    source = Path(
        "backend/app/services/account_deletion.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "UserNotification.recipient_user_id == user_id"
        in source
    )

    assert (
        "PushDevice.user_id == user_id"
        in source
    )


def test_mobile_delete_flow_requires_same_account_reauthentication():
    settings_source = Path(
        "apps/mobile/src/screens/SettingsScreen.js"
    ).read_text(
        encoding="utf-8"
    )

    reauth_source = Path(
        "apps/mobile/src/screens/"
        "AccountDeletionReauthScreen.js"
    ).read_text(
        encoding="utf-8"
    )

    navigator = Path(
        "apps/mobile/src/navigation/"
        "RootNavigator.js"
    ).read_text(
        encoding="utf-8"
    )

    start = settings_source.index(
        "const handleDeleteAccount"
    )

    end = settings_source.index(
        "const handleSignOut",
        start,
    )

    handler = settings_source[
        start:end
    ]

    assert (
        "AccountDeletionReauth"
        in handler
    )

    assert (
        "await deleteAccount()"
        not in handler
    )

    assert (
        "signInWithEmail"
        in reauth_source
    )

    assert (
        "signInWithGoogle"
        in reauth_source
    )

    assert (
        "signInWithApple"
        in reauth_source
    )

    assert (
        "verifiedUserId !== originalUserId"
        in reauth_source
    )

    assert (
        "await deleteAccount("
        in reauth_source
    )

    assert (
        "appleAuthorizationCode"
        in reauth_source
    )

    assert (
        'name="AccountDeletionReauth"'
        in navigator
    )
