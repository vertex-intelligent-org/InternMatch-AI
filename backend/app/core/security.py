"""
Supabase Bearer JWT Authentication Foundation & Reusable FastAPI Dependencies
Enforces cryptographic verification and strict claim validation for Supabase JWTs.
"""

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, Optional
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import get_db
from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from supabase import create_client

logger = get_logger(__name__)


class AuthenticatedUser(BaseModel):
    """Container for validated Supabase authenticated user identity."""

    user_id: UUID = Field(
        ...,
        description="Supabase auth user UUID extracted from JWT sub claim",
    )
    email: Optional[str] = Field(None, description="Optional user email from JWT claims")
    role: Optional[str] = Field(None, description="Optional auth role (e.g. authenticated)")
    token_claims: Dict[str, Any] = Field(
        default_factory=dict,
        description="Complete verified JWT payload claims",
    )


def format_auth_error(message: str, code: str = "UNAUTHORIZED") -> Dict[str, Any]:
    """Helper to generate standardized machine-readable authentication error payloads."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }


@lru_cache(maxsize=4)
def _get_supabase_auth_client(
    supabase_url: str,
    supabase_pub_key: str,
    client_factory: Any,
) -> Any:
    """Reuse the Supabase auth client for stable process-level configuration."""
    return client_factory(
        supabase_url,
        supabase_pub_key,
    )


def verify_jwt_token(token: str) -> Dict[str, Any]:
    """
    Validate Supabase JWT bearer token using Supabase Auth's verified claims API.
    Cryptographically verifies algorithm (e.g. ES256/HS256/RS256), signature,
    and expiration via supabase.auth.get_claims(jwt=token).
    Validates issuer, audience, and subject (sub UUID).
    Never logs or exposes the raw token string or secrets.
    """
    supabase_url = settings.SUPABASE_URL.strip() if settings.SUPABASE_URL else ""
    supabase_pub_key = (
        settings.SUPABASE_PUBLISHABLE_KEY.strip() if settings.SUPABASE_PUBLISHABLE_KEY else ""
    )

    if (
        not supabase_url
        or "placeholder" in supabase_url.lower()
        or not supabase_pub_key
        or "placeholder" in supabase_pub_key.lower()
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=format_auth_error("Authentication service is not configured."),
        )

    try:
        supabase = _get_supabase_auth_client(
            supabase_url,
            supabase_pub_key,
            create_client,
        )
        claims_response = supabase.auth.get_claims(jwt=token)
    except Exception as exc:
        logger.warning("Supabase JWT claims verification failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=format_auth_error("Invalid or expired authentication token."),
        ) from exc

    if not claims_response:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=format_auth_error("Invalid or expired authentication token."),
        )

    # Extract claims payload dictionary from ClaimsResponse, TypedDict, or dict
    if isinstance(claims_response, dict) and "claims" in claims_response:
        payload = claims_response["claims"]
    elif hasattr(claims_response, "claims"):
        payload = claims_response.claims
    elif isinstance(claims_response, dict):
        payload = claims_response
    else:
        payload = {}

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=format_auth_error("Invalid or expired authentication token."),
        )

    # 1. Require exact issuer: {SUPABASE_URL.rstrip('/')}/auth/v1
    iss = payload.get("iss")
    expected_issuer = f"{supabase_url.rstrip('/')}/auth/v1"
    if iss != expected_issuer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=format_auth_error("Invalid JWT issuer."),
        )

    # 2. Require audience 'authenticated'
    aud = payload.get("aud")
    if isinstance(aud, list):
        aud_valid = "authenticated" in aud
    elif isinstance(aud, str):
        aud_valid = aud == "authenticated"
    else:
        aud_valid = False

    if not aud_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=format_auth_error(f"Invalid JWT audience '{aud}'. Expected 'authenticated'."),
        )

    # 3. Require non-empty sub
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=format_auth_error("Token is missing required subject ('sub') claim."),
        )

    # 4. Require sub to be a valid UUID
    try:
        UUID(str(sub))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=format_auth_error("Token subject claim is not a valid UUID."),
        )

    return payload


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> AuthenticatedUser:
    """
    Reusable FastAPI authentication dependency.
    Extracts, validates, and derives user_id strictly from Bearer JWT in Authorization header.
    Never accepts client-supplied user_id from path, query, or request body.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=format_auth_error("Missing Authorization header."),
        )

    parts = authorization.strip().split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        err_fmt = "Invalid Authorization header format. Expected 'Bearer <JWT>'."
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=format_auth_error(err_fmt),
        )

    token = parts[1]
    payload = verify_jwt_token(token)

    sub = payload.get("sub")
    user_uuid = UUID(str(sub))

    return AuthenticatedUser(
        user_id=user_uuid,
        email=payload.get("email"),
        role=payload.get("role"),
        token_claims=payload,
    )


async def get_current_user_id(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UUID:
    """
    Convenience dependency for endpoints that only require
    the authenticated user_id UUID.
    """
    return current_user.user_id


def require_admin_user(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """
    Require server-authorized InternMatch administrative access.

    Administrative authority is derived only from the authenticated Supabase
    user UUID and the server-side ADMIN_USER_IDS allowlist. Public account
    roles, profile preferences, email addresses, and client metadata never
    grant administrative privileges.

    An empty allowlist denies all administrative access.
    Invalid configured UUID values fail closed.
    """
    configured_admin_ids = set()

    for raw_value in (settings.ADMIN_USER_IDS or "").split(","):
        candidate = raw_value.strip()
        if not candidate:
            continue

        try:
            configured_admin_ids.add(UUID(candidate))
        except (ValueError, TypeError) as exc:
            logger.error("Invalid UUID found in ADMIN_USER_IDS configuration.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=format_auth_error(
                    "Administrative access is not configured correctly.",
                    code="ADMIN_CONFIGURATION_ERROR",
                ),
            ) from exc

    if current_user.user_id not in configured_admin_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=format_auth_error(
                "Administrative access denied.",
                code="FORBIDDEN",
            ),
        )

    return current_user


def require_employer_user(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    """
    FastAPI dependency ensuring authenticated user has a canonical StudentProfile
    with preferences['account_type'] == 'employer'.
    Rejects missing profiles and non-employer accounts with HTTP 403 Forbidden.
    """
    from app.repositories.student_profile import StudentProfileRepository

    profile = StudentProfileRepository.get_by_user_id(db, user_id=current_user.user_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=format_auth_error(
                "Employer profile not found or access denied.",
                code="FORBIDDEN",
            ),
        )
    account_type = (profile.preferences or {}).get("account_type")
    if not isinstance(account_type, str) or account_type.strip().lower() != "employer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=format_auth_error(
                "Only employer accounts are permitted to perform this action.",
                code="FORBIDDEN",
            ),
        )
    return current_user
