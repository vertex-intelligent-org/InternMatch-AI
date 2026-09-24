# InternMatch AI — REST API Contract (v1)

**Documentation checkpoint:** 2026-09-24
**Release source:** `707601d93294c891d53b900d01c644200f27292b`
**Production base:** `https://api.internmatch.college/api/v1`
**Local development base:** `http://localhost:8000/api/v1`

This document describes the current FastAPI v1 surface. Endpoint authority comes from the mounted routers in `backend/app/api/v1/router.py` and their endpoint modules. Production intentionally disables Swagger/ReDoc/OpenAPI, so this document is the human-readable contract for release review.

## 1. General Conventions

### 1.1 Authentication

Protected endpoints expect:

```http
Authorization: Bearer <Supabase access token>
```

The backend derives user identity from the validated token. Employer/Admin authorization is an additional server-side role/allow-list check, not a client flag.

### 1.2 Content Types

- JSON for ordinary request/response payloads.
- `multipart/form-data` for CV/avatar/compliance-evidence upload endpoints.
- Private document content endpoints stream the underlying file through authenticated server boundaries.

### 1.3 Error Shapes

The API does not guarantee one universal error envelope. Endpoint-specific handlers may return a structured `error` object, while ordinary FastAPI `HTTPException` responses use `detail`. Pydantic validation errors return HTTP 422.

Clients should branch on HTTP status and the endpoint's documented response, not assume every error has an identical body.

### 1.4 Localization

The mobile UI is localized client-side for `en`, `tr`, and `ar`. Selected generated-content endpoints accept an explicit supported content locale. The API does not use one global `Accept-Language` contract for every response.

## 2. Health

| Method | Path | Access | Behavior |
|---|---|---|---|
| `GET` | `/health` | Public | Root process liveness; dependency-independent |
| `GET` | `/api/v1/health` | Public | Readiness for PostgreSQL, Redis, and RQ worker; HTTP 200 ready, HTTP 503 otherwise |

Do not use `/openapi.json` as a production health check; production disables OpenAPI.

## 3. Authentication & Canonical Account

Prefix: `/api/v1/auth`

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/auth/sync` | Authenticated | Returns authenticated identity and whether the InternMatch profile exists |
| `POST` | `/auth/complete-signup` | Authenticated | Creates the canonical InternMatch account once with role `intern` or `employer` |
| `DELETE` | `/auth/account` | Recently reauthenticated user | Permanently deletes the authenticated account through guarded deletion orchestration |

`complete-signup` persists the application role server-side; provider metadata is not treated as the role authority.

`DELETE /auth/account` requires recent reauthentication. Apple-linked deletion may additionally require `X-Apple-Authorization-Code` so server-side Apple authorization can be revoked safely.

## 4. Student Profile, CV, and Avatar

Prefix: `/api/v1/profile`

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/profile` | Authenticated | Read own structured profile |
| `PUT` | `/profile` | Authenticated | Update allowed profile fields; account role remains server-owned |
| `POST` | `/profile/cv` | Authenticated | Upload PDF/DOCX CV, persist private file, enqueue background extraction; HTTP 202 |
| `POST` | `/profile/cv/{job_id}/cancel` | Authenticated owner | Persist a cancellation request for an active CV-analysis job |
| `POST` | `/profile/cv/confirm` | Authenticated owner | Confirm and apply a pending CV profile replacement when the extraction flow requires confirmation |
| `POST` | `/profile/avatar` | Authenticated | Upload validated private profile avatar |
| `DELETE` | `/profile/avatar` | Authenticated | Delete own avatar |
| `GET` | `/profile/avatar/content` | Authenticated/owner | Stream own avatar through product-owned endpoint |

CV processing includes rate limiting, file validation, durable job tracking, and idempotency/quota integration. Storage metadata such as `cv_storage_path` is server-managed and rejected as a client-owned profile field.

The profile response includes structured skills, education, experience, projects, preferences, CV presence, and an opaque avatar content URL when present.

## 5. Internship Catalog & Employer-Owned Opportunities

Prefix: `/api/v1/internships`

