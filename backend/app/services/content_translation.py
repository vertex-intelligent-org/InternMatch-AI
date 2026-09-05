"""
Dynamic Internship Content Translation Service
Provides on-demand translation of free-form internship fields (description, min_education)
using Google Gemini Structured Outputs and Redis content-hashed caching.
"""

import hashlib
import json
import logging
from typing import Optional, Tuple
from uuid import UUID

import redis
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.services.ai_telemetry import create_tracked_gemini_client

logger = logging.getLogger(__name__)

CACHE_VERSION = "v1"
CACHE_TTL_SECONDS = 30 * 86400  # 30 days
LOCK_TTL_SECONDS = 120  # 2-minute bounded stampede guard
FAILURE_SENTINEL_TTL_SECONDS = 300  # 5 minutes failure cooldown


class TranslatedInternshipContent(BaseModel):
    """Structured model for translated free-form internship content."""

    model_config = ConfigDict(extra="forbid")

    description: Optional[str] = Field(
        None,
        description="Faithfully translated internship description with structure preserved.",
    )
    min_education: Optional[str] = Field(
        None,
        description="Faithfully translated education requirements, if present in source.",
    )


def compute_internship_content_hash(
    description: Optional[str],
    min_education: Optional[str] = None,
) -> str:
    """
    Compute a deterministic SHA-256 hash from only translatable source fields.
    Changes to canonical non-translatable fields (title, company, location) do NOT
    alter this hash, while source content modifications automatically invalidate cache.
    """
    payload = {
        "description": (description or "").strip(),
        "min_education": (min_education or "").strip(),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _get_redis_client() -> redis.Redis:
    """Create Redis client with short connection/socket timeout for request protection."""
    return redis.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=2.0,
        socket_timeout=2.0,
        decode_responses=True,
    )


def _build_translation_prompt(target_locale: str) -> str:
    """Build strict, faithful translation instructions for target language."""
    target_language = "Turkish" if target_locale == "tr" else "Modern Standard Arabic"
    return f"""You are a professional, faithful translator for InternMatch AI.
Your role is to accurately translate free-form internship listing content into {target_language}.

Target content locale: {target_locale}

STRICT TRANSLATION RULES:
1. Provide faithful, accurate translation only.
2. Do NOT summarize, omit facts, or add any new information.
3. Preserve paragraph breaks, bullet point formatting, and lists exactly.
4. Preserve all URLs, email addresses, and contact info verbatim.
5. Preserve company, institution, product, and other proper names verbatim.
6. Preserve all technical skill and tool names verbatim.
7. For locale 'tr', use natural, professional Turkish.
8. For locale 'ar', use natural, professional Modern Standard Arabic.
"""


def _call_gemini_translation(
    description: Optional[str],
    min_education: Optional[str],
    target_locale: str,
) -> Optional[TranslatedInternshipContent]:
    """
    Call Google Gemini structured output API to translate free-form content.
    Constructs Gemini client at call-time from settings.
    Returns None on provider or validation failure.
    """
    api_key = settings.GEMINI_API_KEY.strip() if settings.GEMINI_API_KEY else ""
    if not api_key or "placeholder" in api_key.lower():
        logger.warning("GEMINI_API_KEY is missing or placeholder; skipping translation.")
        return None

    user_lines = []
    if description and description.strip():
        user_lines.append(f"--- DESCRIPTION ---\n{description.strip()}")
    if min_education and min_education.strip():
        user_lines.append(f"--- MIN_EDUCATION ---\n{min_education.strip()}")

    if not user_lines:
        return None

    user_content = "\n\n".join(user_lines)

    try:
        client = create_tracked_gemini_client(
            genai.Client,
            "content_translation",
            api_key=settings.GEMINI_API_KEY,
        )
        system_prompt = _build_translation_prompt(target_locale)

        response = client.models.generate_content(
            model=settings.LLM_MODEL_NAME,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_json_schema=TranslatedInternshipContent.model_json_schema(),
            ),
        )

        if response is None:
            logger.warning("Gemini translation returned no content.")
            return None

        raw_text = getattr(response, "text", None)
        if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
            logger.warning("Gemini translation returned empty response text.")
            return None

        return TranslatedInternshipContent.model_validate_json(raw_text)
    except Exception as err:
        logger.warning("Gemini translation call failed: %s", type(err).__name__)
        return None


