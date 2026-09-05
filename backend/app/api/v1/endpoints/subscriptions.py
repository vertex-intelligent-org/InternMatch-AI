"""Authenticated subscription state endpoints."""

from datetime import datetime
from typing import Optional

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.services.ai_quota import (
    AIQuotaConfigurationError,
    get_ai_usage_snapshot,
)
from app.services.revenuecat_reconciliation import (
    RevenueCatReconciliationConfigurationError,
    RevenueCatReconciliationProviderError,
    reconcile_student_subscription,
)
from app.services.subscription import get_student_subscription_snapshot
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter()


class AIQuotaFeatureResponse(BaseModel):
    """User-facing quota snapshot for one AI feature."""

    feature_key: str
    display_name: str
    limit: int
    used: int
    remaining: int
    reset_policy: str
    period_started_at: datetime
    reset_at: datetime


class AIUsageResponse(BaseModel):
    """Backend-authoritative Student AI usage policy snapshot."""

    plan: str
    features: list[AIQuotaFeatureResponse]


class SubscriptionResponse(BaseModel):
    """Backend-authoritative Student subscription snapshot."""

    plan: str
    entitlement_id: str
    is_active: bool
    status: str
    will_renew: bool
    expires_at: Optional[datetime] = None
    product_id: Optional[str] = None
    environment: Optional[str] = None
    store: Optional[str] = None
    last_event_type: Optional[str] = None


class SubscriptionReconciliationResponse(BaseModel):
    """Result of one backend-to-RevenueCat reconciliation."""

    outcome: str
    subscription: SubscriptionResponse


@router.get("/subscription", response_model=SubscriptionResponse)
def get_my_subscription(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the authenticated user's backend-authoritative subscription."""

    return SubscriptionResponse(
        **get_student_subscription_snapshot(
            db,
            user_id=current_user.user_id,
        )
    )


@router.get(
    "/ai-usage",
    response_model=AIUsageResponse,
)
def get_my_ai_usage(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return backend-controlled Student AI limits and remaining usage."""

    try:
        snapshot = get_ai_usage_snapshot(
            db,
            user_id=current_user.user_id,
        )
    except AIQuotaConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI usage policy is temporarily unavailable.",
        ) from exc

    return AIUsageResponse(**snapshot)


@router.post(
    "/subscription/reconcile",
    response_model=SubscriptionReconciliationResponse,
)
def reconcile_my_subscription(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Refresh the authenticated user's subscription from RevenueCat."""

    try:
        result = reconcile_student_subscription(
            db,
            user_id=current_user.user_id,
        )
    except RevenueCatReconciliationConfigurationError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Subscription reconciliation is not configured.",
        ) from exc
    except RevenueCatReconciliationProviderError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Subscription provider is temporarily unavailable.",
        ) from exc

    return SubscriptionReconciliationResponse(**result)
