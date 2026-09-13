-- InternMatch AI - Private Employer Compliance Evidence Storage
-- Target Engine: Supabase PostgreSQL 15+ / Supabase Storage
-- Migration: 025_add_employer_compliance_storage_bucket.sql
--
-- This bucket stores evidence supporting jurisdiction-scoped compliance
-- claims. Organization identity verification remains a separate authority.
--
-- There are intentionally no anon/authenticated storage policies.
-- All access is mediated by the trusted FastAPI backend using service-role
-- credentials after server-side employer/admin authorization.

INSERT INTO storage.buckets (
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types
)
VALUES (
    'employer-compliance-evidence',
    'employer-compliance-evidence',
    false,
    10485760,
    ARRAY['application/pdf']
)
ON CONFLICT (id) DO UPDATE SET
    public = false,
    file_size_limit = 10485760,
    allowed_mime_types = ARRAY['application/pdf'];