### 5.1 Public catalog

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/internships` | Public | Candidate-visible published catalog; backend supports work-type/location/skill filters plus pagination |
| `GET` | `/internships/{id}` | Public | Candidate-visible detail; non-public listings are not exposed |

The current mobile catalog UI primarily exposes work-type filters even though the backend catalog contract supports additional query filters.

Public responses never expose owner-only moderation feedback.

### 5.2 Employer ownership

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/internships` | Employer | Create employer-owned opportunity; requires verified organization and listing capacity; enters moderation workflow |
| `GET` | `/internships/mine` | Employer | List own opportunities across owner-visible states |
| `GET` | `/internships/mine/{id}` | Employer owner | Read owner detail, including employer-visible review feedback when present |
| `PATCH` | `/internships/{id}` | Employer owner | Edit eligible owned listing; resubmission returns requested-change drafts to `under_review` |
| `DELETE` | `/internships/{id}` | Employer owner | Permanently delete an owned opportunity only when no candidate application exists |
| `POST` | `/internships/{id}/close` | Employer owner | Close eligible owned listing while preserving application history |

Create/update behavior is moderated. Organization verification is required for employer publishing eligibility, but verification does not itself make a listing public.

### 5.3 Employer applicants & interviews

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/internships/{id}/applicants` | Employer owner | List applicants for owned opportunity |
| `GET` | `/internships/{id}/applicants/{application_id}` | Employer owner | Read applicant detail |
| `GET` | `/internships/{id}/applicants/{application_id}/cv/content` | Employer owner | Stream authorized applicant CV without exposing provider path |
| `PATCH` | `/internships/{id}/applicants/{application_id}/status` | Employer owner | Apply valid employer-controlled status transition |
| `POST` | `/internships/{id}/applicants/{application_id}/interview` | Employer owner | Schedule/update interview workflow |
| `POST` | `/internships/{id}/applicants/{application_id}/insight` | Employer owner | Generate grounded candidate insight; separately quota-controlled and available under the Employer product policy |
| `POST` | `/internships/{id}/applicants/{application_id}/interview-kit` | Employer Pro owner | Generate a grounded interview kit; `Idempotency-Key` required for Employer AI execution |
| `POST` | `/internships/{id}/shortlist-comparison` | Employer Pro owner | Compare 2–5 owned applicants without producing an autonomous hiring decision; `Idempotency-Key` required |

Server ownership checks prevent cross-employer applicant access. Employer AI operations also enforce durable product-unit quotas.

### 5.4 Employer product tools

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/internships/employer-tools/description-assistant` | Employer Pro | Generate an editable internship-description draft only; does not publish or mutate a listing; `Idempotency-Key` required |
| `GET` | `/internships/employer-tools/product-policy` | Employer | Return backend-authoritative Employer Free/Pro capabilities |
| `GET` | `/internships/employer-tools/pipeline-analytics` | Employer Pro | Return current tenant-scoped hiring-pipeline analytics |

Employer Free supports one published internship and candidate insight, with AI usage quotas enforced separately. Employer Pro removes the one-listing cap and enables interview kit, shortlist comparison, description assistant, and pipeline analytics.

## 6. Saved Internships

Prefix: `/api/v1/saved-internships`

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/saved-internships` | Authenticated candidate | List own saved opportunities |
| `POST` | `/saved-internships/{internship_id}` | Authenticated candidate | Save/bookmark; idempotent |
| `DELETE` | `/saved-internships/{internship_id}` | Authenticated candidate | Remove bookmark; idempotent |

Saved state is tenant-scoped to the authenticated user.

## 7. Matching

Prefix: `/api/v1/matches`

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/matches` | Authenticated candidate | Return persisted matches for current candidate |
| `POST` | `/matches/calculate` | Authenticated candidate | Enqueue/trigger authoritative match recalculation |
| `POST` | `/matches/{id}/explanation` | Authenticated candidate | Enqueue cancellable grounded Why You Match explanation generation for an owned match; HTTP 202 |

The explanation endpoint is `POST` in the current source. Numeric match scores are deterministic application data; generated explanation text does not set the authoritative score.

## 8. Applications

Prefix: `/api/v1/applications`

Application states:

