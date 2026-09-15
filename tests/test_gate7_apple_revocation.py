
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.services import apple_account_revocation as service
from app.services.apple_account_revocation import (
    AppleAuthorizationCodeRequired,
    AppleRevocationUnavailable,
)


def _apple_user(
    subject: str,
):
    return SimpleNamespace(
        identities=[
            SimpleNamespace(
                provider="apple",
                provider_id=subject,
                identity_data={
                    "sub": subject,
                },
            )
        ],
        app_metadata={
            "provider": "apple",
            "providers": [
                "apple"
            ],
        },
    )


def _email_user():
    return SimpleNamespace(
        identities=[
            SimpleNamespace(
                provider="email",
                provider_id="user@example.com",
                identity_data={},
            )
        ],
        app_metadata={
            "provider": "email",
            "providers": [
                "email"
            ],
        },
    )


def test_non_apple_account_needs_no_apple_revocation(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "_load_supabase_user",
        lambda **_kwargs: _email_user(),
    )

    result = (
        service.revoke_apple_authorization_for_account(
            user_id=uuid4(),
            authorization_code=None,
        )
    )

    assert result is False


def test_apple_account_requires_fresh_authorization_code(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "_load_supabase_user",
        lambda **_kwargs: _apple_user(
            "apple-subject-1"
        ),
    )

    with pytest.raises(
        AppleAuthorizationCodeRequired
    ):
        service.revoke_apple_authorization_for_account(
            user_id=uuid4(),
            authorization_code=None,
        )


def test_apple_authorization_is_bound_to_same_identity(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "_load_supabase_user",
        lambda **_kwargs: _apple_user(
            "expected-subject"
        ),
    )

    monkeypatch.setattr(
        service,
        "_credentials",
        lambda: (
            "client",
            "team",
            "key",
            "private",
        ),
    )

    monkeypatch.setattr(
        service,
        "_client_secret",
        lambda **_kwargs:
            "client-secret",
    )

    monkeypatch.setattr(
        service,
        "_exchange_authorization_code",
        lambda **_kwargs: (
            "refresh-token",
            "refresh_token",
            "apple-id-token",
        ),
    )

    monkeypatch.setattr(
        service,
        "_decode_apple_subject",
        lambda _token:
            "different-subject",
    )

    revoked = []

    monkeypatch.setattr(
        service,
        "_revoke_token",
        lambda **kwargs:
            revoked.append(
                kwargs
            ),
    )

    with pytest.raises(
        AppleRevocationUnavailable
    ):
        service.revoke_apple_authorization_for_account(
            user_id=uuid4(),
            authorization_code="fresh-code",
        )

    assert revoked == []


def test_same_apple_identity_is_revoked_before_deletion(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "_load_supabase_user",
        lambda **_kwargs: _apple_user(
            "same-subject"
        ),
    )

    monkeypatch.setattr(
        service,
        "_credentials",
        lambda: (
            "client",
            "team",
            "key",
            "private",
        ),
    )

    monkeypatch.setattr(
        service,
        "_client_secret",
        lambda **_kwargs:
            "client-secret",
    )

    monkeypatch.setattr(
        service,
        "_exchange_authorization_code",
        lambda **_kwargs: (
            "refresh-token",
            "refresh_token",
            "apple-id-token",
        ),
    )

    monkeypatch.setattr(
        service,
        "_decode_apple_subject",
        lambda _token:
            "same-subject",
    )

    revoked = []

    monkeypatch.setattr(
        service,
        "_revoke_token",
        lambda **kwargs:
            revoked.append(
                kwargs
            ),
    )

    result = (
        service.revoke_apple_authorization_for_account(
            user_id=uuid4(),
            authorization_code="fresh-code",
        )
    )

    assert result is True
    assert len(revoked) == 1
    assert (
        revoked[0]["token"]
        == "refresh-token"
    )
    assert (
        revoked[0]["token_type"]
        == "refresh_token"
    )


def test_mobile_forwards_fresh_apple_code_to_delete_api():
    from pathlib import Path

    apple_auth = Path(
        "apps/mobile/src/services/appleAuth.js"
    ).read_text(
        encoding="utf-8"
    )

    screen = Path(
        "apps/mobile/src/screens/"
        "AccountDeletionReauthScreen.js"
    ).read_text(
        encoding="utf-8"
    )

    api = Path(
        "apps/mobile/src/services/api.ts"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "credential.authorizationCode"
        in apple_auth
    )

    assert (
        "result.authorizationCode"
        in screen
    )

    assert (
        "appleAuthorizationCode"
        in api
    )

    assert (
        "X-Apple-Authorization-Code"
        in api
    )


def test_backend_revokes_apple_before_product_purge():
    from pathlib import Path

    source = Path(
        "backend/app/api/v1/endpoints/auth.py"
    ).read_text(
        encoding="utf-8"
    )

    revoke_index = source.index(
        "revoke_apple_authorization_for_account("
    )

    delete_index = source.index(
        "result = delete_authenticated_account("
    )

    assert revoke_index < delete_index

    assert (
        "APPLE_REAUTH_REQUIRED"
        in source
    )

    assert (
        "APPLE_REVOCATION_UNAVAILABLE"
        in source
    )
