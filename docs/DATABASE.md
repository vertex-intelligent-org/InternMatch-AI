# InternMatch AI — Database Schema & Data Security

**Documentation checkpoint:** 2026-09-24
**Release source:** `707601d93294c891d53b900d01c644200f27292b`

## 1. Database Boundary

The production-oriented schema targets **Supabase PostgreSQL** with `pgvector`, Supabase Auth, and Supabase Storage. Migration `001` references `auth.users`, so a plain PostgreSQL database is not a complete replacement for the full platform.

The repository also provides a local `pgvector` PostgreSQL container for isolated development/testing scenarios. For faithful full-stack development, use a development Supabase project.

## 2. Migration State

Repository migration source spans `001` through `028`.

**Current release execution baseline:** through `027`.

- `027` provides notification/push-device infrastructure.
- `028_promo_campaigns.sql` exists in source but is **not part of the current production-applied baseline**.
- Do not instruct production/current release environments to run `028`.
- Existing environments must track their own applied migrations and must not blindly replay the chain.
- A fresh development Supabase database should apply the required migration chain once in numeric order through `027`.

## 3. Core Candidate Domain

### `student_profiles`

Canonical InternMatch application profile keyed to Supabase `auth.users`. It stores identity-adjacent profile data such as name/headline, preferences, candidate embedding, CV/avatar storage metadata, and timestamps. The application account type is persisted in backend-controlled profile preferences and protected from ordinary role mutation.

### Skills

`skills` is the normalized skill taxonomy; `student_skills` links candidates to skills and carries proficiency/provenance-related state introduced by later migrations.

### Structured candidate history

- `education_entries`
- `experience_entries`
- `project_entries`

These records feed the structured profile and deterministic candidate embedding context.

## 4. Internship Listings

`internship_listings` is the shared opportunity table for controlled/admin-curated and employer-owned listings.

Important domains added across migrations include:

- employer ownership (`employer_user_id`, organization linkage)
- publication lifecycle (`draft`, `under_review`, `published`, `closed`)
- listing provenance/source
- description embeddings (`vector(1536)` in the current configuration)
- requirements/skills/language/education/experience fields
- metadata for internal source/review context

Employer moderation feedback is stored in internal listing metadata and exposed only through the owner-specific API contract. Public catalog schemas do not include `employer_visible_feedback`.

### Publication semantics

Candidate-visible catalog queries select published/active opportunities according to repository policy. `under_review` and requested-change `draft` listings are not public.

## 5. Matches

`matches` persists the hybrid matching result between a student profile and internship listing.

Core fields include:

- `overall_score`
- `skill_score`
- `vector_score`
- `attribute_score`
- generated `why_you_match`
- canonical `skill_gap_analysis` JSON

Uniqueness is enforced per `(student_id, internship_id)`.

The authoritative score is deterministic application logic. Generated explanation text is downstream of that score.

### Matching index

The internship description embedding uses a pgvector cosine index (HNSW in the initial schema). Supporting B-tree indexes cover common student/status/ownership access paths.

## 6. Applications & Lifecycle History

`applications` tracks candidate opportunity state:

```text
saved | applied | interviewing | rejected | accepted
```

Later migrations add `applied_date`, interview metadata, recruiter-controlled fields, and lifecycle support.

`application_status_events` preserves chronological transitions for the tracker/audit timeline.

Historical retention is intentional: candidate application history can outlive active ownership/publication details where foreign-key delete rules use `SET NULL`/detachment instead of cascading away the record.

## 7. Saved Internships

`saved_internships` stores candidate bookmarks, scoped to student and internship uniqueness. Save/unsave operations are idempotent at the API level.

## 8. Processing Jobs

`processing_jobs` persists async RQ work such as CV extraction, match calculation, and application generation. Later migration adds progress tracking.

Ownership is tied to the authenticated user. Jobs have durable status and result/error metadata; active match jobs are also used to prevent employer-facing stale-match presentation.

## 9. Subscription State

Later migrations add backend-authoritative subscription state for Student and Employer entitlements.

The backend persists provider-derived status rather than trusting a client-side flag. RevenueCat reconciliation and webhook handling update this state.

Canonical entitlements:

- `pro_student`
- `pro_employer`

Subscription snapshots can include provider/store/environment/product/renewal/expiry/event metadata as defined by the current backend model/service contract.

## 10. AI Quota & Usage Domain

AI product policy is persisted server-side. The schema supports quota periods/operations/usage events needed for:

- feature limits
- used/remaining counts
- period reset windows
- idempotent operation reservation/settlement
- employer/student feature policy

