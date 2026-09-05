-- SUB-4A: Internal AI provider usage/cost telemetry.
-- Server-owned only. No direct client access.

CREATE TABLE IF NOT EXISTS public.ai_usage_events (
    id UUID PRIMARY KEY,
    user_id UUID NULL,
    processing_job_id UUID NULL
        REFERENCES public.processing_jobs(id)
        ON DELETE SET NULL,
    quota_operation_id UUID NULL
        REFERENCES public.ai_quota_operations(id)
        ON DELETE SET NULL,

    provider VARCHAR(32) NOT NULL DEFAULT 'gemini',
    operation VARCHAR(128) NOT NULL,
    model VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL,

    input_tokens INTEGER NULL,
    output_tokens INTEGER NULL,
    total_tokens INTEGER NULL,
    candidate_tokens INTEGER NULL,
    thought_tokens INTEGER NULL,
    cached_input_tokens INTEGER NULL,

    estimated_cost_usd NUMERIC(18, 10) NULL,
    pricing_version VARCHAR(128) NULL,
    latency_ms INTEGER NOT NULL,
    error_type VARCHAR(255) NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_ai_usage_events_provider
        CHECK (provider IN ('gemini')),
    CONSTRAINT ck_ai_usage_events_status
        CHECK (status IN ('success', 'error')),
    CONSTRAINT ck_ai_usage_events_latency_nonnegative
        CHECK (latency_ms >= 0),
    CONSTRAINT ck_ai_usage_events_input_tokens_nonnegative
        CHECK (input_tokens IS NULL OR input_tokens >= 0),
    CONSTRAINT ck_ai_usage_events_output_tokens_nonnegative
        CHECK (output_tokens IS NULL OR output_tokens >= 0),
    CONSTRAINT ck_ai_usage_events_total_tokens_nonnegative
        CHECK (total_tokens IS NULL OR total_tokens >= 0),
    CONSTRAINT ck_ai_usage_events_candidate_tokens_nonnegative
        CHECK (candidate_tokens IS NULL OR candidate_tokens >= 0),
    CONSTRAINT ck_ai_usage_events_thought_tokens_nonnegative
        CHECK (thought_tokens IS NULL OR thought_tokens >= 0),
    CONSTRAINT ck_ai_usage_events_cached_tokens_nonnegative
        CHECK (
            cached_input_tokens IS NULL
            OR cached_input_tokens >= 0
        ),
    CONSTRAINT ck_ai_usage_events_cost_nonnegative
        CHECK (
            estimated_cost_usd IS NULL
            OR estimated_cost_usd >= 0
        )
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_events_user_created
    ON public.ai_usage_events (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_usage_events_operation_created
    ON public.ai_usage_events (operation, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_usage_events_model_created
    ON public.ai_usage_events (model, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_usage_events_processing_job
    ON public.ai_usage_events (processing_job_id)
    WHERE processing_job_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ai_usage_events_quota_operation
    ON public.ai_usage_events (quota_operation_id)
    WHERE quota_operation_id IS NOT NULL;

ALTER TABLE public.ai_usage_events ENABLE ROW LEVEL SECURITY;

REVOKE ALL
ON TABLE public.ai_usage_events
FROM PUBLIC, anon, authenticated;

GRANT ALL
ON TABLE public.ai_usage_events
TO service_role;
