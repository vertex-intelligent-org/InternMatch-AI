"""Cross-provider generation failover regression tests."""

from types import SimpleNamespace

import pytest
from app.core.config import settings
from app.services import ai_telemetry


class ProviderError(RuntimeError):
    def __init__(self, status_code: int):
        super().__init__(f"provider error {status_code}")
        self.status_code = status_code


def _tracked_client(models):
    class Client:
        def __init__(self):
            self.models = models

    return ai_telemetry.create_tracked_gemini_client(
        Client,
        "provider_failover_test",
    )


def test_generation_falls_back_to_openai_after_gemini_chain(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "LLM_FALLBACK_MODEL_NAMES",
        "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash",
    )

    gemini_calls = []

    class Models:
        def generate_content(self, **kwargs):
            gemini_calls.append(kwargs["model"])
            raise ProviderError(429)

    expected = SimpleNamespace(
        text='{"ok":true}',
    )

    fallback_calls = []

    def fake_openai_fallback(
        *,
        kwargs,
        operation,
    ):
        fallback_calls.append(
            {
                "kwargs": kwargs,
                "operation": operation,
            }
        )
        return expected

    monkeypatch.setattr(
        ai_telemetry,
        "_try_openai_generation_fallback",
        fake_openai_fallback,
    )

    result = (
        _tracked_client(Models())
        .models.generate_content(
            model="gemini-3.5-flash",
            contents="test",
            config=object(),
        )
    )

    assert result is expected

    assert gemini_calls == [
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
    ]

    assert len(fallback_calls) == 1


def test_provider_auth_failure_goes_directly_to_openai(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "LLM_FALLBACK_MODEL_NAMES",
        "gemini-3.8-flash,gemini-3.7-flash",
    )

    gemini_calls = []

    class Models:
        def generate_content(self, **kwargs):
            gemini_calls.append(kwargs["model"])
            raise ProviderError(403)

    expected = SimpleNamespace(
        text='{"ok":true}',
    )

    fallback_calls = []

    def fake_openai_fallback(
        *,
        kwargs,
        operation,
    ):
        fallback_calls.append(operation)
        return expected

    monkeypatch.setattr(
        ai_telemetry,
        "_try_openai_generation_fallback",
        fake_openai_fallback,
    )

    result = (
        _tracked_client(Models())
        .models.generate_content(
            model="gemini-3.5-flash",
            contents="test",
        )
    )

    assert result is expected
    assert gemini_calls == [
        "gemini-3.5-flash",
    ]
    assert fallback_calls == [
        "provider_failover_test",
    ]


def test_generation_does_not_cross_provider_on_bad_request(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "LLM_FALLBACK_MODEL_NAMES",
        "gemini-3.8-flash",
    )

    class Models:
        def generate_content(self, **_kwargs):
            raise ProviderError(400)

    called = False

    def fake_openai_fallback(
        *,
        kwargs,
        operation,
    ):
        nonlocal called
        called = True
        return SimpleNamespace(text="unexpected")

    monkeypatch.setattr(
        ai_telemetry,
        "_try_openai_generation_fallback",
        fake_openai_fallback,
    )

    with pytest.raises(ProviderError):
        (
            _tracked_client(Models())
            .models.generate_content(
                model="gemini-3.5-flash",
                contents="test",
            )
        )

    assert called is False


def test_embeddings_never_cross_provider(
    monkeypatch,
):
    class Models:
        def embed_content(self, **_kwargs):
            raise ProviderError(429)

    called = False

    def fake_openai_fallback(
        *,
        kwargs,
        operation,
    ):
        nonlocal called
        called = True
        return SimpleNamespace(text="unexpected")

    monkeypatch.setattr(
        ai_telemetry,
        "_try_openai_generation_fallback",
        fake_openai_fallback,
    )

    with pytest.raises(ProviderError):
        (
            _tracked_client(Models())
            .models.embed_content(
                model="gemini-embedding-2",
                contents="test",
            )
        )

    assert called is False


def test_provider_billing_depletion_goes_directly_to_openai(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "LLM_FALLBACK_MODEL_NAMES",
        "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash",
    )

    gemini_calls = []

    class BillingProviderError(RuntimeError):
        status_code = 429

        def __init__(self):
            super().__init__(
                "429 RESOURCE_EXHAUSTED. "
                "Your prepayment credits are depleted. "
                "Please manage your project and billing."
            )

    class Models:
        def generate_content(
            self,
            **kwargs,
        ):
            gemini_calls.append(
                kwargs["model"]
            )

            raise BillingProviderError()

    expected = SimpleNamespace(
        text='{"ok":true}',
    )

    fallback_calls = []

    def fake_openai_fallback(
        *,
        kwargs,
        operation,
    ):
        fallback_calls.append(
            operation
        )

        return expected

    monkeypatch.setattr(
        ai_telemetry,
        "_try_openai_generation_fallback",
        fake_openai_fallback,
    )

    result = (
        _tracked_client(
            Models()
        )
        .models.generate_content(
            model="gemini-3.5-flash",
            contents="test",
        )
    )

    assert result is expected

    assert gemini_calls == [
        "gemini-3.5-flash",
    ]

    assert fallback_calls == [
        "provider_failover_test",
    ]


def test_generic_429_remains_model_level_failover():
    class Generic429(RuntimeError):
        status_code = 429

    exc = Generic429(
        "429 Too Many Requests. "
        "Temporary rate limit exceeded."
    )

    assert (
        ai_telemetry._is_gemini_account_wide_failure(
            exc
        )
        is False
    )


def test_billing_429_is_account_wide_failure():
    class Billing429(RuntimeError):
        status_code = 429

    exc = Billing429(
        "429 RESOURCE_EXHAUSTED. "
        "Your prepayment credits are depleted. "
        "Please manage your project and billing."
    )

    assert (
        ai_telemetry._is_gemini_account_wide_failure(
            exc
        )
        is True
    )
