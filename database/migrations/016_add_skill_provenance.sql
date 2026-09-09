-- Gate 11B/11D: Candidate skill provenance and ranking integrity
--
-- Historical StudentSkill rows predate provenance tracking. We deliberately
-- do NOT fabricate CV evidence for them.
--
-- When cv_provenance_known is first added with DEFAULT FALSE, existing rows
-- become legacy-unknown. After that, the database default is changed to TRUE
-- so future rows cannot silently become legacy-unknown.
--
-- IMPORTANT: there is intentionally NO blanket UPDATE here. Re-running this
-- migration must never overwrite provenance established after deployment.

ALTER TABLE public.student_skills
    ADD COLUMN IF NOT EXISTS cv_evidenced BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS self_declared BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS cv_provenance_known BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE public.student_skills
    ALTER COLUMN cv_provenance_known SET DEFAULT TRUE;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_student_skills_has_source'
          AND conrelid = 'public.student_skills'::regclass
    ) THEN
        ALTER TABLE public.student_skills
            ADD CONSTRAINT ck_student_skills_has_source
            CHECK (cv_evidenced OR self_declared);
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_student_skills_cv_evidence_is_known'
          AND conrelid = 'public.student_skills'::regclass
    ) THEN
        ALTER TABLE public.student_skills
            ADD CONSTRAINT ck_student_skills_cv_evidence_is_known
            CHECK (NOT cv_evidenced OR cv_provenance_known);
    END IF;
END
$$;
