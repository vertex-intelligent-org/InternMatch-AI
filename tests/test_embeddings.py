from types import SimpleNamespace

import pytest
from app.core.config import settings
from app.services import embeddings


def _response(vector):
    return SimpleNamespace(
        data=[
            SimpleNamespace(
                embedding=vector,
            )
        ]
    )


def _configure_openai(
    monkeypatch,
    *,
    response=None,
    exception=None,
):
    constructed_keys = []
    calls = []

    class FakeEmbeddings:
        def create(
            self,
            *,
            model,
            input,
            dimensions,
        ):
            calls.append(
                {
                    "model": model,
                    "input": input,
                    "dimensions": dimensions,
                }
            )

            if exception is not None:
                raise exception

            return response

    class FakeOpenAI:
        def __init__(self, *, api_key):
            constructed_keys.append(api_key)
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr(
        settings,
        "EMBEDDING_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "OPENAI_API_KEY",
        "openai-valid-test-key",
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
        FakeOpenAI,
    )

    return constructed_keys, calls


def test_generate_embedding_valid_text(monkeypatch):
    vector = [0.125] * 1536

    constructed_keys, calls = _configure_openai(
        monkeypatch,
        response=_response(vector),
    )

    result = embeddings.generate_embedding(
        "Software Engineer"
    )

    assert result == vector
    assert constructed_keys == [
        "openai-valid-test-key"
    ]
    assert calls == [
        {
            "model": "text-embedding-3-small",
            "input": "Software Engineer",
            "dimensions": 1536,
        }
    ]


def test_generate_embedding_preserves_original_whitespace(
    monkeypatch,
):
    vector = [0.125] * 1536

    _, calls = _configure_openai(
        monkeypatch,
        response=_response(vector),
    )

    original = "  Software Engineer  "

    embeddings.generate_embedding(original)

    assert calls[0]["input"] == original


def test_generate_embedding_empty_string_raises_value_error(
    monkeypatch,
):
    constructed_keys, _ = _configure_openai(
        monkeypatch,
        response=_response([0.1] * 1536),
    )

    with pytest.raises(
        ValueError,
        match="cannot be empty or whitespace-only",
    ):
        embeddings.generate_embedding("")

    assert constructed_keys == []


def test_generate_embedding_whitespace_only_string_raises_value_error(
    monkeypatch,
):
    constructed_keys, _ = _configure_openai(
        monkeypatch,
        response=_response([0.1] * 1536),
    )

    with pytest.raises(
        ValueError,
        match="cannot be empty or whitespace-only",
    ):
        embeddings.generate_embedding(
            "   \t\n  "
        )

    assert constructed_keys == []


def test_generate_embedding_non_string_input_raises_type_error(
    monkeypatch,
):
    constructed_keys, _ = _configure_openai(
        monkeypatch,
        response=_response([0.1] * 1536),
    )

    with pytest.raises(
        TypeError,
        match="text input must be a string",
    ):
        embeddings.generate_embedding(123)

    with pytest.raises(
        TypeError,
        match="text input must be a string",
    ):
        embeddings.generate_embedding(None)

    assert constructed_keys == []


def test_generate_embedding_empty_response_data_raises_value_error(
    monkeypatch,
):
    _configure_openai(
        monkeypatch,
        response=SimpleNamespace(data=[]),
    )

    with pytest.raises(
        ValueError,
        match="no embedding data",
    ):
        embeddings.generate_embedding(
            "Software Engineer"
        )


def test_generate_embedding_wrong_dimension_raises_value_error(
    monkeypatch,
):
    _configure_openai(
        monkeypatch,
        response=_response([0.1] * 10),
    )

    with pytest.raises(
        ValueError,
        match="dimension mismatch",
    ):
        embeddings.generate_embedding(
            "Software Engineer"
        )


def test_generate_embedding_nan_value_raises_value_error(
    monkeypatch,
):
    vector = (
        [0.1] * 1535
        + [float("nan")]
    )

    _configure_openai(
        monkeypatch,
        response=_response(vector),
    )

    with pytest.raises(
        ValueError,
        match="non-finite float value",
    ):
        embeddings.generate_embedding(
            "Software Engineer"
        )


def test_generate_embedding_positive_infinity_raises_value_error(
    monkeypatch,
):
    vector = (
        [0.1] * 1535
        + [float("inf")]
    )

    _configure_openai(
        monkeypatch,
        response=_response(vector),
    )

    with pytest.raises(
        ValueError,
        match="non-finite float value",
    ):
        embeddings.generate_embedding(
            "Software Engineer"
        )


def test_generate_embedding_negative_infinity_raises_value_error(
    monkeypatch,
):
    vector = (
        [0.1] * 1535
        + [float("-inf")]
    )

    _configure_openai(
        monkeypatch,
        response=_response(vector),
    )

    with pytest.raises(
        ValueError,
        match="non-finite float value",
    ):
        embeddings.generate_embedding(
            "Software Engineer"
        )


def test_generate_embedding_non_numeric_item_raises_value_error(
    monkeypatch,
):
    vector = (
        [0.1] * 1535
        + ["invalid_string"]
    )

    _configure_openai(
        monkeypatch,
        response=_response(vector),
    )

    with pytest.raises(
        ValueError,
        match="non-numeric element",
    ):
        embeddings.generate_embedding(
            "Software Engineer"
        )


def test_generate_embedding_boolean_item_raises_value_error(
    monkeypatch,
):
    vector = (
        [0.1] * 1535
        + [True]
    )

    _configure_openai(
        monkeypatch,
        response=_response(vector),
    )

    with pytest.raises(
        ValueError,
        match="non-numeric element",
    ):
        embeddings.generate_embedding(
            "Software Engineer"
        )


def test_generate_embedding_empty_api_key_raises_value_error(
    monkeypatch,
):
    constructed = []

    class ForbiddenOpenAI:
        def __init__(self, *, api_key):
            constructed.append(api_key)

    monkeypatch.setattr(
        settings,
        "EMBEDDING_PROVIDER",
        "openai",
    )
    monkeypatch.setattr(
        settings,
        "OPENAI_EMBEDDING_MODEL_NAME",
        "text-embedding-3-small",
    )
    monkeypatch.setattr(
        embeddings,
        "OpenAI",
        ForbiddenOpenAI,
    )

    monkeypatch.setattr(
        settings,
        "OPENAI_API_KEY",
        "",
    )

    with pytest.raises(
        ValueError,
        match="OPENAI_API_KEY configuration is missing",
    ):
        embeddings.generate_embedding(
            "Software Engineer"
        )

    monkeypatch.setattr(
        settings,
        "OPENAI_API_KEY",
        "   \t  ",
    )

    with pytest.raises(
        ValueError,
        match="OPENAI_API_KEY configuration is missing",
    ):
        embeddings.generate_embedding(
            "Software Engineer"
        )

    assert constructed == []


def test_generate_embedding_provider_exception_propagates(
    monkeypatch,
):
    error = RuntimeError(
        "OpenAI API 500 Server Error"
    )

    _configure_openai(
        monkeypatch,
        exception=error,
    )

    with pytest.raises(
        RuntimeError,
        match="OpenAI API 500 Server Error",
    ):
        embeddings.generate_embedding(
            "Software Engineer"
        )
