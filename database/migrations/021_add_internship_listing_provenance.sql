-- InternMatch AI - Gate 2 A4 Listing Provenance + Organization Binding
-- Target Engine: Supabase PostgreSQL 15+
-- Migration: 021_add_internship_listing_provenance.sql
--
-- Security invariant:
-- NULL employer_user_id is never authority for curated provenance.
-- Unknown historical rows remain legacy_unknown and are not public.

ALTER TABLE public.internship_listings
ADD COLUMN IF NOT EXISTS employer_organization_id UUID
    REFERENCES public.employer_organizations(id)
    ON DELETE SET NULL;

ALTER TABLE public.internship_listings
ADD COLUMN IF NOT EXISTS listing_source TEXT
    NOT NULL
    DEFAULT 'legacy_unknown';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_internship_listings_listing_source'
    ) THEN
        ALTER TABLE public.internship_listings
        ADD CONSTRAINT ck_internship_listings_listing_source
        CHECK (
            listing_source IN (
                'curated',
                'employer',
                'legacy_unknown'
            )
        );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS
idx_internship_listings_employer_organization_id
ON public.internship_listings(employer_organization_id);

CREATE INDEX IF NOT EXISTS
idx_internship_listings_listing_source
ON public.internship_listings(listing_source);

-- Existing explicit employer ownership is sufficient evidence that the
-- row originated from an employer, even if no organization exists now.
UPDATE public.internship_listings
SET listing_source = 'employer'
WHERE employer_user_id IS NOT NULL;

-- Bind historical employer rows to their canonical organization where
-- a current owner -> organization relationship exists.
UPDATE public.internship_listings AS listing
SET
    employer_organization_id = organization.id,
    listing_source = 'employer'
FROM public.employer_organizations AS organization
WHERE
    listing.employer_user_id = organization.owner_user_id;

-- The authoritative synthetic demo dataset is identified ONLY through
-- its controlled deterministic UUID set. No NULL-owner inference.
WITH curated_ids(id) AS (
    VALUES
        ('20000000-0000-0000-0000-000000000001'::uuid),
        ('20000000-0000-0000-0000-000000000002'::uuid),
        ('20000000-0000-0000-0000-000000000003'::uuid),
        ('20000000-0000-0000-0000-000000000004'::uuid),
        ('20000000-0000-0000-0000-000000000005'::uuid),
        ('20000000-0000-0000-0000-000000000006'::uuid),
        ('20000000-0000-0000-0000-000000000007'::uuid),
        ('20000000-0000-0000-0000-000000000008'::uuid),
        ('20000000-0000-0000-0000-000000000009'::uuid),
        ('20000000-0000-0000-0000-000000000010'::uuid),
        ('20000000-0000-0000-0000-000000000011'::uuid),
        ('20000000-0000-0000-0000-000000000012'::uuid),
        ('20000000-0000-0000-0000-000000000013'::uuid),
        ('20000000-0000-0000-0000-000000000014'::uuid),
        ('20000000-0000-0000-0000-000000000015'::uuid),
        ('20000000-0000-0000-0000-000000000016'::uuid),
        ('20000000-0000-0000-0000-000000000017'::uuid),
        ('20000000-0000-0000-0000-000000000018'::uuid),
        ('20000000-0000-0000-0000-000000000019'::uuid),
        ('20000000-0000-0000-0000-000000000020'::uuid),
        ('20000000-0000-0000-0000-000000000021'::uuid),
        ('20000000-0000-0000-0000-000000000022'::uuid),
        ('20000000-0000-0000-0000-000000000023'::uuid),
        ('20000000-0000-0000-0000-000000000024'::uuid),
        ('20000000-0000-0000-0000-000000000025'::uuid),
        ('20000000-0000-0000-0000-000000000026'::uuid),
        ('20000000-0000-0000-0000-000000000027'::uuid),
        ('20000000-0000-0000-0000-000000000028'::uuid),
        ('20000000-0000-0000-0000-000000000029'::uuid),
        ('20000000-0000-0000-0000-000000000030'::uuid),
        ('20000000-0000-0000-0000-000000000031'::uuid),
        ('20000000-0000-0000-0000-000000000032'::uuid),
        ('20000000-0000-0000-0000-000000000033'::uuid),
        ('20000000-0000-0000-0000-000000000034'::uuid),
        ('20000000-0000-0000-0000-000000000035'::uuid)
)
UPDATE public.internship_listings AS listing
SET
    listing_source = 'curated',
    employer_organization_id = NULL
FROM curated_ids
WHERE listing.id = curated_ids.id;
