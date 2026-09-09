"""
InternMatch AI — Backend FastAPI Application Entrypoint
Authors: Mohammad & Selen (AISS Club — Üsküdar University)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.v1.endpoints.health import HealthResponse, get_liveness
from app.core.config import settings, validate_production_config
from app.core.logging import logger
from app.services.ai_quota import (
    AIQuotaExceededError,
    AIQuotaIdempotencyConflictError,
)
from app.services.ai_quota_integration import (
    format_ai_idempotency_conflict_payload,
    format_ai_quota_exceeded_payload,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events manager for application startup and shutdown."""
    validate_production_config(settings)
    logger.info(
        f"Starting {settings.PROJECT_NAME} backend v{settings.VERSION} "
        f"[{settings.ENVIRONMENT}]"
    )
    yield
    logger.info(f"Shutting down {settings.PROJECT_NAME} backend service.")


_IS_PRODUCTION = (
    (settings.ENVIRONMENT or "").strip().lower() == "production"
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="AI-powered personalized internship matching and application assistant REST API.",
    docs_url=None if _IS_PRODUCTION else "/docs",
    redoc_url=None if _IS_PRODUCTION else "/redoc",
    openapi_url=None if _IS_PRODUCTION else "/openapi.json",
    lifespan=lifespan,
)


@app.exception_handler(AIQuotaExceededError)
async def handle_ai_quota_exceeded(
    _request: Request,
    exc: AIQuotaExceededError,
) -> JSONResponse:
    """Expose product quota exhaustion separately from abuse rate limiting."""

    return JSONResponse(
        status_code=402,
        content=format_ai_quota_exceeded_payload(exc),
    )


@app.exception_handler(AIQuotaIdempotencyConflictError)
async def handle_ai_idempotency_conflict(
    _request: Request,
    _exc: AIQuotaIdempotencyConflictError,
) -> JSONResponse:
    """Reject reuse of an HTTP idempotency key for different input."""

    return JSONResponse(
        status_code=409,
        content=format_ai_idempotency_conflict_payload(),
    )

@app.middleware("http")
async def add_security_headers(
    request: Request,
    call_next,
):
    """Apply defensive browser-facing headers to every API response."""
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )

    if _IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    return response


# CORS Configuration
if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Mount Versioned API Routes (/api/v1/...)
app.include_router(api_router, prefix="/api")

# Mount Root Liveness Endpoint (/health)
app.add_api_route(
    "/health",
    endpoint=get_liveness,
    response_model=HealthResponse,
    methods=["GET"],
    tags=["Health Operations"],
    summary="Root Liveness Endpoint",
)
