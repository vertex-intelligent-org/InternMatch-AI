"""Independent OpenAI fallback for Gemini generation requests.

This module intentionally adapts only the subset of the Gemini generate_content
contract used by InternMatch AI. Embeddings remain Gemini-only.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any

from app.core.config import settings


def _configured_api_key() -> str:
    value = (
        settings.OPENAI_API_KEY.strip()
        if settings.OPENAI_API_KEY
        else ""
    )

    if not value or "placeholder" in value.lower():
        return ""

    return value


def openai_fallback_enabled() -> bool:
    return bool(_configured_api_key())


def _schema_from_config(config: Any) -> dict[str, Any] | None:
    if config is None:
        return None

    json_schema = getattr(
        config,
        "response_json_schema",
        None,
    )

    if isinstance(json_schema, dict):
        return json_schema

    response_schema = getattr(
        config,
        "response_schema",
        None,
    )

    model_json_schema = getattr(
        response_schema,
        "model_json_schema",
        None,
    )

    if callable(model_json_schema):
        value = model_json_schema()

        if isinstance(value, dict):
            return value

    return None


def _system_instruction(config: Any) -> str | None:
    if config is None:
        return None

    value = getattr(
        config,
        "system_instruction",
        None,
    )

    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _part_inline_bytes(
    part: Any,
) -> tuple[bytes, str] | None:
    inline_data = getattr(
        part,
        "inline_data",
        None,
    )

    if inline_data is None:
        return None

    data = getattr(
        inline_data,
        "data",
        None,
    )

    mime_type = getattr(
        inline_data,
        "mime_type",
        None,
    )

    if not isinstance(data, (bytes, bytearray)):
        return None

    clean_mime = (
        mime_type.strip()
        if isinstance(mime_type, str)
        and mime_type.strip()
        else "application/octet-stream"
    )

    return bytes(data), clean_mime


def _openai_input(contents: Any) -> Any:
    if isinstance(contents, str):
        return contents

    if not isinstance(contents, (list, tuple)):
        return str(contents)

    content_items: list[dict[str, Any]] = []

    for item in contents:
        if isinstance(item, str):
            content_items.append(
                {
                    "type": "input_text",
                    "text": item,
                }
            )
            continue

        inline = _part_inline_bytes(item)

        if inline is not None:
            data, mime_type = inline
            encoded = base64.b64encode(data).decode("ascii")

            extension = {
                "application/pdf": "pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
            }.get(
                mime_type,
                "bin",
            )

            content_items.append(
                {
                    "type": "input_file",
                    "filename": f"internmatch_document.{extension}",
                    "file_data": encoded,
                }
            )
            continue

        text_value = getattr(
            item,
            "text",
            None,
        )

        if isinstance(text_value, str) and text_value.strip():
            content_items.append(
                {
                    "type": "input_text",
                    "text": text_value,
                }
            )
            continue

        content_items.append(
            {
                "type": "input_text",
                "text": str(item),
            }
        )

    return [
        {
            "role": "user",
            "content": content_items,
        }
    ]


def _compatible_response(
    response: Any,
) -> Any:
    output_text = getattr(
        response,
        "output_text",
        None,
    )

    if not isinstance(output_text, str):
        output_text = ""

    usage = getattr(
        response,
        "usage",
        None,
    )

    input_tokens = getattr(
        usage,
        "input_tokens",
        None,
    )

    output_tokens = getattr(
        usage,
        "output_tokens",
        None,
    )

    total_tokens = getattr(
        usage,
        "total_tokens",
        None,
    )

    if (
        total_tokens is None
        and isinstance(input_tokens, int)
        and isinstance(output_tokens, int)
    ):
        total_tokens = input_tokens + output_tokens

    usage_metadata = SimpleNamespace(
        prompt_token_count=input_tokens,
        candidates_token_count=output_tokens,
        thoughts_token_count=0,
        total_token_count=total_tokens,
        cached_content_token_count=0,
    )

    return SimpleNamespace(
        text=output_text,
        usage_metadata=usage_metadata,
    )


def generate_openai_fallback(
    *,
    contents: Any,
    config: Any,
) -> tuple[Any, str] | None:
    """Run one independent provider attempt.

    Returns None when OpenAI fallback is intentionally not configured.
    Provider errors propagate to the caller.
    """

    api_key = _configured_api_key()

    if not api_key:
        return None

    from openai import OpenAI

    model = (
        settings.OPENAI_FALLBACK_MODEL_NAME.strip()
        if settings.OPENAI_FALLBACK_MODEL_NAME
        else ""
    )

    if not model:
        raise RuntimeError(
            "OPENAI_FALLBACK_MODEL_NAME is missing."
        )

    client = OpenAI(
        api_key=api_key,
        max_retries=0,
        timeout=30.0,
    )

    schema = _schema_from_config(config)

    request: dict[str, Any] = {
        "model": model,
        "input": _openai_input(contents),
    }

    instructions = _system_instruction(config)

    if instructions:
        request["instructions"] = instructions

    if schema is not None:
        request["text"] = {
            "format": {
                "type": "json_schema",
                "name": "internmatch_response",
                "schema": schema,
                # Pydantic validation remains authoritative downstream.
                # Avoid rejecting provider-compatible schemas solely because
                # they do not meet every strict Structured Outputs constraint.
                "strict": False,
            }
        }

    response = client.responses.create(
        **request
    )

    return (
        _compatible_response(response),
        model,
    )