```text
saved | applied | interviewing | accepted | rejected
```

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/applications` | Authenticated candidate | List own tracked applications |
| `GET` | `/applications/{id}` | Authenticated candidate | Read own application detail/timeline/interview data |
| `POST` | `/applications/generate` | Authenticated candidate | Enqueue AI-assisted application/cover-letter generation |
| `POST` | `/applications/{id}/submit` | Authenticated candidate | Submit eligible saved application |
| `PATCH` | `/applications/{id}/status` | Authenticated candidate | Candidate-managed tracker transition subject to lifecycle rules |
| `POST` | `/applications/{id}/interview-prep` | Authenticated candidate | Enqueue cancellable interview-preparation generation for an eligible interviewing application; HTTP 202 |
| `DELETE` | `/applications/{id}` | Authenticated candidate | Discard eligible saved draft according to backend state rules |

Employer-controlled transitions such as `interviewing`, `accepted`, and `rejected` are enforced through recruiter-owned applicant endpoints rather than trusting candidate input.

## 9. Processing Jobs

Prefix: `/api/v1/jobs`

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/jobs/{job_id}` | Authenticated owner | Poll durable async job state |
| `POST` | `/jobs/{job_id}/cancel` | Authenticated owner | Cancel eligible processing job through server rules |

Job lookup is scoped by both job ID and authenticated owner.

## 10. Subscription & AI Usage

Prefix: `/api/v1/me`

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/me/subscription` | Authenticated | Return backend-authoritative student/employer subscription snapshot |
| `GET` | `/me/ai-usage` | Authenticated | Return backend-controlled AI quota/remaining usage snapshot |
| `POST` | `/me/subscription/reconcile` | Authenticated | Refresh subscription from RevenueCat server API |

The backend selects student vs employer subscription reconciliation from the persisted account role.

Canonical entitlements:

- Student: `pro_student`
- Employer: `pro_employer`

## 11. RevenueCat Webhook

Prefix: `/api/v1/webhooks`

| Method | Path | Access | Purpose |
|---|---|---|---|
| `POST` | `/webhooks/revenuecat` | Provider-authenticated | Process RevenueCat lifecycle events into authoritative subscription state |

Configured Bearer webhook authentication is required. When `REVENUECAT_WEBHOOK_SIGNING_SECRET` is configured, HMAC signature and timestamp verification additionally apply. Event handling is idempotent.

## 12. Notifications & Push Devices

Prefix: `/api/v1/notifications`

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/notifications` | Authenticated | Paginated durable inbox + unread count |
| `GET` | `/notifications/unread-count` | Authenticated | Current unread count |
| `GET` | `/notifications/preferences/opportunity-alerts` | Authenticated | Read opportunity-alert preference |
| `PUT` | `/notifications/preferences/opportunity-alerts` | Authenticated | Update opportunity-alert preference |
| `POST` | `/notifications/{notification_id}/read` | Authenticated owner | Mark read |
| `POST` | `/notifications/{notification_id}/unread` | Authenticated owner | Mark unread |
| `POST` | `/notifications/read-all` | Authenticated | Mark all current user's notifications read |
| `POST` | `/notifications/devices` | Authenticated | Register Expo push device/token |
| `DELETE` | `/notifications/devices` | Authenticated | Disable registered push token; idempotent |
| `DELETE` | `/notifications/{notification_id}` | Authenticated owner | Delete own notification |

Expo push tokens are validated server-side before registration. Push delivery supplements persisted notification state.

## 13. Employer Organization Verification

Employer prefix: `/api/v1/employer-organization`

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/employer-organization` | Employer | Read own organization |
| `POST` | `/employer-organization` | Employer | Create organization profile |
| `PUT` | `/employer-organization` | Employer | Edit own organization while state allows |
| `POST` | `/employer-organization/submit` | Employer | Submit unverified/rejected organization for Admin review |

Organization fields include legal/display name, website, business email, country, optional registration/tax numbers, and representative name/role.

Admin prefix: `/api/v1/admin/employer-organizations`

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/admin/employer-organizations` | Admin | List organizations by review status |
| `GET` | `/admin/employer-organizations/{organization_id}` | Admin | Read review detail |
| `POST` | `/admin/employer-organizations/{organization_id}/approve` | Admin | Approve pending organization |
| `POST` | `/admin/employer-organizations/{organization_id}/reject` | Admin | Reject with reason |
| `POST` | `/admin/employer-organizations/{organization_id}/suspend` | Admin | Suspend according to server transition rules |

Verification is distinct from opportunity publication and from compliance review.

## 14. Employer Compliance Claims

Employer prefix: `/api/v1/employer-compliance`

