-- Gate 2 A3: canonicalize company identity for listings owned by
-- organizations already verified when this migration runs.
--
-- Unverified employer-owned listings remain stored but are hidden by the
-- application visibility policy until verification.
-- Curated listings (employer_user_id IS NULL) are intentionally preserved.

UPDATE public.internship_listings AS listing
SET company = organization.display_name
FROM public.employer_organizations AS organization
WHERE listing.employer_user_id = organization.owner_user_id
  AND organization.verification_status = 'verified'
  AND listing.company IS DISTINCT FROM organization.display_name;
