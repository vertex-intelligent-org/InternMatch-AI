"""SUB-4A internal Gemini usage/cost telemetry tests."""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.db.models import AIUsageEvent
from app.services.ai_telemetry import (
    PRICING_VERSION,
    ai_telemetry_context,
    create_tracked_gemini_client,
    estimate_standard_paid_cost_usd,
    extract_gemini_usage,
)

from tests.db import TestingSessionLocal


@pytest.fixture(autouse=True)
def clean_ai_usage_events():
    db = TestingSessionLocal()

    try:
        db.query(AIUsageEvent).delete()
        db.commit()
    finally:
        db.close()

    yield

    db = TestingSessionLocal()

    try:
        db.query(AIUsageEvent).delete()
        db.commit()
    finally:
        db.close()


def _usage_response(
    *,
    prompt: int,
    candidates: int,
    thoughts: int,
    total: int,
):
    return SimpleNamespace(
        text="ok",
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt,
            candidates_token_count=candidates,
            thoughts_token_count=thoughts,
            total_token_count=total,
            cached_content_token_count=0,
        ),
    )


def test_extract_generation_usage_includes_thinking_in_output():
    response = _usage_response(
        prompt=100,
        candidates=50,
        thoughts=25,
        total=175,
    )

    usage = extract_gemini_usage(response)

    assert usage["input_tokens"] == 100
    assert usage["candidate_tokens"] == 50
    assert usage["thought_tokens"] == 25
    assert usage["output_tokens"] == 75
    assert usage["total_tokens"] == 175


def test_current_gemini_flash_cost_estimate():
    cost = estimate_standard_paid_cost_usd(
        model="gemini-3.5-flash",
        input_tokens=1000,
        output_tokens=2000,
    )

    assert cost == Decimal("0.0195000000")


def test_embedding_cost_uses_input_only():
    cost = estimate_standard_paid_cost_usd(
        model="gemini-embedding-2",
        input_tokens=5000,
        output_tokens=0,
    )

    assert cost == Decimal("0.0010000000")


def test_unknown_model_never_invents_price():
    assert (
        estimate_standard_paid_cost_usd(
            model="future-model-not-priced",
            input_tokens=100,
            output_tokens=100,
        )
        is None
    )


def test_tracked_generation_persists_correlated_usage():
    user_id = uuid4()
    job_id = None
    quota_operation_id = None

    response = _usage_response(
        prompt=120,
        candidates=60,
        thoughts=20,
        total=200,
    )

    class FakeModels:
        def generate_content(self, **_kwargs):
            return response

    class FakeClient:
        def __init__(self):
            self.models = FakeModels()

    client = create_tracked_gemini_client(
        lambda: FakeClient(),
        "match_explanation",
    )

    with ai_telemetry_context(
        enabled=True,
        user_id=user_id,
        processing_job_id=job_id,
        quota_operation_id=quota_operation_id,
        session_factory=TestingSessionLocal,
    ):
        result = client.models.generate_content(
            model="gemini-3.5-flash",
            contents="test",
        )

    assert result is response

    db = TestingSessionLocal()

    try:
        event = db.query(AIUsageEvent).one()

        assert event.user_id == user_id
        assert event.provider == "gemini"
        assert event.operation == "match_explanation"
        assert event.model == "gemini-3.5-flash"
        assert event.status == "success"
        assert event.input_tokens == 120
        assert event.output_tokens == 80
        assert event.total_tokens == 200
        assert event.candidate_tokens == 60
        assert event.thought_tokens == 20
        assert event.estimated_cost_usd == Decimal(
            "0.0009000000"
        )
        assert event.pricing_version == PRICING_VERSION
        assert event.latency_ms >= 0
        assert event.error_type is None
    finally:
        db.close()


def test_tracked_provider_failure_is_recorded_and_reraised():
    class FakeModels:
        def generate_content(self, **_kwargs):
            raise RuntimeError("provider unavailable")

    class FakeClient:
        def __init__(self):
            self.models = FakeModels()

    client = create_tracked_gemini_client(
        lambda: FakeClient(),
        "interview_prep",
    )

    with pytest.raises(
        RuntimeError,
        match="provider unavailable",
    ):
        with ai_telemetry_context(
            enabled=True,
            session_factory=TestingSessionLocal,
        ):
            client.models.generate_content(
                model="gemini-3.5-flash",
                contents="test",
            )

    db = TestingSessionLocal()

    try:
        event = db.query(AIUsageEvent).one()

        assert event.status == "error"
        assert event.operation == "interview_prep"
        assert event.error_type == "RuntimeError"
        assert event.input_tokens is None
        assert event.output_tokens is None
        assert event.estimated_cost_usd is None
        assert event.latency_ms >= 0
    finally:
        db.close()


def test_no_explicit_context_persists_uncorrelated_usage():
    response = _usage_response(
        prompt=10,
        candidates=5,
        thoughts=0,
        total=15,
    )

    class FakeModels:
        def generate_content(self, **_kwargs):
            return response

    class FakeClient:
        def __init__(self):
            self.models = FakeModels()

    client = create_tracked_gemini_client(
        lambda: FakeClient(),
        "content_translation",
    )

    client.models.generate_content(
        model="gemini-3.5-flash",
        contents="test",
    )

    db = TestingSessionLocal()

    try:
        event = db.query(AIUsageEvent).one()

        assert event.operation == "content_translation"
        assert event.user_id is None
        assert event.processing_job_id is None
        assert event.quota_operation_id is None
        assert event.status == "success"
    finally:
        db.close()



def test_quota_execution_boundaries_bind_correlation_context():
    application_worker = Path(
        "worker/tasks/application_generation.py"
    ).read_text(encoding="utf-8")

    cv_worker = Path(
        "worker/tasks/cv_extraction.py"
    ).read_text(encoding="utf-8")

    match_service = Path(
        "backend/app/services/match_explanation.py"
    ).read_text(encoding="utf-8")

    interview_service = Path(
        "backend/app/services/interview_prep.py"
    ).read_text(encoding="utf-8")

    for source in (
        application_worker,
        cv_worker,
    ):
        assert "activate_ai_telemetry_context(" in source
        assert "processing_job_id=norm_job_id" in source
        assert "quota_operation_id=(" in source
        assert "reset_ai_telemetry_context(" in source

    assert match_service.count(
        "with ai_telemetry_context("
    ) >= 2
    assert (
        "quota_operation_id=quota_operation_id"
        in match_service
    )

    assert "with ai_telemetry_context(" in interview_service
    assert (
        "quota_operation_id=quota_operation_id"
        in interview_service
    )
