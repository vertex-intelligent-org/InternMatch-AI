-- 026_expand_ai_quota_for_employer.sql
--
-- Extend the existing durable AI quota ledger for Employer AI features.
-- This migration preserves all existing Student feature keys and plans.
--
-- IMPORTANT:
-- This file is created locally by the Employer Pro implementation slice.
-- It is NOT applied automatically by application code.

BEGIN;

ALTER TABLE public.ai_quota_periods
    DROP CONSTRAINT IF EXISTS ck_ai_quota_periods_feature_key;

ALTER TABLE public.ai_quota_periods
    ADD CONSTRAINT ck_ai_quota_periods_feature_key
    CHECK (
        feature_key IN (
            'cv_analysis',
            'match_explanation',
            'application_support',
            'interview_prep',
            'employer_candidate_insight',
            'employer_interview_kit',
            'employer_shortlist_comparison',
            'employer_internship_description'
        )
    );

ALTER TABLE public.ai_quota_periods
    DROP CONSTRAINT IF EXISTS ck_ai_quota_periods_plan_key;

ALTER TABLE public.ai_quota_periods
    ADD CONSTRAINT ck_ai_quota_periods_plan_key
    CHECK (
        plan_key IN (
            'free',
            'pro_student',
            'employer_pro'
        )
    );

ALTER TABLE public.ai_quota_operations
    DROP CONSTRAINT IF EXISTS ck_ai_quota_operations_feature_key;

ALTER TABLE public.ai_quota_operations
    ADD CONSTRAINT ck_ai_quota_operations_feature_key
    CHECK (
        feature_key IN (
            'cv_analysis',
            'match_explanation',
            'application_support',
            'interview_prep',
            'employer_candidate_insight',
            'employer_interview_kit',
            'employer_shortlist_comparison',
            'employer_internship_description'
        )
    );

ALTER TABLE public.ai_quota_operations
    DROP CONSTRAINT IF EXISTS ck_ai_quota_operations_plan_key;

ALTER TABLE public.ai_quota_operations
    ADD CONSTRAINT ck_ai_quota_operations_plan_key
    CHECK (
        plan_key IN (
            'free',
            'pro_student',
            'employer_pro'
        )
    );

COMMIT;
