-- InternMatch AI - Employer Compliance Evidence Foundation
-- Target Engine: Supabase PostgreSQL 15+
-- Migration: 024_add_employer_compliance_evidence.sql
--
-- SECURITY / PRODUCT INVARIANT:
-- Organization verification proves reviewed organization identity only.
-- It MUST NOT imply insurance coverage, certificate availability,
-- university agreement, or legal internship eligibility.
--
-- Compliance claims are separate, jurisdiction-scoped assertions with
-- independent evidence, review status, validity, and audit history.


CREATE TABLE IF NOT EXISTS public.employer_compliance_claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    organization_id UUID NOT NULL
        REFERENCES public.employer_organizations(id)
        ON DELETE CASCADE,

    claim_type TEXT NOT NULL,

    jurisdiction_country_code VARCHAR(2) NOT NULL,

    -- Supports organization-wide claims and narrower scopes such as
    -- a specific university agreement or internship program.
    scope_key TEXT NOT NULL DEFAULT 'organization',
    scope_label TEXT,

    -- Employer-provided factual context. This is never proof by itself.
    statement TEXT,

    status TEXT NOT NULL DEFAULT 'draft',

    -- Monotonic optimistic-concurrency token.
    version INTEGER NOT NULL DEFAULT 1,

    submitted_at TIMESTAMPTZ,
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID
        REFERENCES auth.users(id)
        ON DELETE SET NULL,

    rejection_reason_code TEXT,

    valid_from DATE,
    valid_until DATE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_employer_compliance_claim_type
        CHECK (
            claim_type IN (
                'insurance_arrangement',
                'completion_certificate',
                'university_agreement',
                'legal_internship_eligibility'
            )
        ),

    CONSTRAINT ck_employer_compliance_claim_status
        CHECK (
            status IN (
                'draft',
                'pending',
                'approved',
                'rejected',
                'revoked',
                'expired'
            )
        ),

    CONSTRAINT ck_employer_compliance_country_code
        CHECK (
            jurisdiction_country_code ~ '^[A-Z]{2}$'
        ),

    CONSTRAINT ck_employer_compliance_scope_key
        CHECK (
            LENGTH(TRIM(scope_key)) > 0
        ),

    CONSTRAINT ck_employer_compliance_version
        CHECK (
            version > 0
        ),

    CONSTRAINT ck_employer_compliance_validity
        CHECK (
            valid_from IS NULL
            OR valid_until IS NULL
            OR valid_until >= valid_from
        ),

    CONSTRAINT uq_employer_compliance_claim_scope
        UNIQUE (
            organization_id,
            claim_type,
            jurisdiction_country_code,
            scope_key
        )
);


CREATE INDEX IF NOT EXISTS
    idx_employer_compliance_claims_organization_id
ON public.employer_compliance_claims(organization_id);

CREATE INDEX IF NOT EXISTS
    idx_employer_compliance_claims_status
ON public.employer_compliance_claims(status);

CREATE INDEX IF NOT EXISTS
    idx_employer_compliance_claims_type_country
ON public.employer_compliance_claims(
    claim_type,
    jurisdiction_country_code
);


CREATE TABLE IF NOT EXISTS public.employer_compliance_evidence (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    claim_id UUID NOT NULL
        REFERENCES public.employer_compliance_claims(id)
        ON DELETE CASCADE,

    -- Server-generated private-storage key only.
    storage_path TEXT NOT NULL,

    original_filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,

    -- Lower-case SHA-256 digest of stored bytes.
    sha256_hex VARCHAR(64) NOT NULL,

    uploaded_by_user_id UUID
        REFERENCES auth.users(id)
        ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_employer_compliance_evidence_storage_path
        UNIQUE (storage_path),

    CONSTRAINT ck_employer_compliance_evidence_content_type
        CHECK (
            content_type = 'application/pdf'
        ),

    CONSTRAINT ck_employer_compliance_evidence_size
        CHECK (
            size_bytes > 0
            AND size_bytes <= 10485760
        ),

    CONSTRAINT ck_employer_compliance_evidence_sha256
        CHECK (
            sha256_hex ~ '^[0-9a-f]{64}$'
        )
);


CREATE INDEX IF NOT EXISTS
    idx_employer_compliance_evidence_claim_id
ON public.employer_compliance_evidence(claim_id);


CREATE TABLE IF NOT EXISTS public.employer_compliance_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    claim_id UUID NOT NULL
        REFERENCES public.employer_compliance_claims(id)
        ON DELETE CASCADE,

    actor_user_id UUID
        REFERENCES auth.users(id)
        ON DELETE SET NULL,

    actor_role TEXT NOT NULL,

    action TEXT NOT NULL,

    previous_status TEXT,
    new_status TEXT NOT NULL,

    reason_code TEXT,
    internal_note TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_employer_compliance_event_actor_role
        CHECK (
            actor_role IN (
                'employer',
                'admin',
                'system'
            )
        ),

    CONSTRAINT ck_employer_compliance_event_action
        CHECK (
            action IN (
                'created',
                'updated',
                'evidence_attached',
                'submitted',
                'approved',
                'rejected',
                'revoked',
                'expired'
            )
        ),

    CONSTRAINT ck_employer_compliance_event_status
        CHECK (
            new_status IN (
                'draft',
                'pending',
                'approved',
                'rejected',
                'revoked',
                'expired'
            )
        )
);


CREATE INDEX IF NOT EXISTS
    idx_employer_compliance_events_claim_id
ON public.employer_compliance_events(claim_id);

CREATE INDEX IF NOT EXISTS
    idx_employer_compliance_events_created_at
ON public.employer_compliance_events(created_at);


-- Server-owned compliance information.
--
-- Employers and admins access this information only through the backend
-- authorization boundary. Raw storage paths and private reviewer notes must
-- never be directly readable through Supabase client credentials.

ALTER TABLE public.employer_compliance_claims
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.employer_compliance_evidence
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.employer_compliance_events
    ENABLE ROW LEVEL SECURITY;


REVOKE ALL
ON TABLE public.employer_compliance_claims
FROM PUBLIC, anon, authenticated;

REVOKE ALL
ON TABLE public.employer_compliance_evidence
FROM PUBLIC, anon, authenticated;

REVOKE ALL
ON TABLE public.employer_compliance_events
FROM PUBLIC, anon, authenticated;


GRANT ALL
ON TABLE public.employer_compliance_claims
TO service_role;

GRANT ALL
ON TABLE public.employer_compliance_evidence
TO service_role;

GRANT ALL
ON TABLE public.employer_compliance_events
TO service_role;
