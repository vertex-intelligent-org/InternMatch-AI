-- InternMatch AI - Gate 2 A5A Organization Trust Provenance
-- Target Engine: Supabase PostgreSQL 15+
-- Migration: 023_add_organization_type_and_verification_method.sql
--
-- Organization classification and verification provenance are
-- backend/admin authoritative.

ALTER TABLE public.employer_organizations
    ADD COLUMN IF NOT EXISTS organization_type TEXT;

ALTER TABLE public.employer_organizations
    ALTER COLUMN organization_type SET DEFAULT 'company';

UPDATE public.employer_organizations
SET organization_type = 'company'
WHERE organization_type IS NULL;

ALTER TABLE public.employer_organizations
    ALTER COLUMN organization_type SET NOT NULL;


ALTER TABLE public.employer_organizations
    ADD COLUMN IF NOT EXISTS verification_method TEXT;

ALTER TABLE public.employer_verification_events
    ADD COLUMN IF NOT EXISTS verification_method TEXT;


-- Organizations verified before A5A were all handled by the
-- pre-existing company verification workflow.
UPDATE public.employer_organizations
SET verification_method = 'standard_company'
WHERE verification_status IN ('verified', 'suspended')
  AND verification_method IS NULL;


-- Snapshot legacy approval/suspension provenance into immutable audit events.
UPDATE public.employer_verification_events AS event
SET verification_method = organization.verification_method
FROM public.employer_organizations AS organization
WHERE event.organization_id = organization.id
  AND event.action IN ('approved', 'suspended')
  AND event.verification_method IS NULL
  AND organization.verification_method IS NOT NULL;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname =
            'ck_employer_organizations_organization_type'
    ) THEN
        ALTER TABLE public.employer_organizations
            ADD CONSTRAINT
                ck_employer_organizations_organization_type
            CHECK (
                organization_type IN (
                    'company',
                    'university_lab',
                    'research_center'
                )
            );
    END IF;
END
$$;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname =
            'ck_employer_organizations_verification_method'
    ) THEN
        ALTER TABLE public.employer_organizations
            ADD CONSTRAINT
                ck_employer_organizations_verification_method
            CHECK (
                verification_method IS NULL
                OR verification_method IN (
                    'standard_company',
                    'manual_admin'
                )
            );
    END IF;
END
$$;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname =
            'ck_employer_organizations_verification_method_status'
    ) THEN
        ALTER TABLE public.employer_organizations
            ADD CONSTRAINT
                ck_employer_organizations_verification_method_status
            CHECK (
                (
                    verification_status IN ('verified', 'suspended')
                    AND verification_method IS NOT NULL
                )
                OR
                (
                    verification_status IN (
                        'unverified',
                        'pending',
                        'rejected'
                    )
                    AND verification_method IS NULL
                )
            );
    END IF;
END
$$;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname =
            'ck_employer_organizations_non_company_manual_verification'
    ) THEN
        ALTER TABLE public.employer_organizations
            ADD CONSTRAINT
                ck_employer_organizations_non_company_manual_verification
            CHECK (
                organization_type = 'company'
                OR verification_method IS NULL
                OR verification_method = 'manual_admin'
            );
    END IF;
END
$$;


DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname =
            'ck_employer_verification_events_verification_method'
    ) THEN
        ALTER TABLE public.employer_verification_events
            ADD CONSTRAINT
                ck_employer_verification_events_verification_method
            CHECK (
                verification_method IS NULL
                OR verification_method IN (
                    'standard_company',
                    'manual_admin'
                )
            );
    END IF;
END
$$;


CREATE INDEX IF NOT EXISTS
    idx_employer_organizations_organization_type
ON public.employer_organizations(organization_type);