def translate_internship_content(
    internship_id: UUID,
    description: Optional[str],
    min_education: Optional[str],
    target_locale: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Translate internship free-form fields for display in target locale.
    Returns (translated_description, translated_min_education).

    Safety and cost controls:
    - locale='en': Returns canonical values immediately (no Redis, no Gemini).
    - Empty source fields: Returns canonical values immediately (no Redis, no Gemini).
    - Redis unavailable: Returns canonical values immediately (no Gemini).
    - Redis healthy + Cache hit: Returns cached translated values (no Gemini).
    - Redis healthy + Failure sentinel: Returns canonical values immediately (cooldown active).
    - Redis healthy + Cache miss: Acquires stampede lock, calls Gemini once, caches result.
    - Gemini failure: Sets failure sentinel, returns canonical values with HTTP 200.
    """
    # 1. English or unsupported locale -> Canonical immediately
    if target_locale not in ("tr", "ar"):
        return description, min_education

    # 2. Empty source short-circuit
    has_desc = bool(description and description.strip())
    has_edu = bool(min_education and min_education.strip())
    if not has_desc and not has_edu:
        return description, min_education

    source_hash = compute_internship_content_hash(description, min_education)
    cache_key = (
        f"internmatch:i18n:internship:{CACHE_VERSION}:{internship_id}:{target_locale}:{source_hash}"
    )
    lock_key = (
        f"internmatch:i18n:internship:{CACHE_VERSION}:lock:"
        f"{internship_id}:{target_locale}:{source_hash}"
    )
    failure_key = (
        f"internmatch:i18n:internship:{CACHE_VERSION}:failure:"
        f"{internship_id}:{target_locale}:{source_hash}"
    )

    # 3. Redis lookup & Stampede protection
    try:
        client = _get_redis_client()
        # Test connection / ping implicitly on first call
        cached_data = client.get(cache_key)
        if cached_data:
            try:
                validated = TranslatedInternshipContent.model_validate_json(cached_data)
                return (
                    validated.description if validated.description is not None else description,
                    validated.min_education
                    if validated.min_education is not None
                    else min_education,
                )
            except Exception as parse_err:
                logger.warning(
                    "Corrupted cached translation encountered; clearing key: %s", parse_err
                )
                client.delete(cache_key)

        failure_sentinel = client.get(failure_key)
        if failure_sentinel:
            # Active cooldown from recent provider failure; return canonical safely
            return description, min_education

        # Cache miss: Attempt stampede lock
        lock_acquired = client.set(lock_key, "1", nx=True, ex=LOCK_TTL_SECONDS)
        if not lock_acquired:
            # Another request is currently translating; re-check cache once
            rechecked = client.get(cache_key)
            if rechecked:
                try:
                    validated = TranslatedInternshipContent.model_validate_json(rechecked)
                    return (
                        validated.description if validated.description is not None else description,
                        validated.min_education
                        if validated.min_education is not None
                        else min_education,
                    )
                except Exception:
                    pass
            # Lock held or cache unavailable; fall back to canonical without duplicate call
            return description, min_education

    except Exception as redis_err:
        # Redis is down or unreachable; DO NOT call Gemini on public requests
        logger.warning(
            "Redis unavailable for content translation (%s); returning canonical content.",
            type(redis_err).__name__,
        )
        return description, min_education

    # 4. Lock acquired: Execute Gemini translation
    try:
        # Re-check cache under lock
        cached_data = client.get(cache_key)
        if cached_data:
            try:
                validated = TranslatedInternshipContent.model_validate_json(cached_data)
                return (
                    validated.description if validated.description is not None else description,
                    validated.min_education
                    if validated.min_education is not None
                    else min_education,
                )
            except Exception:
                pass

        translated = _call_gemini_translation(
            description=description,
            min_education=min_education,
            target_locale=target_locale,
        )

        if translated is not None:
            # Store in Redis cache
            try:
                client.set(
                    cache_key,
                    translated.model_dump_json(),
                    ex=CACHE_TTL_SECONDS,
                )
            except Exception as cache_write_err:
                logger.warning("Failed to write translation cache: %s", cache_write_err)

            return (
                translated.description if translated.description is not None else description,
                translated.min_education if translated.min_education is not None else min_education,
            )
        else:
            # Set failure sentinel in Redis to prevent repeated calls
            try:
                client.set(failure_key, "1", ex=FAILURE_SENTINEL_TTL_SECONDS)
            except Exception:
                pass
            return description, min_education

    except Exception as redis_err:
        logger.warning(
            "Redis unavailable after translation lock acquisition (%s); "
            "returning canonical content.",
            type(redis_err).__name__,
        )
        return description, min_education
