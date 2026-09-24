# InternMatch AI — Security & Data Isolation Policy

**Documentation checkpoint:** 2026-09-24
**Release source:** `707601d93294c891d53b900d01c644200f27292b`

This document describes implemented security boundaries. It is not a claim of absolute security or external regulatory certification.

## 1. Identity & Authentication

Supabase Auth is the identity provider. Protected API calls use a Bearer access token; the backend validates the token and derives the acting user from authenticated claims.

Core invariants:

- clients do not choose an arbitrary `user_id` to act as
- authentication identity and InternMatch application role are separate concepts
- the canonical InternMatch account is provisioned through authenticated backend flow
- account type is persisted by the backend and protected from ordinary profile edits
- candidate Google auth uses Supabase OAuth/browser flow
- candidate Sign in with Apple uses the iOS Apple authentication integration
- employer signup/sign-in uses email/password; candidate social signup is not an employer signup path

## 2. Authorization Boundaries

Authorization is enforced in FastAPI dependencies and repository ownership checks.

### Candidate

Candidate-owned resources are scoped to the authenticated user/student profile. This covers profile data, saved internships, processing jobs, applications, matches, notification inbox, push devices, and private file access.

### Employer

Employer-only endpoints use the employer-role dependency. Opportunity/applicant actions additionally enforce opportunity ownership so one employer cannot manage another employer's listings or applicants.

A verified employer organization is required before employer opportunity creation. Organization verification alone does not publish the opportunity; listing moderation remains independent.

### Admin

Admin endpoints require backend admin authorization (`ADMIN_USER_IDS` plus authenticated identity). The Next.js Admin Console does not grant authority by itself.

The Admin user directory intentionally reads InternMatch-owned application records and does not expose passwords, provider tokens, raw authentication credentials, raw CV content, or private storage paths in its directory payload.

## 3. Organization Verification vs Compliance Evidence

Organization identity verification and compliance evidence are separate trust domains.

Organization verification status can be `unverified`, `pending`, `verified`, `rejected`, or `suspended`. Employer identity/business fields are normalized and review actions are recorded.

Compliance claims are jurisdiction/scope-specific with states `draft`, `pending`, `approved`, `rejected`, `revoked`, and `expired`. Approval means only that supporting evidence for that recorded claim/jurisdiction/scope was reviewed. It is not legal certification and does not bypass listing moderation.

## 4. Listing Moderation & Feedback Privacy

Employer-created opportunities enter administrative review before they become public.

- `under_review` listings are not public candidate listings.
- Admin approval transitions an eligible listing to `published`.
- Admin request-changes transitions it to `draft` and stores employer-visible feedback.
- The owner can edit the existing listing and resubmit it to `under_review`.
- Successful resubmission clears the previous employer-visible feedback.
- `employer_visible_feedback` is returned only through the owner-specific detail contract; public internship detail does not expose it.

This separates moderation communications from the public catalog surface.

## 5. Secret & Environment Boundaries

### 5.1 Client-safe/public configuration

`EXPO_PUBLIC_*` variables are bundled into the mobile client and are publicly readable. Mobile may contain only public Supabase/API/RevenueCat SDK configuration.

Admin `NEXT_PUBLIC_*` values are likewise public browser configuration and do not grant backend admin authority.

### 5.2 Server-only credentials

Server-only configuration includes, where enabled:

- Supabase service-role key and JWT verification material
- database credentials
- Gemini API key
- RevenueCat project/secret server credentials
- RevenueCat webhook authentication/signing secrets
- Apple Sign in private key and related server revocation credentials
- SMTP credentials

These must never be placed in mobile/Admin public variables or committed with real values.

## 6. Storage Security

### 6.1 Candidate CVs

CV upload is authenticated and validates allowed document format/content boundaries, size, and ownership. Files are stored in private Supabase Storage through trusted backend credentials.

The API keeps the storage object path server-owned. Candidate/recruiter document download paths re-check authorization server-side instead of returning a reusable raw provider URL as authority.

### 6.2 Avatars

`database/supabase_storage_setup.sql` provisions a private `avatars` bucket with allowed image types and a size limit. Avatar upload/deletion/content delivery are mediated by FastAPI using authenticated ownership. Client responses use an InternMatch-owned opaque content URL rather than disclosing the object path.

### 6.3 Employer compliance evidence

Migration `025` provisions `employer-compliance-evidence` as a private PDF bucket. It intentionally has no direct anon/authenticated storage policies; upload/download/delete is mediated by trusted backend employer/admin authorization.

### 6.4 Browser guard for private documents

For browser navigation to inaccessible private avatar/CV/compliance document endpoints, the backend redirects to a generic branded unavailable-document page rather than exposing resource-existence/storage details. The response is non-cacheable and noindex/nofollow; machine/API callers keep their original status behavior.

## 7. Input, Text, and Upload Controls

The backend applies endpoint-specific validation to:

- file type/size and document signatures
- public profile text normalization
- employer organization fields and normalized website/email domains
- compliance jurisdiction/scope syntax and version-based concurrency checks
- listing/application lifecycle transitions
- Expo push token shape
- AI request idempotency and quotas where applicable

