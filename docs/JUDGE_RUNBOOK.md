# InternMatch AI — Judge Reproduction Runbook

**Documentation checkpoint:** 2026-09-24
**Release source:** `707601d93294c891d53b900d01c644200f27292b`
**Canonical repository:** https://github.com/vertex-intelligent-org/InternMatch-AI

> **Audience:** Shipaton judges, technical evaluators, and developers reproducing InternMatch AI on a fresh **development** environment.
>
> This runbook documents technical reproduction. It does **not** treat TestFlight, a Google Play testing track, or RevenueCat Test Store as proof of a public Shipaton Standard Track release. At this checkpoint, iOS `1.0.0` Build 9 is associated with App Review and Build 10 has been uploaded to App Store Connect / TestFlight for validation. Public-store eligibility must be verified separately at final submission time.

---

## 1. What This Runbook Reproduces

InternMatch AI has three connected product surfaces:

1. **Student / Candidate mobile experience** — profile and CV workflows, internship discovery, saved opportunities, hybrid matching, Why You Match explanations, AI-assisted application preparation, interview preparation, application tracking, notifications, localization, and Student Pro subscription-aware behavior.
2. **Employer mobile experience** — organization workspace, organization verification, separate compliance-evidence workflow, moderated opportunity publishing, applicant/interview workflows, Employer product policy, and Employer Pro tools.
3. **Admin Trust & Safety Console** — server-authorized organization review, compliance review, listing moderation, user directory/search, audit context, and Admin-managed opportunity workflows.

The supporting platform uses FastAPI, Supabase Auth/PostgreSQL/Storage, PostgreSQL `pgvector`, Redis, RQ workers, Google Gemini, RevenueCat, Expo/React Native, and a Next.js Admin Console.

---

## 2. Development Prerequisites

The repository's CI reference runtimes are **Python 3.13** and **Node.js 22**. A typical development workstation also needs Git, npm, Docker with Compose support, and Android Studio for a local Android native client.

For local iOS native builds, use macOS with the appropriate Apple/Xcode tooling. Windows should not be treated as a local native iOS build environment.

> Version numbers for Git, Docker, Android SDK, or Xcode are intentionally not presented as mandatory minimums unless enforced by repository configuration.

---

## 3. Clone the Canonical Repository

```bash
git clone https://github.com/vertex-intelligent-org/InternMatch-AI.git
cd InternMatch-AI
git checkout 707601d93294c891d53b900d01c644200f27292b
```

High-level structure:

```text
.
├── apps/
│   ├── admin/              # Next.js Admin Trust & Safety Console
│   ├── landing/            # Product / legal web surface
│   └── mobile/             # Expo / React Native student + employer app
├── backend/                # FastAPI API, authorization, repositories, services
├── database/               # SQL migrations, seeds, storage setup
├── docs/                   # Architecture, API, security, database, runbooks
├── tests/                  # Pytest + source/contract coverage
├── worker/                 # Redis/RQ background jobs
└── docker-compose.yml      # Optional local service orchestration
```

---

## 4. Use a Development Supabase Project

The complete application schema targets **Supabase PostgreSQL** and references Supabase-managed resources such as `auth.users`. The application also depends on Supabase Auth and private Storage.

Therefore, for faithful full-stack reproduction, use a **development Supabase project** for:

- PostgreSQL
- Supabase Auth
- Supabase Storage

The `pgvector` PostgreSQL service in `docker-compose.yml` is useful for isolated development/testing, but it is **not** a complete replacement for Supabase Auth + Storage.

Never point reproduction or test workflows at the production database/project.

---

## 5. Server Environment Configuration

Copy the repository template:

```bash
cp .env.example .env
```

Populate it with **development** credentials. Important groups include:

