-- InternMatch AI ? SUB-2 AI Feature Quota Period Foundation
-- Target Engine: Supabase PostgreSQL 15+
--
-- This table stores the current aggregate server-owned quota period
-- for each user + AI feature. Plan changes and period resets update the
-- same authoritative row so concurrent requests cannot create parallel
-- quota windows. Mobile clients must never mutate usage counters directly.
--
-- used_count:
--   successfully settled AI operations.
--
-- reserved_count:
--   in-flight reservations used by SUB-3 to prevent concurrent overuse.

CREATE TABLE IF NOT EXISTS public.ai_quota_periods (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    feature_key TEXT NOT NULL,
    plan_key TEXT NOT NULL,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    used_count INTEGER NOT NULL DEFAULT 0,
    reserved_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ai_quota_periods_user_feature
        UNIQUE (
            user_id,
            feature_key
        ),

    CONSTRAINT ck_ai_quota_periods_feature_key
        CHECK (
            feature_key IN (
                'cv_analysis',
                'match_explanation',
                'application_support',
                'interview_prep'
            )
        ),

    CONSTRAINT ck_ai_quota_periods_plan_key
        CHECK (
            plan_key IN ('free', 'pro_student')
        ),

    CONSTRAINT ck_ai_quota_periods_used_count
        CHECK (used_count >= 0),

    CONSTRAINT ck_ai_quota_periods_reserved_count
        CHECK (reserved_count >= 0),

    CONSTRAINT ck_ai_quota_periods_period
        CHECK (period_end > period_start)
);

CREATE INDEX IF NOT EXISTS idx_ai_quota_periods_user_plan
    ON public.ai_quota_periods(user_id, plan_key);

CREATE INDEX IF NOT EXISTS idx_ai_quota_periods_active_lookup
    ON public.ai_quota_periods(
        user_id,
        plan_key,
        feature_key,
        period_end
    );

-- Quota authority belongs only to the backend service role.
ALTER TABLE public.ai_quota_periods ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.ai_quota_periods
    FROM PUBLIC, anon, authenticated;

GRANT ALL ON public.ai_quota_periods
    TO service_role;