Rate limiting is applied to source-verified high-cost/abuse-sensitive operations such as CV processing and compliance evidence upload. Rate limits are distinct from product AI quotas.

## 8. AI Security & Authority

Generative AI does not control the core authorization or numeric match score.

- Candidate identity is resolved before AI processing.
- Matching score is deterministic application logic; LLM explanation is downstream text.
- CV processing writes through controlled repositories rather than trusting arbitrary model-produced identifiers.
- Product AI usage is reserved/settled through backend quota logic.
- Idempotency keys/fingerprints prevent reuse of one request identity for incompatible input.
- Failures are handled without transferring authorization decisions to generated text.

Model/API credentials remain server-side.

## 9. Matching Integrity

The hybrid score is computed from exact/fuzzy skill matching, semantic vector similarity, and supported preferences. Numeric score persistence is deterministic and independent of generated prose.

Employer-facing score/ranking logic fails closed while an authoritative match recalculation is actively queued or processing, avoiding presentation of a previously persisted score as fresh.

## 10. RevenueCat & Payment Isolation

### 10.1 Mobile boundary

The mobile app uses RevenueCat public SDK keys only. Store package price/product metadata is dynamically resolved. Local flags are not server authority.

Student and Employer canonical entitlements are `pro_student` and `pro_employer`.

### 10.2 Backend subscription authority

The backend persists subscription state and exposes authenticated state/reconciliation endpoints. RevenueCat reconciliation uses server-only credentials; mobile cannot submit a server secret.

Relevant endpoints:

- `GET /api/v1/me/subscription`
- `POST /api/v1/me/subscription/reconcile`
- `POST /api/v1/webhooks/revenuecat`

### 10.3 Webhook authentication

RevenueCat webhook ingress verifies the configured Bearer authentication token. If `REVENUECAT_WEBHOOK_SIGNING_SECRET` is configured, signature/timestamp HMAC verification additionally applies. Event processing is designed to be idempotent so repeated provider delivery does not create duplicate state transitions.

Do not describe HMAC as unconditional when no signing secret is configured.

## 11. Product Quotas vs Abuse Controls

AI usage limits are product policy. HTTP/operation rate limits are abuse/operational controls. They should not be conflated.

Backend quota state, including Student AI usage and Employer product policy, is authoritative. Client-visible counters/status are snapshots of server state, not a bypass mechanism.

## 12. Account Deletion Safety

Permanent account deletion is a destructive operation and requires a recent authenticated session check. Apple-linked accounts additionally require the Apple revocation boundary when necessary.

Deletion orchestration cleans owned candidate data/private files and associated product state. Where employer listings must remain for historical candidate application integrity, ownership/publication handling is performed explicitly rather than silently destroying unrelated historical records. A RevenueCat deletion barrier prevents unsafe partial completion when subscription-provider cleanup cannot be completed safely.

After server deletion, the mobile client clears its local Supabase session.

## 13. Database and RLS

Migrations define relational constraints, Supabase `auth.users` foreign keys, RLS policies, and later trust/subscription/notification tables. Backend service-role operations are trusted-server operations; that power must remain isolated from public clients.

The full schema depends on Supabase-managed Auth/Storage. A plain Docker PostgreSQL instance does not by itself reproduce those security schemas.

## 14. API Security Headers & Production Surface

FastAPI adds:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- restrictive `Permissions-Policy`
- HSTS in production
- request correlation IDs for observability

When `ENVIRONMENT=production`:

- `/docs` is disabled
- `/redoc` is disabled
- `/openapi.json` is disabled

Production CORS is driven by the server allow-list configuration.

## 15. Health and Error Isolation

`GET /health` is dependency-independent process liveness. `GET /api/v1/health` checks database, Redis, and RQ worker readiness. Readiness returns HTTP 503 when a required dependency is unavailable, without returning credentials/exception internals.

## 16. Dependency & CI Controls

CI uses deterministic dependency installation where lockfiles exist and runs backend lint/tests, container checks, and mobile/Admin type checks. Containers are tested for non-root runtime. Dependency management should continue to avoid force-upgrade fixes that bypass compatibility review.

## 17. Operational Invariants

1. Never commit real `.env` secrets.
2. Never expose service-role or RevenueCat server credentials to client bundles.
3. Never infer admin authority from the Admin UI alone.
4. Never expose compliance evidence publicly.
5. Never expose employer review feedback through public internship responses.
6. Never treat mobile subscription state as the only server authority.
7. Never bypass listing moderation because an organization is verified.
8. Never use production as a test environment.
9. Never blindly rerun migrations against an existing environment.
10. Migration `028_promo_campaigns.sql` is source-only relative to the current production-applied baseline and must not be assumed applied.

## 18. Related Documents

- [Architecture](ARCHITECTURE.md)
- [API Contract](API_CONTRACT.md)
- [Database](DATABASE.md)
- [Deployment](DEPLOYMENT.md)
- [Development](DEVELOPMENT.md)
