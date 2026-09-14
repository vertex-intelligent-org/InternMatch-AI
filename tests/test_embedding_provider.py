from types import SimpleNamespace

import pytest
from app.core.config import settings
from app.services import embeddings


class _FakeOpenAIEmbeddings:
    def create(
        self,
        *,
        model,
        input,
        dimensions,
    ):
        assert model == "text-embedding-3-small"
        assert input == "canonical vector input"
        assert dimensions == 1536

        return SimpleNamespace(
            data=[
                SimpleNamespace(
                    embedding=[0.125] * dimensions
                )
            ]
        )


class _FakeOpenAI:
    def __init__(
        self,
        *,
        api_key,
    ):
        assert api_key == "test-openai-key"
        self.embeddings = _FakeOpenAIEmbeddings()


def test_openai_is_canonical_embedding_provider(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "EMBEDDING_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "OPENAI_API_KEY",
        "test-openai-key",
    )
    monkeypatch.setattr(
        settings,
        "OPENAI_EMBEDDING_MODEL_NAME",
        "text-embedding-3-small",
    )
    monkeypatch.setattr(
        settings,
        "EMBEDDING_DIMENSION",
        1536,
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        _FakeOpenAI,
    )

    def forbidden_gemini(_text):
        raise AssertionError(
            "Gemini must not be called when OpenAI "
            "is the canonical embedding provider."
        )

    monkeypatch.setattr(
        embeddings,
        "_generate_gemini_embedding",
        forbidden_gemini,
    )

    vector = embeddings.generate_embedding(
        "canonical vector input"
    )

    assert len(vector) == 1536
    assert vector[0] == pytest.approx(0.125)


def test_gemini_provider_remains_explicitly_supported(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "EMBEDDING_PROVIDER",
        "gemini",
    )

    expected = [0.25] * 1536

    monkeypatch.setattr(
        embeddings,
        "_generate_gemini_embedding",
        lambda text: expected
        if text == "candidate"
        else None,
    )

    assert (
        embeddings.generate_embedding(
            "candidate"
        )
        == expected
    )


def test_invalid_embedding_provider_fails_closed(
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "EMBEDDING_PROVIDER",
        "mixed",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported EMBEDDING_PROVIDER",
    ):
        embeddings.generate_embedding(
            "candidate"
        )


def test_openai_embedding_dimension_is_enforced(
    monkeypatch,
):
    class BadEmbeddings:
        def create(self, **kwargs):
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        embedding=[0.1, 0.2]
                    )
                ]
            )

    class BadOpenAI:
        def __init__(self, *, api_key):
            self.embeddings = BadEmbeddings()

    monkeypatch.setattr(
        settings,
        "EMBEDDING_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "OPENAI_API_KEY",
        "test-openai-key",
    )
    monkeypatch.setattr(
        settings,
        "OPENAI_EMBEDDING_MODEL_NAME",
        "text-embedding-3-small",
    )
    monkeypatch.setattr(
        settings,
        "EMBEDDING_DIMENSION",
        1536,
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        BadOpenAI,
    )

    with pytest.raises(
        ValueError,
        match="dimension mismatch",
    ):
        embeddings.generate_embedding(
            "canonical vector input"
        )
