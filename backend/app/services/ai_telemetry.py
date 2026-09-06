"""Server-side Gemini usage, latency, and estimated-cost telemetry."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from time import perf_counter
from typing import Any, Callable, Iterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import AIUsageEvent
from app.db.session import SessionLocal

logger = get_logger(__name__)

PROVIDER_GEMINI = "gemini"
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"

# Telemetry is best-effort and must never hold an AI request behind
# a PostgreSQL row/FK lock for an unbounded amount of time.
TELEMETRY_LOCK_TIMEOUT_MS = 1500

# Snapshot of Google's standard paid list prices verified 2026-09-05.
# This is an internal estimate, not an invoice and not Free Tier detection.
PRICING_VERSION = "google-ai-standard-paid-list-2026-09-05"

USD_PER_MILLION_TOKENS: dict[
    str,
    tuple[Decimal, Decimal],
] = {
    # input, output (output includes thinking tokens)
    "gemini-3.5-flash": (
        Decimal("1.50"),
        Decimal("9.00"),
    ),
    # Text embedding input. Embeddings have no generated token output.
    "gemini-embedding-2": (
        Decimal("0.20"),
        Decimal("0.00"),
    ),
}

_COST_QUANTUM = Decimal("0.0000000001")


@dataclass(frozen=True)
class AITelemetryContext:
    """Optional correlation metadata supplied by an orchestration boundary."""

    enabled: bool = True
    user_id: UUID | None = None
    processing_job_id: UUID | None = None
    quota_operation_id: UUID | None = None
    operation: str | None = None
    session_factory: Callable[[], Session] | None = None


_CONTEXT: ContextVar[AITelemetryContext] = ContextVar(
    "internmatch_ai_telemetry_context",
    default=AITelemetryContext(),
)



def activate_ai_telemetry_context(
    *,
    enabled: bool = True,
    user_id: UUID | None = None,
    processing_job_id: UUID | None = None,
    quota_operation_id: UUID | None = None,
    operation: str | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> Token[AITelemetryContext]:
    """Activate correlation metadata until explicitly reset."""

    return _CONTEXT.set(
        AITelemetryContext(
            enabled=enabled,
            user_id=user_id,
            processing_job_id=processing_job_id,
            quota_operation_id=quota_operation_id,
            operation=operation,
            session_factory=session_factory,
        )
    )


def reset_ai_telemetry_context(
    token: Token[AITelemetryContext],
) -> None:
    """Restore the previous telemetry context."""

    _CONTEXT.reset(token)


@contextmanager
def ai_telemetry_context(
    *,
    enabled: bool = True,
    user_id: UUID | None = None,
    processing_job_id: UUID | None = None,
    quota_operation_id: UUID | None = None,
    operation: str | None = None,
    session_factory: Callable[[], Session] | None = None,
) -> Iterator[None]:
    """Temporarily attach correlation metadata to Gemini provider calls."""

    token: Token[AITelemetryContext] = _CONTEXT.set(
        AITelemetryContext(
            enabled=enabled,
            user_id=user_id,
            processing_job_id=processing_job_id,
            quota_operation_id=quota_operation_id,
            operation=operation,
            session_factory=session_factory,
        )
    )

    try:
        yield
    finally:
        _CONTEXT.reset(token)


def _safe_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int) and value >= 0:
        return value

    return None


def _usage_attr(
    usage: Any,
    *names: str,
) -> int | None:
    if usage is None:
        return None

    for name in names:
        value = getattr(usage, name, None)
        parsed = _safe_nonnegative_int(value)

        if parsed is not None:
            return parsed

    return None


def extract_gemini_usage(
    response: Any,
    *,
    embedding: bool = False,
) -> dict[str, int | None]:
    """Extract provider-reported usage without estimating token counts."""

    usage = getattr(response, "usage_metadata", None)

    input_tokens = _usage_attr(
        usage,
        "prompt_token_count",
        "promptTokenCount",
    )
    candidate_tokens = _usage_attr(
        usage,
        "candidates_token_count",
        "candidatesTokenCount",
    )
    thought_tokens = _usage_attr(
        usage,
        "thoughts_token_count",
        "thoughtsTokenCount",
    )
    cached_input_tokens = _usage_attr(
        usage,
        "cached_content_token_count",
        "cachedContentTokenCount",
    )
    total_tokens = _usage_attr(
        usage,
        "total_token_count",
        "totalTokenCount",
    )

    if embedding:
        output_tokens = 0

        if total_tokens is None:
            total_tokens = input_tokens
    else:
        output_tokens = None

        if (
            total_tokens is not None
            and input_tokens is not None
        ):
            output_tokens = max(
                total_tokens - input_tokens,
                0,
            )
        elif (
            candidate_tokens is not None
            or thought_tokens is not None
        ):
            output_tokens = (
                (candidate_tokens or 0)
                + (thought_tokens or 0)
            )

        if (
            total_tokens is None
            and input_tokens is not None
            and output_tokens is not None
        ):
            total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "candidate_tokens": candidate_tokens,
        "thought_tokens": thought_tokens,
        "cached_input_tokens": cached_input_tokens,
    }


def estimate_standard_paid_cost_usd(
    *,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> Decimal | None:
    """Estimate list-price cost for a supported model.

    Unknown models intentionally return None instead of inventing a price.
    """

    normalized_model = (model or "").strip()

    pricing = USD_PER_MILLION_TOKENS.get(
        normalized_model
    )

    if pricing is None:
        return None

    if input_tokens is None:
        return None

    input_rate, output_rate = pricing

    safe_output_tokens = output_tokens or 0

    cost = (
        (
            Decimal(input_tokens)
            * input_rate
        )
        + (
            Decimal(safe_output_tokens)
            * output_rate
        )
    ) / Decimal(1_000_000)

    return cost.quantize(
        _COST_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def _sanitize_operation(value: str) -> str:
    normalized = (value or "").strip()

    if not normalized:
        return "unknown"

    return normalized[:128]


def _sanitize_model(value: Any) -> str:
    if not isinstance(value, str):
        return "unknown"

    normalized = value.strip()

    if not normalized:
        return "unknown"

    return normalized[:255]


def _apply_telemetry_lock_timeout(
    db: Session,
) -> None:
    """Bound PostgreSQL lock waits for best-effort telemetry."""

    bind = db.get_bind()

    if (
        bind is None
        or bind.dialect.name != "postgresql"
    ):
        return

    db.execute(
        text(
            "SET LOCAL lock_timeout = "
            f"'{TELEMETRY_LOCK_TIMEOUT_MS}ms'"
        )
    )


def _record_provider_event(
    *,
    operation: str,
    model: str,
    status: str,
    latency_ms: int,
    response: Any = None,
    embedding: bool = False,
    error: BaseException | None = None,
) -> None:
    """Persist one provider event when telemetry context is enabled.

    Telemetry persistence is best-effort and must never break the AI feature.
    """

    context = _CONTEXT.get()

    if not context.enabled:
        return

    usage = extract_gemini_usage(
        response,
        embedding=embedding,
    )

    estimated_cost = estimate_standard_paid_cost_usd(
        model=model,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
    )

    factory = (
        context.session_factory
        if context.session_factory is not None
        else SessionLocal
    )

    db = factory()

    try:
        _apply_telemetry_lock_timeout(db)

        event = AIUsageEvent(
            user_id=context.user_id,
            processing_job_id=context.processing_job_id,
            quota_operation_id=context.quota_operation_id,
            provider=PROVIDER_GEMINI,
            operation=_sanitize_operation(
                context.operation or operation
            ),
            model=_sanitize_model(model),
            status=status,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
            candidate_tokens=usage["candidate_tokens"],
            thought_tokens=usage["thought_tokens"],
            cached_input_tokens=usage[
                "cached_input_tokens"
            ],
            estimated_cost_usd=estimated_cost,
            pricing_version=(
                PRICING_VERSION
                if estimated_cost is not None
                else None
            ),
            latency_ms=max(int(latency_ms), 0),
            error_type=(
                type(error).__name__[:255]
                if error is not None
                else None
            ),
        )

        db.add(event)
        db.commit()

    except Exception as telemetry_error:
        db.rollback()

        logger.warning(
            "AI telemetry persistence failed (%s).",
            type(telemetry_error).__name__,
        )

    finally:
        db.close()



_TRANSIENT_GEMINI_STATUS_CODES = frozenset(
    {
        408,
        429,
        500,
        502,
        503,
        504,
    }
)


def _gemini_model_attempts(
    primary_model: Any,
) -> tuple[Any, ...]:
    """
    Return the ordered Gemini generation model failover chain.

    The explicitly requested model always remains primary.
    Fallbacks are only appended for Gemini generation models.
    """
    if not isinstance(primary_model, str):
        return (primary_model,)

    primary = primary_model.strip()

    if not primary:
        return (primary_model,)

    if not primary.startswith("gemini-"):
        return (primary,)

    from app.core.config import settings

    raw_fallbacks = getattr(
        settings,
        "LLM_FALLBACK_MODEL_NAMES",
        "",
    )

    fallback_models = [
        candidate.strip()
        for candidate in str(raw_fallbacks).split(",")
        if candidate.strip()
    ]

    ordered = []

    for candidate in [
        primary,
        *fallback_models,
    ]:
        if candidate not in ordered:
            ordered.append(candidate)

    return tuple(ordered)


def _provider_status_code(
    exc: Exception,
) -> int | None:
    """
    Extract an HTTP-like provider status without depending on
    one google-genai exception subclass implementation.
    """
    candidates = [
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
    ]

    response = getattr(
        exc,
        "response",
        None,
    )

    if response is not None:
        candidates.append(
            getattr(
                response,
                "status_code",
                None,
            )
        )

    for candidate in candidates:
        if candidate is None:
            continue

        try:
            return int(candidate)
        except (TypeError, ValueError):
            continue

    return None


def _is_transient_gemini_error(
    exc: Exception,
) -> bool:
    return (
        _provider_status_code(exc)
        in _TRANSIENT_GEMINI_STATUS_CODES
    )


def _replace_provider_model(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    model: Any,
) -> tuple[
    tuple[Any, ...],
    dict[str, Any],
]:
    """
    Preserve the provider call shape while replacing only
    the model argument for a fallback attempt.
    """
    next_args = list(args)
    next_kwargs = dict(kwargs)

    if "model" in next_kwargs:
        next_kwargs["model"] = model
    elif (
        next_args
        and isinstance(next_args[0], str)
    ):
        next_args[0] = model
    elif model is not None:
        next_kwargs["model"] = model

    return (
        tuple(next_args),
        next_kwargs,
    )


class _TrackedModelsProxy:
    def __init__(
        self,
        models: Any,
        *,
        operation: str,
    ) -> None:
        self._models = models
        self._operation = operation

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._models, name)

        if name not in {
            "generate_content",
            "embed_content",
        }:
            return target

        embedding = name == "embed_content"

        def tracked_call(*args: Any, **kwargs: Any) -> Any:
            model = kwargs.get("model")

            if (
                not isinstance(model, str)
                and args
                and isinstance(args[0], str)
            ):
                model = args[0]

            if name == "generate_content":
                model_attempts = _gemini_model_attempts(
                    model
                )
            else:
                model_attempts = (model,)

            for attempt_index, attempt_model in enumerate(
                model_attempts
            ):
                call_args, call_kwargs = (
                    _replace_provider_model(
                        args,
                        kwargs,
                        attempt_model,
                    )
                )

                safe_model = _sanitize_model(
                    attempt_model
                )

                started = perf_counter()

                try:
                    response = target(
                        *call_args,
                        **call_kwargs,
                    )
                except Exception as exc:
                    latency_ms = round(
                        (
                            perf_counter()
                            - started
                        )
                        * 1000
                    )

                    _record_provider_event(
                        operation=self._operation,
                        model=safe_model,
                        status=STATUS_ERROR,
                        latency_ms=latency_ms,
                        response=None,
                        embedding=embedding,
                        error=exc,
                    )

                    has_fallback = (
                        attempt_index
                        < len(model_attempts) - 1
                    )

                    if (
                        name == "generate_content"
                        and has_fallback
                        and _is_transient_gemini_error(
                            exc
                        )
                    ):
                        continue

                    raise

                latency_ms = round(
                    (
                        perf_counter()
                        - started
                    )
                    * 1000
                )

                _record_provider_event(
                    operation=self._operation,
                    model=safe_model,
                    status=STATUS_SUCCESS,
                    latency_ms=latency_ms,
                    response=response,
                    embedding=embedding,
                    error=None,
                )

                return response

            raise RuntimeError(
                "Gemini model attempt chain "
                "completed without a result."
            )

        return tracked_call


class _TrackedClientProxy:
    def __init__(
        self,
        client: Any,
        *,
        operation: str,
    ) -> None:
        self._client = client
        self._operation = operation
        self.models = _TrackedModelsProxy(
            client.models,
            operation=operation,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def create_tracked_gemini_client(
    client_factory: Callable[..., Any],
    operation: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Create a Gemini client whose provider calls can emit telemetry."""

    client = client_factory(
        *args,
        **kwargs,
    )

    return _TrackedClientProxy(
        client,
        operation=_sanitize_operation(operation),
    )
