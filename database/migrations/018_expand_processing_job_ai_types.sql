-- Expand durable processing_jobs to cover all user-facing long-running AI
-- operations that require authoritative cancellation semantics.
--
-- Existing job types remain unchanged. This migration only broadens the
-- allowed values of ck_processing_jobs_job_type.

-- Migration 001 created the original job_type CHECK without an explicit
-- constraint name. PostgreSQL therefore names it
-- processing_jobs_job_type_check. Drop both that legacy generated name and
-- the canonical name so this migration is safe for existing databases and
-- fresh migration chains.
ALTER TABLE public.processing_jobs
    DROP CONSTRAINT IF EXISTS processing_jobs_job_type_check;

ALTER TABLE public.processing_jobs
    DROP CONSTRAINT IF EXISTS ck_processing_jobs_job_type;

ALTER TABLE public.processing_jobs
    ADD CONSTRAINT ck_processing_jobs_job_type
    CHECK (
        job_type IN (
            'cv_extraction',
            'match_calculation',
            'application_generation',
            'match_explanation',
            'interview_prep'
        )
    );