```ini
ENVIRONMENT=development
PORT=8000
LOG_LEVEL=INFO

SUPABASE_URL=...
SUPABASE_PUBLISHABLE_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWT_SECRET=...
DATABASE_URL=...

CV_STORAGE_BUCKET=cvs
AVATAR_STORAGE_BUCKET=avatars
COMPLIANCE_STORAGE_BUCKET=employer-compliance-evidence

REDIS_URL=redis://redis:6379/0

GEMINI_API_KEY=...
LLM_MODEL_NAME=gemini-3.5-flash
EMBEDDING_MODEL_NAME=gemini-embedding-2
EMBEDDING_DIMENSION=1536
SKILL_FUZZY_THRESHOLD=85

REVENUECAT_PROJECT_ID=...
REVENUECAT_SECRET_KEY=...
REVENUECAT_ENVIRONMENT=sandbox
REVENUECAT_WEBHOOK_AUTH_TOKEN=...
REVENUECAT_WEBHOOK_SIGNING_SECRET=...

ADMIN_USER_IDS=...
ADMIN_BASE_URL=http://localhost:3000

ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000,http://localhost:19006
```

Use the actual `.env.example` as the authoritative list. Do not put server secrets in mobile or Admin public environment variables.

`ADMIN_USER_IDS` is a comma-separated allow-list of Supabase user UUIDs. An Admin UI session does not grant Admin authority by itself; backend authorization remains authoritative.

---

## 6. Database & Private Storage Initialization

Repository migration source spans `001` through `028`.

**Release execution baseline for this checkpoint: through `027`.**

- Apply the required SQL migration chain **once**, in numeric order, through `027` to a fresh development Supabase database.
- Do not blindly replay migrations against an existing environment; track its actual applied state.
- `028_promo_campaigns.sql` exists in source but is **not part of the current production-applied release baseline**. Do not run it as part of this reproduction baseline.
- `database/supabase_storage_setup.sql` provisions the private avatar storage boundary.
- Provision the configured CV bucket (template name `cvs`) privately in the development Supabase project.
- Migration `025` provisions the private `employer-compliance-evidence` bucket.

For schema details and retention rules, use [DATABASE.md](DATABASE.md).

---

## 7. Start Backend, Redis, and Worker

When the server environment points to the development Supabase project, the backend, worker, and Redis services can be started with Docker Compose:

```bash
docker compose up --build -d backend worker redis
```

Check service state:

```bash
docker compose ps
```

Verify process liveness:

```bash
curl http://localhost:8000/health
```

Verify dependency readiness:

```bash
curl http://localhost:8000/api/v1/health
```

Expected readiness behavior:

- HTTP `200` when required database, Redis, and RQ worker dependencies are ready.
- HTTP `503` when a required readiness dependency is unavailable.

In a development environment, FastAPI may expose `/docs`, `/redoc`, and `/openapi.json`. Production intentionally disables all three, so production OpenAPI must not be used as a health check.

---

## 8. Run the Admin Trust & Safety Console

Create Admin client environment from `apps/admin/.env.example`, using the same **development** Supabase project and local API base. Client-side variables configure connectivity only; backend Admin authorization still requires a UUID in `ADMIN_USER_IDS`.

```bash
cd apps/admin
npm ci
npm run dev
```

Default local Next.js development URL is normally `http://localhost:3000`.

Admin workflows worth evaluating:

- organization review (`pending` -> approve/reject; verified organizations can later be suspended)
- employer compliance claim/evidence review as a separate trust domain
- employer listing moderation (approve or request changes)
- Admin user directory/search and audit context
- Admin-managed opportunity/applicant flows

---

## 9. Configure & Run the Mobile App

From the repository root:

```bash
cd apps/mobile
cp .env.example .env
npm ci
```

Configure only public client values:

```ini
EXPO_PUBLIC_SUPABASE_URL=https://<development-project>.supabase.co
EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY=...
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000/api/v1

# Development / RevenueCat Test Store public key
EXPO_PUBLIC_REVENUECAT_API_KEY=...
```

