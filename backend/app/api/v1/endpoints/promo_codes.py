"""Authenticated promo redemption and administrator campaign controls."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from app.core.security import (
    AuthenticatedUser,
    get_current_user,
    require_admin_user,
)
from app.db.session import get_db
from app.repositories.promo_code import PromoCodeRepository
from app.services.promo_codes import (
    PromoCampaignNotFound,
    PromoCodeActivePro,
    PromoCodeAlreadyRedeemed,
    PromoCodeConfigurationError,
    PromoCodeConflict,
    PromoCodeDisabled,
    PromoCodeInProgress,
    PromoCodeInvalid,
    PromoCodeProviderUnavailable,
    create_campaign,
    get_redemption_status,
    list_campaigns,
    publish_campaign,
    redeem_promo_code,
    retire_campaign,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

user_router = APIRouter()
admin_router = APIRouter()


class PromoRedeemRequest(BaseModel):
    code: str = Field(
        ...,
        min_length=16,
        max_length=64,
    )


class PromoRedeemResponse(BaseModel):
    outcome: str
    audience: Literal[
        "student",
        "employer",
    ]
    plan: str
    access_started_at: datetime
    access_expires_at: datetime
    sync_pending: bool


class PromoStatusResponse(BaseModel):
    audience: Literal[
        "student",
        "employer",
    ]
    used_once: bool
    status: str | None = None
    access_expires_at: datetime | None = None


class PromoCampaignCreateRequest(BaseModel):
    audience: Literal[
        "student",
        "employer",
    ]

    code: str = Field(
        ...,
        min_length=16,
        max_length=64,
    )

    publish: bool = True


class PromoCampaignResponse(BaseModel):
    id: UUID
    audience: Literal[
        "student",
        "employer",
    ]
    code_hint: str
    status: Literal[
        "draft",
        "published",
        "retired",
    ]
    duration_days: int
    redemption_count: int
    created_at: datetime
    updated_at: datetime
    retired_at: datetime | None = None


def _campaign_response(
    db: Session,
    campaign,
) -> PromoCampaignResponse:
    return PromoCampaignResponse(
        id=campaign.id,
        audience=campaign.audience,
        code_hint=campaign.code_hint,
        status=campaign.status,
        duration_days=campaign.duration_days,
        redemption_count=(
            PromoCodeRepository
            .count_redeemed_for_campaign(
                db,
                campaign_id=campaign.id,
            )
        ),
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        retired_at=campaign.retired_at,
    )


def _promo_http_error(
    exc: Exception,
) -> HTTPException:
    if isinstance(
        exc,
        PromoCodeDisabled,
    ):
        return HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail={
                "error": {
                    "code":
                        "PROMO_DISABLED",
                    "message":
                        "Promo redemption is not currently available.",
                }
            },
        )

    if isinstance(
        exc,
        PromoCodeInvalid,
    ):
        return HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail={
                "error": {
                    "code":
                        "PROMO_INVALID",
                    "message":
                        "Promo code is invalid or unavailable.",
                }
            },
        )

    if isinstance(
        exc,
        PromoCodeAlreadyRedeemed,
    ):
        return HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail={
                "error": {
                    "code":
                        "PROMO_ALREADY_REDEEMED",
                    "message":
                        "This account has already used its promotional access.",
                }
            },
        )

    if isinstance(
        exc,
        PromoCodeActivePro,
    ):
        return HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail={
                "error": {
                    "code":
                        "PROMO_PRO_ALREADY_ACTIVE",
                    "message":
                        "Pro access is already active on this account.",
                }
            },
        )

    if isinstance(
        exc,
        PromoCodeInProgress,
    ):
        return HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail={
                "error": {
                    "code":
                        "PROMO_IN_PROGRESS",
                    "message":
                        "A promo redemption is already being processed.",
                }
            },
        )

    if isinstance(
        exc,
        PromoCampaignNotFound,
    ):
        return HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail={
                "error": {
                    "code":
                        "PROMO_CAMPAIGN_NOT_FOUND",
                    "message":
                        "Promo campaign was not found.",
                }
            },
        )

    if isinstance(
        exc,
        PromoCodeConflict,
    ):
        return HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
            ),
            detail={
                "error": {
                    "code":
                        "PROMO_CONFLICT",
                    "message":
                        str(exc),
                }
            },
        )

    if isinstance(
        exc,
        PromoCodeConfigurationError,
    ):
        return HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail={
                "error": {
                    "code":
                        "PROMO_CONFIGURATION_ERROR",
                    "message":
                        "Promotional access is temporarily unavailable.",
                }
            },
        )

    if isinstance(
        exc,
        PromoCodeProviderUnavailable,
    ):
        return HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail={
                "error": {
                    "code":
                        "PROMO_PROVIDER_UNAVAILABLE",
                    "message":
                        "Promotional access provider is temporarily unavailable.",
                }
            },
        )

    return HTTPException(
        status_code=(
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ),
        detail={
            "error": {
                "code":
                    "PROMO_INTERNAL_ERROR",
                "message":
                    "Promo request could not be completed.",
            }
        },
    )


@user_router.get(
    "/status",
    response_model=PromoStatusResponse,
)
def get_my_promo_status(
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(
        get_db
    ),
):
    try:
        payload = get_redemption_status(
            db,
            user_id=current_user.user_id,
        )
    except Exception as exc:
        raise _promo_http_error(
            exc
        ) from exc

    return PromoStatusResponse(
        **payload
    )


@user_router.post(
    "/redeem",
    response_model=PromoRedeemResponse,
)
def redeem_my_promo(
    payload: PromoRedeemRequest,
    current_user: AuthenticatedUser = Depends(
        get_current_user
    ),
    db: Session = Depends(
        get_db
    ),
):
    try:
        result = redeem_promo_code(
            db,
            user_id=current_user.user_id,
            code=payload.code,
        )
    except Exception as exc:
        raise _promo_http_error(
            exc
        ) from exc

    return PromoRedeemResponse(
        outcome=result["outcome"],
        audience=result["audience"],
        plan=result["plan"],
        access_started_at=(
            result["access_started_at"]
        ),
        access_expires_at=(
            result["access_expires_at"]
        ),
        sync_pending=(
            result["sync_pending"]
        ),
    )


@admin_router.get(
    "",
    response_model=list[
        PromoCampaignResponse
    ],
)
def admin_list_promo_campaigns(
    audience: Literal[
        "student",
        "employer",
    ]
    | None = Query(
        default=None
    ),
    _admin: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(
        get_db
    ),
):
    campaigns = list_campaigns(
        db,
        audience=audience,
    )

    return [
        _campaign_response(
            db,
            campaign,
        )
        for campaign in campaigns
    ]


@admin_router.post(
    "",
    response_model=PromoCampaignResponse,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_promo_campaign(
    payload: PromoCampaignCreateRequest,
    admin: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(
        get_db
    ),
):
    try:
        campaign = create_campaign(
            db,
            audience=payload.audience,
            code=payload.code,
            admin_user_id=admin.user_id,
            publish=payload.publish,
        )
    except Exception as exc:
        raise _promo_http_error(
            exc
        ) from exc

    return _campaign_response(
        db,
        campaign,
    )


@admin_router.post(
    "/{campaign_id}/publish",
    response_model=PromoCampaignResponse,
)
def admin_publish_promo_campaign(
    campaign_id: UUID,
    admin: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(
        get_db
    ),
):
    try:
        campaign = publish_campaign(
            db,
            campaign_id=campaign_id,
            admin_user_id=admin.user_id,
        )
    except Exception as exc:
        raise _promo_http_error(
            exc
        ) from exc

    return _campaign_response(
        db,
        campaign,
    )


@admin_router.post(
    "/{campaign_id}/retire",
    response_model=PromoCampaignResponse,
)
def admin_retire_promo_campaign(
    campaign_id: UUID,
    admin: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(
        get_db
    ),
):
    try:
        campaign = retire_campaign(
            db,
            campaign_id=campaign_id,
            admin_user_id=admin.user_id,
        )
    except Exception as exc:
        raise _promo_http_error(
            exc
        ) from exc

    return _campaign_response(
        db,
        campaign,
    )


@admin_router.delete(
    "/{campaign_id}",
    response_model=PromoCampaignResponse,
)
def admin_delete_promo_campaign(
    campaign_id: UUID,
    admin: AuthenticatedUser = Depends(
        require_admin_user
    ),
    db: Session = Depends(
        get_db
    ),
):
    # "Delete" is deliberately implemented as soft retirement so
    # previously redeemed users are never affected and audit history
    # remains intact.
    try:
        campaign = retire_campaign(
            db,
            campaign_id=campaign_id,
            admin_user_id=admin.user_id,
        )
    except Exception as exc:
        raise _promo_http_error(
            exc
        ) from exc

    return _campaign_response(
        db,
        campaign,
    )
