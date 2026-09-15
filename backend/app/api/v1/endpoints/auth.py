"""
Backend Authentication Endpoints
Provides authenticated user account sync and identity verification.
"""

from typing import Literal, Optional
from uuid import UUID

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.repositories.student_profile import StudentProfileRepository
from app.services.account_deletion import (
    AccountDeletionError,
    delete_authenticated_account,
)
from app.services.account_reauthentication import (
    AccountReauthenticationRequired,
    AccountReauthenticationUnavailable,
    require_recent_account_reauthentication,
)
from app.services.apple_account_revocation import (
    AppleAuthorizationCodeRequired,
    AppleRevocationUnavailable,
    revoke_apple_authorization_for_account,
)
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter()


class AuthSyncResponse(BaseModel):
    """Schema for authentication session sync response."""

    user_id: UUID
    email: Optional[str] = None
    has_profile: bool


class CompleteSignupRequest(BaseModel):
    """One-time canonical InternMatch account provisioning payload."""

    full_name: str
    department: Optional[str] = None
    account_type: Literal["intern", "employer"]


class CompleteSignupResponse(BaseModel):
    """Response after canonical account provisioning."""

    created: bool
    user_id: UUID
    account_type: Literal["intern", "employer"]


class AccountDeletionResponse(BaseModel):
    """Response after permanent authenticated account deletion."""

    deleted: bool
    message: str


@router.post("/sync", response_model=AuthSyncResponse)
def sync_authenticated_user(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sync authenticated user session upon login via Supabase Auth.
    Checks whether candidate student profile exists in database.
    Identity is strictly derived from validated JWT claims.
    """
    profile = StudentProfileRepository.get_by_user_id(db, user_id=current_user.user_id)
    return AuthSyncResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        has_profile=profile is not None,
    )

@router.post(
    "/complete-signup",
    response_model=CompleteSignupResponse,
    status_code=status.HTTP_201_CREATED,
)
def complete_signup(
    payload: CompleteSignupRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Provision the canonical InternMatch account exactly once.

    Supabase authentication proves identity only. The application account role
    is validated and persisted here, never inferred from provider metadata.
    """
    existing_profile = StudentProfileRepository.get_by_user_id(
        db,
        user_id=current_user.user_id,
    )
    if existing_profile is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="InternMatch account already exists.",
        )

    full_name = payload.full_name.strip()
    if not full_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Full name is required.",
        )

    department = (
        payload.department.strip()
        if isinstance(payload.department, str) and payload.department.strip()
        else None
    )

    preferences = {
        "account_type": payload.account_type,
        "department": department,
    }

    try:
        StudentProfileRepository.create_by_user_id(
            db=db,
            user_id=current_user.user_id,
            full_name=full_name,
            headline=None,
            preferences=preferences,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="InternMatch account already exists.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    return CompleteSignupResponse(
        created=True,
        user_id=current_user.user_id,
        account_type=payload.account_type,
    )



def get_recently_reauthenticated_account_user(
    authorization: str | None = Header(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    """
    Destructive account deletion requires a fresh, session-specific login.

    get_current_user verifies the bearer token first. The recent-auth guard then
    verifies that the same token belongs to a newly-created Supabase session.
    """
    try:
        require_recent_account_reauthentication(
            db=db,
            authorization=authorization,
            expected_user_id=current_user.user_id,
        )
    except AccountReauthenticationRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACCOUNT_REAUTH_REQUIRED",
                "message": (
                    "Please verify your identity again "
                    "before permanently deleting your account."
                ),
            },
        ) from exc
    except AccountReauthenticationUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "ACCOUNT_REAUTH_UNAVAILABLE",
                "message": (
                    "Account identity verification is "
                    "temporarily unavailable."
                ),
            },
        ) from exc

    return current_user


@router.delete("/account", response_model=AccountDeletionResponse)
def delete_account(
    current_user: AuthenticatedUser = Depends(get_recently_reauthenticated_account_user),
    db: Session = Depends(get_db),
    apple_authorization_code: str | None = Header(
        default=None,
        alias="X-Apple-Authorization-Code",
    ),
):
    """
    Permanently delete the authenticated InternMatch AI account.

    Identity is derived exclusively from the validated bearer token. Client
    body/query identifiers are never used to choose the account being deleted.
    """
    try:
        revoke_apple_authorization_for_account(
            user_id=current_user.user_id,
            authorization_code=apple_authorization_code,
        )
    except AppleAuthorizationCodeRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "APPLE_REAUTH_REQUIRED",
                "message": (
                    "Please verify with Sign in with Apple "
                    "before deleting this account."
                ),
            },
        ) from exc
    except AppleRevocationUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "APPLE_REVOCATION_UNAVAILABLE",
                "message": (
                    "Apple authorization could not be revoked safely. "
                    "Please try again."
                ),
            },
        ) from exc

    try:
        result = delete_authenticated_account(
            db,
            user_id=current_user.user_id,
        )
    except AccountDeletionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Account deletion could not be completed safely. "
                "Please try again."
            ),
        ) from exc

    return AccountDeletionResponse(**result)
