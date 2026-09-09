-- Expand AI telemetry provider support for independent generation failover.
-- Safe for existing Gemini rows.

ALTER TABLE public.ai_usage_events
    DROP CONSTRAINT IF EXISTS ck_ai_usage_events_provider;

ALTER TABLE public.ai_usage_events
    ADD CONSTRAINT ck_ai_usage_events_provider
    CHECK (provider IN ('gemini', 'openai'));