For an Android emulator, `10.0.2.2` reaches the host machine. For a physical device, use a reachable development API address appropriate to the local network.

### Native development client

RevenueCat native functionality is not fully represented by Expo Go. Build/use a native development client:

```bash
npx expo run:android
npx expo start --dev-client
```

On macOS, a local iOS native development client can be built with:

```bash
npx expo run:ios
```

The current mobile stack is Expo SDK 54, React Native 0.81.5, and `react-native-purchases` 10.7.2.

---

## 10. RevenueCat: Development vs Release

InternMatch AI implements separate Student and Employer subscription contracts:

| Audience | Entitlement | Offering | Package | Canonical Product |
|---|---|---|---|---|
| Student | `pro_student` | `default` | `$rc_monthly` | `internmatch_pro_student_monthly` |
| Employer | `pro_employer` | `employer_default` | `$rc_monthly` | `internmatch_pro_employer_monthly` |

Development may use `EXPO_PUBLIC_REVENUECAT_API_KEY` with RevenueCat Test Store. Production builds use the platform-specific public keys `EXPO_PUBLIC_REVENUECAT_IOS_API_KEY` and `EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY`.

The backend is also part of the subscription authority:

- `GET /api/v1/me/subscription`
- `GET /api/v1/me/ai-usage`
- `POST /api/v1/me/subscription/reconcile`
- `POST /api/v1/webhooks/revenuecat`

`REVENUECAT_SECRET_KEY` is server-only. Webhooks require configured Bearer authentication; HMAC signature/timestamp validation additionally applies when `REVENUECAT_WEBHOOK_SIGNING_SECRET` is configured.

> **Shipaton release note:** RevenueCat Test Store is useful for development reproduction, but the official 2026 main-competition submission requirements call for a qualifying public store release and a working RevenueCat-powered purchase (or qualifying RevenueCat Ads path). TestFlight/testing-track availability alone does not satisfy that release requirement. See RevenueCat's current submission guide: https://www.revenuecat.com/blog/engineering/how-to-submit-your-app-for-shipaton

The current mobile custom promo-code field that directly unlocked Pro was removed. Do not look for or depend on an InternMatch-specific in-app promo unlock flow.

---

## 11. End-to-End Evaluation Paths

### 11.1 Student / Candidate

1. Create a candidate account with email/password, Google OAuth, or Sign in with Apple on iOS as supported by the target platform.
2. Complete the profile and add structured skills/profile context.
3. Upload a PDF/DOCX CV; observe durable background processing and profile enrichment.
4. Browse the internship catalog. The current mobile discovery UI exposes work-type filters (`All`, `Remote`, `Hybrid`, `On-site`).
5. Save/unsave an opportunity and verify Saved Internships updates.
6. Calculate/view persisted hybrid matches.
7. Open **Why You Match** to review strengths, missing skills, and generated guidance without treating the generated explanation as the numeric score authority.
8. Generate an AI-assisted application/cover-letter draft, review/edit it, submit, and follow the tracker.
9. When an interview exists, use the interview preparation flow.
10. Verify durable notifications and, on a configured native device, push-device registration/delivery.
11. Switch between English, Turkish, and Arabic; Arabic uses RTL layout.

Candidate lifecycle states are:

```text
saved -> applied -> interviewing -> accepted / rejected
```

Candidates cannot self-promote their application to employer-controlled `interviewing`, `accepted`, or `rejected` states.

### 11.2 Employer + Admin Moderation

1. Create an **employer** account using the email/password employer flow.
2. Create the organization profile and submit it for review.
3. Using an authorized Admin account, review and approve/reject the organization.
4. After verification, create an employer opportunity. It enters `under_review`; it is not automatically public.
5. In Admin, either:
   - **approve** -> listing becomes `published`, or
   - **request changes** -> listing returns to `draft` with owner-visible feedback.
