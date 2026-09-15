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


def _private_document_language(
    *,
    requested_language: str | None,
    accept_language: str,
) -> str:
    if requested_language in {
        "ar",
        "tr",
        "en",
    }:
        return requested_language

    normalized = (
        accept_language
        or ""
    ).lower()

    if normalized.startswith("ar"):
        return "ar"

    if normalized.startswith("tr"):
        return "tr"

    return "en"


def _private_document_unavailable_html(
    *,
    language: str,
) -> str:
    """
    Return one generic InternMatch private-document page.

    No resource identifiers, storage paths, tokens, provider
    hostnames, or resource-existence details are included.
    """
    if language == "ar":
        lang = "ar"
        direction = "rtl"
        title = "تعذر فتح المستند"
        message = (
            "لا يمكن فتح هذا المستند. "
            "قد لا تملك صلاحية الوصول إليه، "
            "أو ربما لم يعد المستند متاحًا. "
            "سجّل الدخول بالحساب الصحيح أو ارجع إلى InternMatch AI."
        )
        action = "العودة إلى InternMatch AI"

    elif language == "tr":
        lang = "tr"
        direction = "ltr"
        title = "Belge açılamıyor"
        message = (
            "Bu belge açılamıyor. "
            "Erişim izniniz olmayabilir veya belge artık mevcut olmayabilir. "
            "Doğru hesapla oturum açın ya da InternMatch AI'a geri dönün."
        )
        action = "InternMatch AI'a dön"

    else:
        lang = "en"
        direction = "ltr"
        title = "Document unavailable"
        message = (
            "This document can't be opened. "
            "You may not have permission to access it, "
            "or the document may no longer be available. "
            "Sign in with the correct account or return to InternMatch AI."
        )
        action = "Return to InternMatch AI"

    return f"""<!doctype html>
<html lang="{lang}" dir="{direction}">
<head>
  <meta charset="utf-8">
  <meta
    name="viewport"
    content="width=device-width, initial-scale=1"
  >
  <meta
    name="robots"
    content="noindex,nofollow"
  >
  <title>{title} | InternMatch AI</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family:
        Inter,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      background: #07111f;
      color: #f8fafc;
    }}

    main {{
      width: min(100%, 540px);
      padding: 32px;
      background: #0d1b2a;
      border: 1px solid #24364b;
      border-radius: 20px;
      box-shadow:
        0 24px 60px
        rgba(0, 0, 0, .30);
    }}

    .brand {{
      margin-bottom: 18px;
      color: #80d8d0;
      font-size: 14px;
      font-weight: 700;
      letter-spacing: .04em;
    }}

    h1 {{
      margin: 0 0 14px;
      font-size: 28px;
      line-height: 1.2;
    }}

    p {{
      margin: 0 0 24px;
      color: #cbd5e1;
      line-height: 1.7;
    }}

    .languages {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 22px;
    }}

    .languages a {{
      padding: 7px 10px;
      border: 1px solid #334155;
      border-radius: 9px;
      background: transparent;
      color: #cbd5e1;
      font-size: 13px;
      font-weight: 600;
    }}

    .return-link {{
      display: inline-block;
      padding: 12px 18px;
      border-radius: 12px;
      background: #f8fafc;
      color: #07111f;
      font-weight: 700;
      text-decoration: none;
    }}

    a {{
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <main>
    <div class="brand">
      InternMatch AI
    </div>

    <h1>{title}</h1>

    <p>{message}</p>

    <nav
      class="languages"
      aria-label="Language"
    >
      <a href="/document-unavailable?lang=en">
        English
      </a>

      <a href="/document-unavailable?lang=tr">
        Türkçe
      </a>

      <a href="/document-unavailable?lang=ar">
        العربية
      </a>
    </nav>

    <a
      class="return-link"
      href="https://internmatch.college/"
    >
      {action}
    </a>
  </main>
</body>
</html>"""


@app.get(
    "/document-unavailable",
    include_in_schema=False,
)
def private_document_unavailable_page(
    request: Request,
    lang: str | None = None,
):
    """
    Generic branded destination for inaccessible private documents.

    Only a non-sensitive language selector may appear in the query
    string. No private resource identifier is accepted or rendered.
    """
    from fastapi.responses import HTMLResponse

    language = _private_document_language(
        requested_language=lang,
        accept_language=(
            request.headers.get(
                "accept-language",
                "",
            )
            or ""
        ),
    )

    return HTMLResponse(
        content=_private_document_unavailable_html(
            language=language,
        ),
        status_code=200,
        headers={
            "Cache-Control":
                "private, no-store, max-age=0",
            "Pragma":
                "no-cache",
            "Referrer-Policy":
                "no-referrer",
            "X-Content-Type-Options":
                "nosniff",
            "X-Robots-Tag":
                "noindex, nofollow",
            "Content-Security-Policy":
                "default-src 'none'; "
                "style-src 'unsafe-inline'; "
                "base-uri 'none'; "
                "frame-ancestors 'none'",
        },
    )


@app.middleware("http")
async def private_document_browser_guard(
    request: Request,
    call_next,
):
    """
    Browser navigation to inaccessible private content goes to one
    generic InternMatch page.

    Mobile/API callers retain the original machine-readable status.
    """
    response = await call_next(
        request
    )

    if response.status_code not in {
        401,
        403,
        404,
    }:
        return response

    accept = (
        request.headers.get(
            "accept",
            "",
        )
        or ""
    ).lower()

    if "text/html" not in accept:
        return response

    path = request.url.path

    is_avatar = (
        path
        == "/api/v1/profile/avatar/content"
    )

    is_cv = (
        path.startswith(
            "/api/v1/internships/"
        )
        and "/applicants/" in path
        and path.endswith(
            "/cv/content"
        )
    )

    is_compliance = (
        "/employer-compliance/" in path
        and "/evidence/" in path
        and path.endswith(
            "/content"
        )
    )

    if not (
        is_avatar
        or is_cv
        or is_compliance
    ):
        return response

    from fastapi.responses import RedirectResponse

    return RedirectResponse(
        url="/document-unavailable",
        status_code=303,
        headers={
            "Cache-Control":
                "private, no-store, max-age=0",
            "Pragma":
                "no-cache",
            "Referrer-Policy":
                "no-referrer",
            "X-Content-Type-Options":
                "nosniff",
        },
    )


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
