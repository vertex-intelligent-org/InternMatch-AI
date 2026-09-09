"""Gemini multi-model transient failover tests."""

import pytest
from app.core.config import settings
from app.services.ai_telemetry import (
    create_tracked_gemini_client,
)


class _ProviderError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


class _FakeClient:
    def __init__(
        self,
        models,
    ) -> None:
        self.models = models


def _tracked_client(models):
    return create_tracked_gemini_client(
        lambda: _FakeClient(models),
        "gemini_failover_test",
    )


@pytest.mark.parametrize(
    "status_code",
    [
        408,
        503,
    ],
)
def test_transient_status_falls_back_to_next_model(
    monkeypatch,
    status_code,
):
    monkeypatch.setattr(
        settings,
        "LLM_FALLBACK_MODEL_NAMES",
        (
            "gemini-3.8-flash,"
            "gemini-3.7-flash,"
            "gemini-3.6-flash"
        ),
    )

    calls = []
    expected = object()

    class Models:
        def generate_content(
            self,
            *args,
            **kwargs,
        ):
            model = kwargs["model"]
            calls.append(model)

            if model == "gemini-3.5-flash":
                raise _ProviderError(
                    status_code,
                    "temporarily unavailable",
                )

            return expected

    response = (
        _tracked_client(Models())
        .models.generate_content(
            model="gemini-3.5-flash",
            contents="test",
        )
    )

    assert response is expected
    assert calls == [
        "gemini-3.5-flash",
        "gemini-3.8-flash",
    ]


def test_non_transient_400_does_not_fallback(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "LLM_FALLBACK_MODEL_NAMES",
        "gemini-3.8-flash",
    )

    calls = []

    class Models:
        def generate_content(
            self,
            *args,
            **kwargs,
        ):
            model = kwargs["model"]
            calls.append(model)

            raise _ProviderError(
                400,
                "invalid request",
            )

    with pytest.raises(
        _ProviderError,
        match="invalid request",
    ):
        (
            _tracked_client(Models())
            .models.generate_content(
                model="gemini-3.5-flash",
                contents="test",
            )
        )

    assert calls == [
        "gemini-3.5-flash",
    ]


def test_all_transient_models_are_attempted_once(
    monkeypatch,
):
    # This test covers Gemini model-level failover only.
    # Cross-provider behavior is covered separately by
    # test_provider_failover.py.
    monkeypatch.setattr(
        settings,
        "OPENAI_API_KEY",
        "",
    )
    monkeypatch.setattr(
        settings,
        "LLM_FALLBACK_MODEL_NAMES",
        (
            "gemini-3.5-flash,"
            "gemini-3.8-flash,"
            "gemini-3.7-flash,"
            "gemini-3.6-flash"
        ),
    )

    calls = []

    class Models:
        def generate_content(
            self,
            *args,
            **kwargs,
        ):
            model = kwargs["model"]
            calls.append(model)

            raise _ProviderError(
                503,
                f"{model} unavailable",
            )

    with pytest.raises(
        _ProviderError,
        match="gemini-3.6-flash unavailable",
    ):
        (
            _tracked_client(Models())
            .models.generate_content(
                model="gemini-3.5-flash",
                contents="test",
            )
        )

    assert calls == [
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
    ]


def test_successful_primary_does_not_use_fallback(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "LLM_FALLBACK_MODEL_NAMES",
        (
            "gemini-3.8-flash,"
            "gemini-3.7-flash"
        ),
    )

    calls = []
    expected = object()

    class Models:
        def generate_content(
            self,
            *args,
            **kwargs,
        ):
            calls.append(
                kwargs["model"]
            )
            return expected

    response = (
        _tracked_client(Models())
        .models.generate_content(
            model="gemini-3.5-flash",
            contents="test",
        )
    )

    assert response is expected
    assert calls == [
        "gemini-3.5-flash",
    ]


def test_embed_content_never_uses_generation_fallback(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "LLM_FALLBACK_MODEL_NAMES",
        "gemini-3.8-flash",
    )

    calls = []
    expected = object()

    class Models:
        def embed_content(
            self,
            *args,
            **kwargs,
        ):
            calls.append(
                kwargs["model"]
            )
            return expected

    response = (
        _tracked_client(Models())
        .models.embed_content(
            model="gemini-embedding-2",
            contents="test",
        )
    )

    assert response is expected
    assert calls == [
        "gemini-embedding-2",
    ]
