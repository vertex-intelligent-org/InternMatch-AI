"""External provider webhook endpoints."""

import json
from typing import Optional

from app.core.logging import get_logger
from app.db.session import get_db
from app.services.revenuecat_webhook import (
    RevenueCatWebhookAuthenticationError,
    RevenueCatWebhookConfigurationError,
    process_revenuecat_webhook,
    verify_revenuecat_webhook_request,
)
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter()
logger = get_logger(__name__)


class RevenueCatWebhookResponse(BaseModel):
    status: str
    event_id: str
    event_type: str
    outcome: str


@router.post("/revenuecat", response_model=RevenueCatWebhookResponse)
async def receive_revenuecat_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Authenticate and process one RevenueCat webhook delivery."""

    raw_body = await request.body()

    authorization: Optional[str] = request.headers.get("Authorization")
    signature: Optional[str] = request.headers.get(
        "X-RevenueCat-Webhook-Signature"
    )

    try:
        verify_revenuecat_webhook_request(
            raw_body=raw_body,
            authorization=authorization,
            signature_header=signature,
        )
    except RevenueCatWebhookConfigurationError as exc:
        logger.error("RevenueCat webhook rejected: server security is not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RevenueCat webhook is not configured.",
        ) from exc
    except RevenueCatWebhookAuthenticationError as exc:
        logger.warning("RevenueCat webhook authentication failed.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook authentication.",
        ) from exc

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid RevenueCat webhook payload.",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid RevenueCat webhook payload.",
        )

    try:
        result = process_revenuecat_webhook(db, payload=payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid RevenueCat webhook event.",
        ) from exc
    except Exception:
        db.rollback()
        logger.exception("RevenueCat webhook processing failed.")
        raise

    logger.info(
        "RevenueCat webhook processed event_id=%s type=%s outcome=%s",
        result["event_id"],
        result["event_type"],
        result["outcome"],
    )

    return RevenueCatWebhookResponse(**result)
