-- Expand durable processing_jobs to cover all user-facing long-running AI
-- operations that require authoritative cancellation semantics.
--
-- Existing job types remain unchanged. This migration only broadens the
-- allowed values of ck_processing_jobs_job_type.

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
