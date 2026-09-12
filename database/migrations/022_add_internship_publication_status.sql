-- Migration 022: authoritative internship publication lifecycle
--
-- publication_status is the source of truth for candidate/public visibility.
-- is_active remains only as a legacy compatibility mirror and is derived
-- from publication_status at the database boundary.

BEGIN;

ALTER TABLE public.internship_listings
    ADD COLUMN IF NOT EXISTS publication_status TEXT;

-- Preserve the meaning of all existing rows.
UPDATE public.internship_listings
SET publication_status = CASE
    WHEN is_active THEN 'published'
    ELSE 'closed'
END
WHERE publication_status IS NULL;

ALTER TABLE public.internship_listings
    ALTER COLUMN publication_status SET DEFAULT 'draft';

ALTER TABLE public.internship_listings
    ALTER COLUMN publication_status SET NOT NULL;

-- New rows fail closed unless a trusted server write explicitly publishes.
ALTER TABLE public.internship_listings
    ALTER COLUMN is_active SET DEFAULT false;

DO $$
BEGIN
    ALTER TABLE public.internship_listings
        ADD CONSTRAINT ck_internship_listings_publication_status
        CHECK (
            publication_status IN (
                'draft',
                'under_review',
                'published',
                'closed'
            )
        );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE INDEX IF NOT EXISTS
    idx_internship_listings_publication_status
ON public.internship_listings (publication_status);

-- Normalize the legacy mirror before enabling enforcement.
UPDATE public.internship_listings
SET is_active = (publication_status = 'published')
WHERE is_active IS DISTINCT FROM
    (publication_status = 'published');

-- publication_status is authoritative. Any INSERT or legacy direct UPDATE
-- of is_active is normalized back to the lifecycle state.
CREATE OR REPLACE FUNCTION
    public.sync_internship_listing_publication_active()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.is_active := (NEW.publication_status = 'published');
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS
    trg_internship_listing_publication_active
ON public.internship_listings;

CREATE TRIGGER trg_internship_listing_publication_active
BEFORE INSERT OR UPDATE OF publication_status, is_active
ON public.internship_listings
FOR EACH ROW
EXECUTE FUNCTION
    public.sync_internship_listing_publication_active();

COMMIT;