Product quota exhaustion is a billing/product-policy condition and is distinct from abuse rate limiting.

## 11. Employer Organization Verification

Employer organization tables persist:

- owner user ID
- legal/display name
- website / normalized domain
- business email
- country
- optional registration/tax numbers
- representative name/role
- organization type
- verification method/status
- submission/review timestamps
- rejection reason

A separate verification event table records lifecycle actions, reviewer context, previous/new state, reasons, and internal notes.

Organization verification is not opportunity publication authority.

## 12. Internship Provenance

Later migrations attach source/provenance context to listings so the platform can distinguish employer-owned opportunities from controlled/admin-curated opportunities and enforce recruiter ownership boundaries.

Admin recruiter operations on applicant records are restricted to admin-managed opportunities; employer recruiter operations are restricted to employer-owned opportunities.

## 13. Employer Compliance Claims & Evidence

Migration `024` adds jurisdiction-scoped employer compliance claims, supporting evidence metadata, and compliance event history.

Claim states:

```text
draft | pending | approved | rejected | revoked | expired
```

Claim types currently include:

- insurance arrangement
- completion certificate
- university agreement
- legal internship eligibility

Each claim records jurisdiction, scope, optional validity dates, version, submission/review state, and rejection reason. Optimistic version checks protect concurrent mutations.

Compliance review is independent from organization identity verification.

### Private evidence storage

Migration `025` provisions the private `employer-compliance-evidence` bucket for PDFs. There are intentionally no direct anon/authenticated storage policies; the backend uses trusted credentials after employer/Admin authorization.

## 14. Notifications & Push Devices

Migration `027` establishes durable notification state and Expo push-device registration data.

The API uses this domain for:

- user inbox
- unread count/read state
- event/entity metadata
- deduplication where applicable
- push token/platform/locale registration
- disable/logout behavior
- notification preferences such as new-opportunity alerts

Push delivery is supplemental to persisted notification records.

## 15. Promo Migration Boundary

Migration `028_promo_campaigns.sql` exists in repository source and backend/Admin promo code source also exists. It is outside the current production-applied release baseline and should not be represented as active current production schema/mobile functionality.

The current mobile custom promo UI that directly unlocked Pro has been removed.

## 16. Row Level Security & Trusted Backend Access

Early migrations establish RLS for candidate-owned/public domains. The trusted FastAPI backend also uses the Supabase service-role boundary for controlled operations such as private storage access and authoritative writes.

Security model:

- candidate-owned data: JWT identity + backend ownership checks + RLS where applicable
- public internship data: read-only published catalog contract
- employer domains: employer role + ownership + organization state
- Admin domains: authenticated Admin allow-list
- private storage: backend-mediated, not direct public access

Service-role credentials must never appear in mobile/Admin public configuration.

## 17. Referential Integrity

Foreign keys are chosen according to data ownership and historical retention. Examples include:

- candidate profile -> `auth.users` lifecycle
- student-owned structured records -> candidate profile lifecycle
- applications -> student cascade, internship historical retention behavior
- employer organization -> owner identity
- compliance/evidence -> organization/claim lifecycle
- notification/device records -> authenticated user lifecycle

When account deletion must preserve other users' historical application records, service-level orchestration explicitly detaches/closes employer-owned listing state instead of indiscriminately deleting shared history.

## 18. Vector & Search Policy

`pgvector` is required. Initial schema creates vector support and the internship embedding index. Candidate embeddings and internship description embeddings use the configured server embedding dimension (`1536` in current template).

The vector score is only one component of the hybrid match; skills and supported preferences contribute independently.

## 19. Storage Configuration

| Purpose | Configuration / provisioning | Visibility |
|---|---|---|
| CV | `CV_STORAGE_BUCKET` (template `cvs`); provision separately | Private |
| Avatar | `database/supabase_storage_setup.sql` -> `avatars` | Private |
| Compliance evidence | migration `025` -> `employer-compliance-evidence` | Private |

Object paths are server-managed and are not client authorization tokens.

## 20. Development/Production Rules

1. Never use production as a migration sandbox.
2. Never blindly rerun a migration already applied.
3. Never run migration `028` as part of the current release baseline.
4. For faithful fresh development, use Supabase PostgreSQL/Auth/Storage and apply through `027` once.
5. Keep service-role/database credentials server-only.
6. Preserve publication/ownership/privacy constraints when adding schema fields.

## 21. Related Documents

- [Architecture](ARCHITECTURE.md)
- [Security](SECURITY.md)
- [API Contract](API_CONTRACT.md)
- [Deployment](DEPLOYMENT.md)
