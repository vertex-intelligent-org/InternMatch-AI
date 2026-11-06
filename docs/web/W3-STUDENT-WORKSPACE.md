# W3 — Student workspace A

Source: local audit `InternMatch-Web-W3-Source-20261104-133831.zip`, HEAD `4ad7dc023ac09866b7b09e85c4f3d4ec8948d28b`. This is a web-only package. No mobile/backend/landing source, production configuration, database or real account is changed.

## Delivered

- `/app/student`: student home with actual saved/application/draft counts and recent records. No invented profile score, matching score or activity metrics.
- `/app/student/opportunities`: paginated catalog, location/skill/work-type filters, URL state and clear/reset.
- `/app/student/opportunities/:id`: public listing details behind the web account gate; skills, language, education, experience and bookmark action.
- `/app/student/saved`: saved opportunities, pagination and explicit remove action. Closed saved listings can still be removed.
- `/app/student/applications`: existing application tracker with status filtering.
- `/app/student/applications/:id`: application details, interview information and timeline. Saved drafts permit cover-letter/notes review followed by an explicit confirmation dialog and submission.
- `/app/account`: preserved W2 account screen, now with a student workspace link. Mobile users can reach it from the header.

New application creation remains the matching flow. The backend exposes `applications/generate` with a match ID, not a catalog-to-application create endpoint. W3-A does not invent such an endpoint. Users can prepare a new application in mobile matching and review/submit its existing draft on web. Web CV upload/matching/new draft generation is W3-B. Employer workflows, notifications, settings and live landing routing remain later packages. Existing W1 review routes remain separate.

## Data boundary

Every `/app/api/student/*` request revalidates the Supabase identity through existing W2 `getUser`, then reads the canonical profile from FastAPI. Only an `intern` canonical role can use student endpoints. No owner/user ID is accepted from the browser. No service-role key, browser auth client, direct Supabase table access, migration or new dependency.

The BFF permits only:

| Browser BFF | FastAPI contract |
| --- | --- |
| GET internships | GET /api/v1/internships with limit/offset/work_type/location/skill |
| GET internships/:id | GET /api/v1/internships/:id |
| GET saved | GET /api/v1/saved-internships with limit/offset |
| POST/DELETE saved/:id | POST/DELETE /api/v1/saved-internships/:id |
| GET applications | GET /api/v1/applications |
| GET applications/:id | GET /api/v1/applications/:id |
| POST applications/:id/submit | GET owned draft, then POST /api/v1/applications/:id/submit |

IDs are UUIDs; paths, fields and query parameters are allowlisted. Catalog responses must contain published active listings. GET details of non-public listings fail closed. Upstream payloads are validated before display. Backend enforces candidate ownership and checks publication state again atomically when submitting. W3 does not expose employer status changes or draft deletion.

Mutation requests require the configured Origin and reject cross-site Fetch Metadata. Submit JSON is streamed with a byte limit, bounded fields and no owner/status input. Double submission is guarded in the UI and current draft status is re-read before posting. There is no automatic mutation retry. A transport/5xx/invalid-response failure after a possible write is marked uncertain; the UI requires a current-status check before another attempt. Backend status transitions remain authoritative; no distributed exactly-once claim is made. All auth/data responses use private/no-store and existing W2 HttpOnly cookies. Descriptions, letters and meeting details render as plain text, not HTML.

## UI and localization

Local Bricolage Grotesque/Cairo fonts and W1.2 landing-inspired light canvas remain. Desktop has an opaque blue sidebar; mobile has an opaque theme-blue bottom bar. Inactive icons remain readable and the active tab has a separate blue surface. No liquid glass layer is introduced. Cards, form fields, status badges and dialogs use semantic light/dark tokens. Existing Reveal/BrandedWait animations are reused and respect reduced motion. Arabic RTL uses logical spacing; EN/TR/AR dictionaries have equal keys and strict UTF-8.

Loading, error, retry, empty, missing/closed record and ambiguous write results are explicit. Filter pagination resets on applying a new filter. Requests abort on navigation so late responses cannot overwrite another page. Draft edits are saved on submission; the UI says so. There is no fake autosave.

## Local sample preview

The audit says `apps/web/.env.local` was absent. Live connectivity and provider redirects are not verified by this package. No credentials are requested in chat or bundled here.

After a successful installer run:

```powershell
Set-Location -LiteralPath 'C:\InternMatch AI\apps\web'
npm.cmd run preview:student
```

Open `http://127.0.0.1:3111/app/sign-in` and use only these fake fixture credentials:

- Email: `student@example.test`
- Password: `valid-password`

This starts a loopback fake backend/auth service on 4412 and a Next production preview on 3111. The child process overrides connection variables with loopback fixtures, not production. A visible localized banner labels every student page as local sample data. Sample edits disappear on restart. Stop with Ctrl+C. No real mail, user, application or database row is created. Do not expose these fixture ports publicly. Normal `npm run dev` on 3100 continues using the real local configuration when it has been configured separately.

## Verification

- 12 unit/encoding/policy checks.
- Existing 104 W1/W2 UI checks.
- 98 isolated auth + student integration/accessibility cases: existing 30 auth cases, plus catalog filtering and pagination, save/remove, ownership and role denial, CSRF, explicit submission, uncertain response, closed listing, separate users, empty/error/loading states, all student pages in three languages and both themes, narrow mobile and desktop layouts.
- ESLint zero warnings, TypeScript and optimized Next build.
- Real sample-preview start/sign-in/banner and visual inspection of mobile Arabic dark, student home, catalog and draft.

Tests use real Next route handlers and the Supabase SDK against controlled loopback services. They are not live backend, email, OAuth or production database certification. No full backend pytest suite is rerun because backend source is unchanged. Windows launcher is written for PowerShell 5.1; local execution verification here uses Linux/Node 24 and Chromium 140. User's Node 22.20 remains supported.

Installer: all included source baseline and payload hashes are validated before writing, updates are backed up, new files cannot overwrite existing files, and existing tracked state stays unchanged. Generated next-env.d.ts/.next are intentionally not baseline source contracts. Do not reapply after success or a partial write; use the printed report and backup for recovery.
