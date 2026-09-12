-- InternMatch AI - Gate 2 Employer Trust & Verification Foundation
-- Target Engine: Supabase PostgreSQL 15+
-- Migration: 019_add_employer_organization_verification.sql
--
-- Public employer account role does NOT imply company verification.
-- Verification state and reviewer authority are backend/admin controlled.

CREATE TABLE IF NOT EXISTS public.employer_organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL
        REFERENCES auth.users(id) ON DELETE CASCADE,
    legal_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    website_url TEXT NOT NULL,
    normalized_domain TEXT NOT NULL,
    business_email TEXT NOT NULL,
    country_code VARCHAR(2) NOT NULL,
    registration_number TEXT,
    tax_number TEXT,
    representative_name TEXT NOT NULL,
    representative_role TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    submitted_at TIMESTAMPTZ,
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID
        REFERENCES auth.users(id) ON DELETE SET NULL,
    rejection_reason_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_employer_organizations_owner_user_id
        UNIQUE (owner_user_id),

    CONSTRAINT ck_employer_organizations_verification_status
        CHECK (
            verification_status IN (
                'unverified',
                'pending',
                'verified',
                'rejected',
                'suspended'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_employer_organizations_owner_user_id
    ON public.employer_organizations(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_employer_organizations_verification_status
    ON public.employer_organizations(verification_status);

CREATE INDEX IF NOT EXISTS idx_employer_organizations_normalized_domain
    ON public.employer_organizations(normalized_domain);


CREATE TABLE IF NOT EXISTS public.employer_verification_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NOT NULL
        REFERENCES public.employer_organizations(id) ON DELETE CASCADE,
    reviewer_user_id UUID
        REFERENCES auth.users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    reason_code TEXT,
    internal_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_employer_verification_events_action
        CHECK (
            action IN (
                'created',
                'submitted',
                'resubmitted',
                'approved',
                'rejected',
                'suspended'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_employer_verification_events_organization_id
    ON public.employer_verification_events(organization_id);

CREATE INDEX IF NOT EXISTS idx_employer_verification_events_reviewer_user_id
    ON public.employer_verification_events(reviewer_user_id);

CREATE INDEX IF NOT EXISTS idx_employer_verification_events_created_at
    ON public.employer_verification_events(created_at);


-- Direct Supabase access hardening.
--
-- These tables contain private company verification information and internal
-- reviewer audit notes. They are server-owned and must never be readable or
-- writable directly by anon/authenticated Supabase clients.
ALTER TABLE public.employer_organizations
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.employer_verification_events
    ENABLE ROW LEVEL SECURITY;

REVOKE ALL
ON TABLE public.employer_organizations
FROM PUBLIC, anon, authenticated;

REVOKE ALL
ON TABLE public.employer_verification_events
FROM PUBLIC, anon, authenticated;

GRANT ALL
ON TABLE public.employer_organizations
TO service_role;

GRANT ALL
ON TABLE public.employer_verification_events
TO service_role;
