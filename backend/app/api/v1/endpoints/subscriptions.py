"""Authenticated subscription state endpoint."""

from datetime import datetime
from typing import Optional

from app.core.security import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.services.subscription import get_student_subscription_snapshot
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter()


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
