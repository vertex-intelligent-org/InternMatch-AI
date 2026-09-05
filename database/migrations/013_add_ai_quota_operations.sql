-- InternMatch AI ? SUB-3 Atomic AI Quota Operation Ledger
-- Target Engine: Supabase PostgreSQL 15+
--
-- Each row represents one quota-controlled AI operation lifecycle:
--
-- reserved:
--   capacity was atomically reserved before expensive work.
--
-- settled:
--   expensive work succeeded and one unit became consumed usage.
--
-- released:
--   work failed/cancelled before successful completion; capacity returned.
--
-- Idempotency is scoped to user + feature + quota period so a retry inside
-- one period cannot double-charge, while the same client key may be reused
-- safely after a future quota reset.

CREATE TABLE IF NOT EXISTS public.ai_quota_operations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    feature_key TEXT NOT NULL,
    plan_key TEXT NOT NULL,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_fingerprint TEXT,
    status TEXT NOT NULL DEFAULT 'reserved',
    processing_job_id UUID
        REFERENCES public.processing_jobs(id)
        ON DELETE SET NULL,
    reserved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    settled_at TIMESTAMPTZ,
    released_at TIMESTAMPTZ,
    release_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ai_quota_operations_idempotency
        UNIQUE (
            user_id,
            feature_key,
            period_start,
            idempotency_key
        ),

    CONSTRAINT ck_ai_quota_operations_feature_key
        CHECK (
            feature_key IN (
                'cv_analysis',
                'match_explanation',
                'application_support',
                'interview_prep'
            )
        ),

    CONSTRAINT ck_ai_quota_operations_plan_key
        CHECK (
            plan_key IN ('free', 'pro_student')
        ),

    CONSTRAINT ck_ai_quota_operations_status
        CHECK (
            status IN (
                'reserved',
                'settled',
                'released'
            )
        ),

    CONSTRAINT ck_ai_quota_operations_period
        CHECK (
            period_end > period_start
        )
);

CREATE INDEX IF NOT EXISTS idx_ai_quota_operations_user_feature_status
    ON public.ai_quota_operations(
        user_id,
        feature_key,
        status
    );

CREATE INDEX IF NOT EXISTS idx_ai_quota_operations_processing_job
    ON public.ai_quota_operations(processing_job_id)
    WHERE processing_job_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ai_quota_operations_created_at
    ON public.ai_quota_operations(created_at);

ALTER TABLE public.ai_quota_operations
    ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.ai_quota_operations
    FROM PUBLIC, anon, authenticated;

GRANT ALL ON public.ai_quota_operations
    TO service_role;
