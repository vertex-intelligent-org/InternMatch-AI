
"""Server-side Sign in with Apple authorization revocation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib import parse, request
from uuid import UUID

import jwt
from supabase import create_client

from app.core.config import settings

APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_REVOKE_URL = "https://appleid.apple.com/auth/revoke"
APPLE_AUDIENCE = "https://appleid.apple.com"


class AppleAuthorizationCodeRequired(Exception):
    """Apple-linked accounts must prove fresh Apple authorization."""


class AppleRevocationUnavailable(Exception):
    """Apple authorization could not be revoked safely."""


def _value(
    obj: object,
    key: str,
) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)

    return getattr(
        obj,
        key,
        None,
    )


def _apple_identity_subject(
    user: object,
) -> str | None:
    identities = (
        _value(
            user,
            "identities",
        )
        or []
    )

    for identity in identities:
        provider = str(
            _value(
                identity,
                "provider",
            )
            or ""
        ).lower()

        if provider != "apple":
            continue

        provider_id = _value(
            identity,
            "provider_id",
        )

        identity_data = (
            _value(
                identity,
                "identity_data",
            )
            or {}
        )

        subject = (
            provider_id
            or _value(
                identity_data,
                "sub",
            )
        )

        if subject:
            return str(
                subject
            )

        raise AppleRevocationUnavailable(
            "Apple identity subject is unavailable."
        )

    app_metadata = (
        _value(
            user,
            "app_metadata",
        )
        or {}
    )

    providers = (
        _value(
            app_metadata,
            "providers",
        )
        or []
    )

    provider = str(
        _value(
            app_metadata,
            "provider",
        )
        or ""
    ).lower()

    linked = (
        provider == "apple"
        or any(
            str(item).lower()
            == "apple"
            for item in providers
        )
    )

    if linked:
        raise AppleRevocationUnavailable(
            "Apple identity metadata is incomplete."
        )

    return None


def _load_supabase_user(
    *,
    user_id: UUID,
) -> object:
    url = (
        settings.SUPABASE_URL
        or ""
    ).strip()

    key = (
        settings.SUPABASE_SERVICE_ROLE_KEY
        or ""
    ).strip()

    if (
        not url
        or "placeholder" in url.lower()
        or not key
        or "placeholder" in key.lower()
    ):
        raise AppleRevocationUnavailable(
            "Identity provider configuration is unavailable."
        )

    try:
        response = (
            create_client(
                url,
                key,
            )
            .auth
            .admin
            .get_user_by_id(
                str(user_id)
            )
        )
    except Exception as exc:
        raise AppleRevocationUnavailable(
            "Unable to inspect linked identity providers."
        ) from exc

    user = (
        _value(
            response,
            "user",
        )
        or response
    )

    if user is None:
        raise AppleRevocationUnavailable(
            "Authenticated identity was not found."
        )

    return user


def _credentials() -> tuple[str, str, str, str]:
    client_id = (
        os.getenv(
            "APPLE_SIGN_IN_CLIENT_ID",
            "",
        )
        .strip()
    )

    team_id = (
        os.getenv(
            "APPLE_SIGN_IN_TEAM_ID",
            "",
        )
        .strip()
    )

    key_id = (
        os.getenv(
            "APPLE_SIGN_IN_KEY_ID",
            "",
        )
        .strip()
    )

    private_key = (
        os.getenv(
            "APPLE_SIGN_IN_PRIVATE_KEY",
            "",
        )
        .strip()
        .replace(
            "\\n",
            "\n",
        )
    )

    if not all(
        (
            client_id,
            team_id,
            key_id,
            private_key,
        )
    ):
        raise AppleRevocationUnavailable(
            "Apple token revocation is not configured."
        )

    return (
        client_id,
        team_id,
        key_id,
        private_key,
    )


def _client_secret(
    *,
    client_id: str,
    team_id: str,
    key_id: str,
    private_key: str,
) -> str:
    now = datetime.now(
        timezone.utc
    )

    payload = {
        "iss": team_id,
        "iat": int(
            now.timestamp()
        ),
        "exp": int(
            (
                now
                + timedelta(
                    minutes=10
                )
            ).timestamp()
        ),
        "aud": APPLE_AUDIENCE,
        "sub": client_id,
    }

    try:
        return jwt.encode(
            payload,
            private_key,
            algorithm="ES256",
            headers={
                "kid": key_id,
            },
        )
    except Exception as exc:
        raise AppleRevocationUnavailable(
            "Apple client-secret generation failed."
        ) from exc


def _post_form(
    *,
    url: str,
    payload: dict[str, str],
) -> tuple[int, bytes]:
    body = parse.urlencode(
        payload
    ).encode(
        "utf-8"
    )

    req = request.Request(
        url,
        data=body,
        headers={
            "Content-Type":
                "application/x-www-form-urlencoded",
            "Accept":
                "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(
            req,
            timeout=10,
        ) as response:
            return (
                int(
                    response.status
                ),
                response.read(),
            )
    except Exception as exc:
        raise AppleRevocationUnavailable(
            "Apple authorization service is unavailable."
        ) from exc


def _decode_apple_subject(
    id_token: str,
) -> str:
    try:
        claims = jwt.decode(
            id_token,
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_exp": False,
            },
        )
    except Exception as exc:
        raise AppleRevocationUnavailable(
            "Apple token response was invalid."
        ) from exc

    subject = claims.get(
        "sub"
    )

    if not subject:
        raise AppleRevocationUnavailable(
            "Apple token response did not identify the user."
        )

    return str(
        subject
    )


def _exchange_authorization_code(
    *,
    authorization_code: str,
    client_id: str,
    client_secret: str,
) -> tuple[str, str, str]:
    status_code, raw = _post_form(
        url=APPLE_TOKEN_URL,
        payload={
            "client_id":
                client_id,
            "client_secret":
                client_secret,
            "code":
                authorization_code,
            "grant_type":
                "authorization_code",
        },
    )

    if status_code != 200:
        raise AppleRevocationUnavailable(
            "Apple authorization-code exchange failed."
        )

    try:
        payload = json.loads(
            raw.decode(
                "utf-8"
            )
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise AppleRevocationUnavailable(
            "Apple token response was invalid."
        ) from exc

    refresh_token = payload.get(
        "refresh_token"
    )

    access_token = payload.get(
        "access_token"
    )

    id_token = payload.get(
        "id_token"
    )

    if refresh_token:
        token = str(
            refresh_token
        )
        token_type = (
            "refresh_token"
        )
    elif access_token:
        token = str(
            access_token
        )
        token_type = (
            "access_token"
        )
    else:
        raise AppleRevocationUnavailable(
            "Apple token response did not contain a revocable token."
        )

    if not id_token:
        raise AppleRevocationUnavailable(
            "Apple token response did not contain an identity token."
        )

    return (
        token,
        token_type,
        str(id_token),
    )


def _revoke_token(
    *,
    token: str,
    token_type: str,
    client_id: str,
    client_secret: str,
) -> None:
    status_code, _raw = _post_form(
        url=APPLE_REVOKE_URL,
        payload={
            "client_id":
                client_id,
            "client_secret":
                client_secret,
            "token":
                token,
            "token_type_hint":
                token_type,
        },
    )

    if status_code != 200:
        raise AppleRevocationUnavailable(
            "Apple authorization revocation failed."
        )


def revoke_apple_authorization_for_account(
    *,
    user_id: UUID,
    authorization_code: str | None,
) -> bool:
    """
    Revoke Sign in with Apple before deleting an Apple-linked account.

    Returns False when the account has no linked Apple identity.
    Returns True only after Apple accepted the revocation request.
    """
    user = _load_supabase_user(
        user_id=user_id
    )

    expected_subject = (
        _apple_identity_subject(
            user
        )
    )

    if expected_subject is None:
        return False

    code = (
        authorization_code
        or ""
    ).strip()

    if not code:
        raise AppleAuthorizationCodeRequired()

    (
        client_id,
        team_id,
        key_id,
        private_key,
    ) = _credentials()

    client_secret = _client_secret(
        client_id=client_id,
        team_id=team_id,
        key_id=key_id,
        private_key=private_key,
    )

    (
        token,
        token_type,
        id_token,
    ) = _exchange_authorization_code(
        authorization_code=code,
        client_id=client_id,
        client_secret=client_secret,
    )

    actual_subject = (
        _decode_apple_subject(
            id_token
        )
    )

    if actual_subject != expected_subject:
        raise AppleRevocationUnavailable(
            "Apple authorization does not belong to the account being deleted."
        )

    _revoke_token(
        token=token,
        token_type=token_type,
        client_id=client_id,
        client_secret=client_secret,
    )

    return True