Employer claim operations:

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/employer-compliance/claims` | Employer | List own organization's claims |
| `POST` | `/employer-compliance/claims` | Employer | Create jurisdiction/scope claim in draft |
| `PUT` | `/employer-compliance/claims/{claim_id}` | Employer owner | Edit eligible draft/rejected claim with optimistic version check |
| `POST` | `/employer-compliance/claims/{claim_id}/evidence` | Employer owner | Upload private PDF supporting evidence; `expected_version` query parameter required |
| `GET` | `/employer-compliance/claims/{claim_id}/evidence/{evidence_id}/content` | Employer owner | Stream authorized private evidence without exposing the storage path |
| `POST` | `/employer-compliance/claims/{claim_id}/submit` | Employer owner | Submit eligible claim with evidence for Admin review |

Admin prefix: `/api/v1/admin/employer-compliance`

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/admin/employer-compliance/claims` | Admin | List claims by review status |
| `GET` | `/admin/employer-compliance/claims/{claim_id}` | Admin | Read claim/evidence metadata for review |
| `GET` | `/admin/employer-compliance/claims/{claim_id}/evidence/{evidence_id}/content` | Admin | Stream private evidence through the Admin authorization boundary |
| `POST` | `/admin/employer-compliance/claims/{claim_id}/approve` | Admin | Approve a pending claim with optimistic version check |
| `POST` | `/admin/employer-compliance/claims/{claim_id}/reject` | Admin | Reject a pending claim with reason and optimistic version check |
| `POST` | `/admin/employer-compliance/claims/{claim_id}/revoke` | Admin | Revoke an approved claim with reason and optimistic version check |

These operations enforce claim ownership/Admin authorization, expected-version concurrency, and private storage boundaries. Raw storage paths/private internal notes are not returned in the employer response contract.

Compliance approval is a review decision for a recorded claim/jurisdiction/scope, not legal certification.

## 15. Admin Internship & Applicant Operations

Prefix: `/api/v1/admin/internships`

### Listing/moderation

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/admin/internships` | Admin | List all publication states / moderation queue |
| `POST` | `/admin/internships` | Admin | Create admin-curated opportunity |
| `GET` | `/admin/internships/{id}` | Admin | Read one listing without public-visibility filtering |
| `DELETE` | `/admin/internships/{id}` | Admin | Permanently delete an Admin-managed listing only when no application exists |
| `POST` | `/admin/internships/{id}/close` | Admin | Close an internship listing while preserving history |
| `POST` | `/admin/internships/{id}/reopen` | Admin | Reopen a closed listing; employer-owned reopen rechecks verification and listing capacity |
| `POST` | `/admin/internships/{id}/approve` | Admin | Approve eligible employer listing for publication |
| `POST` | `/admin/internships/{id}/request-changes` | Admin | Return employer listing to editable draft with employer-visible feedback |

Admin request-changes feedback is explicitly owner-visible and is not copied into the public listing response.

### Admin-managed applicant workflow

Admin recruiter operations are restricted to Admin-created/managed listings and do not cross into employer ownership.

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/admin/internships/{id}/applicants` | Admin | List applicants for admin-managed listing |
| `GET` | `/admin/internships/{id}/applicants/{application_id}` | Admin | Applicant detail |
| `GET` | `/admin/internships/{id}/applicants/{application_id}/cv/content` | Admin | Stream authorized candidate CV |
| `PATCH` | `/admin/internships/{id}/applicants/{application_id}/status` | Admin | Valid recruiter transition |
| `POST` | `/admin/internships/{id}/applicants/{application_id}/interview` | Admin | Schedule interview |

## 16. Admin User Directory & Audit

Prefix: `/api/v1/admin/users`

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/admin/users` | Admin | Search/paginate student and employer application records; optional role filter |
| `GET` | `/admin/users/{user_id}` | Admin | User detail plus organization verification/compliance audit events where applicable |

The Admin user payload deliberately excludes authentication credentials, provider tokens, private document paths, and raw CV data.

## 17. Promo Source Boundary

The v1 router contains promo-code source routes under `/promo-codes` and `/admin/promo-codes`. They are **not part of the current production-applied release baseline** because migration `028_promo_campaigns.sql` has not been applied to production and the custom mobile promo Pro-unlock UI has been removed.

Do not use those source routes as evidence of an active production mobile promo flow.

## 18. Publication & Privacy Invariants

- `draft` and `under_review` employer listings are not public catalog items.
- Organization verification does not auto-publish listings.
- `employer_visible_feedback` is owner-only.
- Candidate saved applications are not recruiter-visible submissions.
- Candidate/employer/Admin document access is revalidated at the server boundary.
- Subscription state and AI quotas are backend-authoritative for protected server behavior.

## 19. Related Documents

- [Architecture](ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Database](DATABASE.md)
- [Judge Runbook](JUDGE_RUNBOOK.md)