6. For a requested-change listing, reopen the same listing in Employer UI. Existing fields are prefilled. Edit and resubmit -> `under_review`; prior employer-visible feedback is cleared.
7. After publication, submit a candidate application and verify the employer applicant pipeline.
8. Employer may schedule interviews and apply valid status transitions.
9. Candidate insight is available under Employer product policy with a separate AI quota. Employer Pro additionally enables interview kit, shortlist comparison, AI internship-description drafting, pipeline analytics, and multiple published listings.

Employer Free supports one published listing at a time. The backend, not a client flag, enforces listing/product policy.

### 11.3 Separate Compliance Review

Organization verification and compliance evidence are separate trust domains.

A representative compliance flow is:

```text
Employer creates claim
  -> attaches private evidence
  -> submits claim
  -> pending
  -> Admin approves / rejects
```

An approved claim means that the evidence for that recorded claim, jurisdiction, and scope was reviewed. It is **not** legal certification and does not publish an internship.

---

## 12. Automated Verification

From repository root:

```bash
python -m ruff check backend/app worker tests --output-format=concise
python -m pytest -q
```

Mobile TypeScript:

```bash
cd apps/mobile
npx tsc --noEmit
```

Admin TypeScript:

```bash
cd apps/admin
npm ci
npm run typecheck
```

This runbook intentionally does not hard-code a total test count because that number changes as coverage grows.

---

## 13. Common Troubleshooting

| Symptom | Check |
|---|---|
| Android emulator cannot reach local API | Use a host-reachable development URL such as `http://10.0.2.2:8000/api/v1` |
| `/api/v1/health` returns `503` | Check development DB connectivity, Redis, and an active RQ worker |
| Native RevenueCat functionality unavailable in Expo Go | Use a native development client (`expo run:*` / `expo start --dev-client`) |
| Admin API returns `403` | Confirm authenticated Supabase UUID is in server-side `ADMIN_USER_IDS` |
| Employer cannot create opportunity | Confirm employer role, verified organization, and plan listing capacity |
| Employer listing not visible publicly | Check moderation state; `under_review`/`draft` are intentionally non-public |
| Compliance evidence unavailable | Check private development Storage configuration and authorized claim ownership/Admin access |
| RevenueCat reconciliation unavailable | Check server-only RevenueCat project/secret configuration and environment |

---

## 14. Security Boundaries Judges Should Notice

- Supabase JWT proves user identity; role/ownership/Admin authority is enforced server-side.
- Private CV, avatar, and compliance documents are mediated by authenticated backend endpoints; raw storage paths are not client authorization tokens.
- Employer organization verification does not bypass listing moderation.
- Compliance approval is scoped evidence review, not legal certification.
- Subscription state and protected AI/product policy are backend-controlled for server operations.
- Production disables Swagger, ReDoc, and OpenAPI JSON.
- Permanent account deletion requires recent reauthentication; Apple-linked deletion applies the Apple authorization revocation boundary when required.

For deeper review:

- [Architecture](ARCHITECTURE.md)
- [API Contract](API_CONTRACT.md)
- [Database](DATABASE.md)
- [Security](SECURITY.md)
- [Development](DEVELOPMENT.md)

---

## 15. Release-Status Check Before Shipaton Judging

At the 2026-09-24 documentation checkpoint, do **not** infer public-store availability from this repository or this runbook. Verify the final store listing independently before the Shipaton submission is treated as Standard Track-ready.

RevenueCat's current 2026 submission guide states that main-competition entries must be publicly released in a qualifying store, available in the United States, and use RevenueCat to power the qualifying monetization path; TestFlight/testing tracks do not count as the public release. The same guide lists the submission deadline as **September 30, 2026 at 11:45 pm PDT**.

For paid-feature judge access, follow the final official submission requirement (for example, a configured free trial or store-compatible promo mechanism). Do not reintroduce the removed custom InternMatch in-app promo unlock field merely for judging.
