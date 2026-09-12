"""
Google Gemini Embedding Service Foundation
Provides reusable synchronous provider boundary for generating text embeddings
via Google Gemini API (google-genai SDK).
"""

import math
from typing import List

from google import genai
from google.genai import types

from openai import OpenAI

from app.core.config import settings
from app.services.ai_telemetry import create_tracked_gemini_client


def _generate_gemini_embedding(text: str) -> List[float]:
    """
    Generate floating point embedding vector for text using Google Gemini API.
    Validates inputs, constructs Gemini client dynamically, requests embeddings
    matching project config model/dimensions (1536), and strictly validates provider output.
    """
    if not isinstance(text, str):
        raise TypeError(f"text input must be a string, got {type(text).__name__}")

    if not text.strip():
        raise ValueError("text input cannot be empty or whitespace-only")

    api_key = settings.GEMINI_API_KEY.strip() if settings.GEMINI_API_KEY else ""
    if not api_key or "placeholder" in api_key.lower():
        raise ValueError("GEMINI_API_KEY configuration is missing or empty")

    client = create_tracked_gemini_client(
        genai.Client,
        "embedding",
        api_key=settings.GEMINI_API_KEY,
    )
    response = client.models.embed_content(
        model=settings.EMBEDDING_MODEL_NAME,
        contents=text,
        config=types.EmbedContentConfig(
            output_dimensionality=settings.EMBEDDING_DIMENSION,
        ),
    )

    if not hasattr(response, "embeddings") or not response.embeddings:
        raise ValueError("Gemini embedding API response returned empty embeddings")

    first_item = response.embeddings[0]
    raw_embedding = getattr(first_item, "values", None)
    if raw_embedding is None:
        raise ValueError("Gemini embedding result item contains no embedding vector")

    if not isinstance(raw_embedding, (list, tuple)):
        raise ValueError("Gemini embedding result is not a valid sequence")

    if len(raw_embedding) != settings.EMBEDDING_DIMENSION:
        raise ValueError(
            f"Embedding dimension mismatch: expected {settings.EMBEDDING_DIMENSION}, "
            f"got {len(raw_embedding)}"
        )

    result_vector: List[float] = []
    for val in raw_embedding:
        if val is None or not isinstance(val, (int, float)) or isinstance(val, bool):
            raise ValueError("Embedding vector contains non-numeric element")
        float_val = float(val)
        if math.isnan(float_val) or math.isinf(float_val):
            raise ValueError("Embedding vector contains non-finite float value (NaN or Inf)")
        result_vector.append(float_val)

    return result_vector

def _generate_openai_embedding(
    text: str,
) -> list[float]:
    """
    Generate one embedding in the canonical OpenAI vector space.

    This function never falls back to Gemini. Mixing providers in one
    vector index would make cosine similarity semantically invalid.
    """
    if not isinstance(text, str):
        raise TypeError(
            f"text input must be a string, got {type(text).__name__}"
        )

    if not text.strip():
        raise ValueError(
            "text input cannot be empty or whitespace-only"
        )

    api_key = (
        settings.OPENAI_API_KEY.strip()
        if settings.OPENAI_API_KEY
        else ""
    )

    if (
        not api_key
        or "placeholder" in api_key.lower()
    ):
        raise ValueError(
            "OPENAI_API_KEY configuration is missing or placeholder."
        )

    model = (
        settings.OPENAI_EMBEDDING_MODEL_NAME or ""
    ).strip()

    if not model:
        raise ValueError(
            "OPENAI_EMBEDDING_MODEL_NAME configuration is missing."
        )

    dimension = settings.EMBEDDING_DIMENSION

    if dimension <= 0:
        raise ValueError(
            "EMBEDDING_DIMENSION must be greater than zero."
        )

    client = OpenAI(
        api_key=api_key,
    )

    response = client.embeddings.create(
        model=model,
        input=text,
        dimensions=dimension,
    )

    data = getattr(
        response,
        "data",
        None,
    )

    if not data:
        raise ValueError(
            "OpenAI embedding response contained no embedding data."
        )

    raw_embedding = getattr(
        data[0],
        "embedding",
        None,
    )

    if not isinstance(raw_embedding, list):
        raise ValueError(
            "OpenAI embedding response contained an invalid vector."
        )

    if len(raw_embedding) != dimension:
        raise ValueError(
            "OpenAI embedding dimension mismatch: "
            f"expected {dimension}, got {len(raw_embedding)}."
        )

    embedding: list[float] = []

    for value in raw_embedding:
        if (
            value is None
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
        ):
            raise ValueError(
                "Embedding vector contains non-numeric element"
            )

        float_value = float(value)

        if (
            math.isnan(float_value)
            or math.isinf(float_value)
        ):
            raise ValueError(
                "Embedding vector contains non-finite float value "
                "(NaN or Inf)"
            )

        embedding.append(float_value)

    return embedding


def generate_embedding(
    text: str,
) -> list[float]:
    """
    Generate an embedding using exactly one canonical vector provider.

    There is intentionally no Gemini -> OpenAI or OpenAI -> Gemini
    per-request fallback. Changing providers requires re-embedding the
    entire candidate + internship vector space.
    """
    provider = (
        settings.EMBEDDING_PROVIDER or ""
    ).strip().lower()

    if provider == "openai":
        return _generate_openai_embedding(
            text
        )

    if provider == "gemini":
        return _generate_gemini_embedding(
            text
        )

    raise ValueError(
        "Unsupported EMBEDDING_PROVIDER configuration."
    )
