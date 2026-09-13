-- Gate 11 follow-up: explicit candidate skill provenance-known state
--
-- Existing rows predate authoritative CV provenance tracking.
-- Preserve them as provenance-unknown until a current accepted CV
-- explicitly establishes their evidence source.

ALTER TABLE public.student_skills
    ADD COLUMN IF NOT EXISTS cv_provenance_known
        BOOLEAN NOT NULL DEFAULT FALSE;
