"""
Google Gemini Embedding Service Foundation
Provides reusable synchronous provider boundary for generating text embeddings
via Google Gemini API (google-genai SDK).
"""

import math
from typing import List

from google import genai
from google.genai import types

from app.core.config import settings
from app.services.ai_telemetry import create_tracked_gemini_client


def generate_embedding(text: str) -> List[float]:
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
