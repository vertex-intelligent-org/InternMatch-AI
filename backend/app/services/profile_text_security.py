
"""
Security boundary for public candidate-profile text.

The headline is user-visible profile content and must never become a
credential-storage field. The helpers here intentionally return only
generic validation errors and never include the suspicious value.
"""

from __future__ import annotations

import re


MAX_PUBLIC_HEADLINE_LENGTH = 160

_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    \b
    (
        password
        | passwd
        | pwd
        | secret
        | api[\s_-]*key
        | access[\s_-]*token
        | refresh[\s_-]*token
        | auth[\s_-]*token
    )
    \s*
    [:=]
    \s*
    \S{4,}
    """
)

_BEARER_RE = re.compile(
    r"(?i)^bearer\s+\S{8,}$"
)

_JWT_RE = re.compile(
    r"^[A-Za-z0-9_-]{8,}\."
    r"[A-Za-z0-9_-]{8,}\."
    r"[A-Za-z0-9_-]{8,}$"
)

_SECRET_PREFIX_RE = re.compile(
    r"""(?ix)
    ^
    (
        sk-[A-Za-z0-9_-]{12,}
        | ghp_[A-Za-z0-9]{12,}
        | github_pat_[A-Za-z0-9_]{12,}
        | xox[baprs]-[A-Za-z0-9-]{12,}
    )
    $
    """
)


class ProfileTextSecurityError(ValueError):
    """Raised when public profile text appears credential-like."""


def _normalize_headline(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ProfileTextSecurityError(
            "Headline must be text."
        )

    clean = re.sub(
        r"\s+",
        " ",
        value.strip(),
    )

    if not clean:
        return None

    if len(clean) > MAX_PUBLIC_HEADLINE_LENGTH:
        raise ProfileTextSecurityError(
            "Headline exceeds the maximum length."
        )

    return clean


def looks_like_sensitive_credential(
    value: str | None,
) -> bool:
    """
    Conservative detector for credential-like values.

    Professional phrases containing ordinary spaces remain allowed.
    Compact password-shaped values, explicit secret assignments,
    JWTs, bearer tokens, and common secret-key prefixes are blocked.
    """
    clean = _normalize_headline(
        value
    )

    if clean is None:
        return False

    if _CREDENTIAL_ASSIGNMENT_RE.search(
        clean
    ):
        return True

    if _BEARER_RE.fullmatch(
        clean
    ):
        return True

    if _JWT_RE.fullmatch(
        clean
    ):
        return True

    if _SECRET_PREFIX_RE.fullmatch(
        clean
    ):
        return True

    # Public professional headlines are normally phrases.
    # A compact string with all four password character classes
    # is treated as credential-like.
    if (
        len(clean) >= 10
        and not any(
            char.isspace()
            for char in clean
        )
    ):
        has_lower = any(
            char.islower()
            for char in clean
        )

        has_upper = any(
            char.isupper()
            for char in clean
        )

        has_digit = any(
            char.isdigit()
            for char in clean
        )

        has_symbol = any(
            not char.isalnum()
            for char in clean
        )

        if (
            has_lower
            and has_upper
            and has_digit
            and has_symbol
        ):
            return True

    return False


def normalize_public_profile_headline(
    value: str | None,
) -> str | None:
    """
    Validate an explicitly user-authored public headline.

    Suspicious credential-like content is rejected before persistence.
    """
    clean = _normalize_headline(
        value
    )

    if (
        clean is not None
        and looks_like_sensitive_credential(
            clean
        )
    ):
        raise ProfileTextSecurityError(
            "Headline cannot contain credential-like or secret data."
        )

    return clean


def sanitize_extracted_profile_headline(
    value: str | None,
) -> str | None:
    """
    Sanitize an AI/CV-extracted headline.

    Extraction must not persist credential-like content. Instead of
    failing the entire CV confirmation, suspicious headline content
    is discarded.
    """
    try:
        clean = _normalize_headline(
            value
        )
    except ProfileTextSecurityError:
        return None

    if clean is None:
        return None

    if looks_like_sensitive_credential(
        clean
    ):
        return None

    return clean
