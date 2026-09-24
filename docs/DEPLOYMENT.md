# InternMatch AI — Deployment & Release Architecture

**Documentation checkpoint:** 2026-09-24
**Release source:** `707601d93294c891d53b900d01c644200f27292b`

This document separates **local/development reproduction** from **release/production architecture**. Never use production as a test environment.

## 1. Deployment Surfaces

| Surface | Runtime | Role |
|---|---|---|
| Mobile | Expo / React Native | Student + Employer product |
| Admin | Next.js | Trust & Safety Console |
| API | FastAPI / Uvicorn | Authenticated application boundary |
| Worker | Python RQ | Background AI/data jobs |
| Queue | Redis | RQ queue and operational dependency |
| Database/Auth/Storage | Supabase | PostgreSQL/pgvector, Auth, private storage |
| AI | Google Gemini | Embeddings and generated assistance |
| Monetization | RevenueCat | Store SDK + server reconciliation/webhooks |

Public product site: `https://internmatch.college`
Production API origin: `https://api.internmatch.college`

## 2. Local Development Model

The repository `docker-compose.yml` provides:

- `backend` on port 8000
- `worker`
- Redis 7
- local `pgvector/pgvector:0.8.6-pg17-bookworm` PostgreSQL

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

### Important Supabase boundary

The local PostgreSQL container is not a complete local Supabase installation. The full application migration chain references Supabase-managed resources such as `auth.users`, and the product also depends on Supabase Auth/Storage.

For faithful full-stack development reproduction:

1. create/use a **development** Supabase project
2. point `SUPABASE_*` and `DATABASE_URL` to that development project
3. apply the required fresh-database migration chain once through `027`
4. provision required private storage buckets
5. run backend/worker/Redis locally or through Docker Compose

The local PostgreSQL service remains useful for isolated database/container scenarios, but should not be documented as a drop-in full Supabase replacement.

## 3. Migration & Storage Provisioning

Repository migration source spans `001` through `028`.

- Current release execution baseline: **through `027`**
- `027`: notification infrastructure
- `028_promo_campaigns.sql`: exists in source but is **not** part of the current production-applied release baseline

For a fresh development Supabase database, apply the required migration chain once in numeric order through `027`. For an existing environment, track what is already applied and never blindly replay migrations.

Storage:

- `cvs`: private development Supabase bucket configured by `CV_STORAGE_BUCKET`; provision separately
- `avatars`: private bucket provisioned by `database/supabase_storage_setup.sql`
- `employer-compliance-evidence`: private PDF bucket provisioned by migration `025`

Do not run migration `028` as part of this release procedure.

## 4. Server Environment

Start from `.env.example` and inject real values through the target environment's secret system; never commit them.

Key server settings include:

```text
ENVIRONMENT
PORT
LOG_LEVEL

SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_JWT_SECRET
DATABASE_URL
CV_STORAGE_BUCKET
AVATAR_STORAGE_BUCKET
COMPLIANCE_STORAGE_BUCKET

REDIS_URL

GEMINI_API_KEY
LLM_MODEL_NAME
EMBEDDING_MODEL_NAME
EMBEDDING_DIMENSION
SKILL_FUZZY_THRESHOLD

REVENUECAT_PROJECT_ID
REVENUECAT_SECRET_KEY
REVENUECAT_ENVIRONMENT
REVENUECAT_WEBHOOK_AUTH_TOKEN
REVENUECAT_WEBHOOK_SIGNING_SECRET

ADMIN_USER_IDS
ADMIN_ALERT_EMAILS
ADMIN_BASE_URL

SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
SMTP_FROM_EMAIL
SMTP_FROM_NAME
SMTP_SECURITY

ALLOWED_ORIGINS

APPLE_SIGN_IN_CLIENT_ID
APPLE_SIGN_IN_TEAM_ID
APPLE_SIGN_IN_KEY_ID
APPLE_SIGN_IN_PRIVATE_KEY
```

RevenueCat/Apple/Supabase service credentials are server-only.

## 5. Mobile Release Environment

Mobile public configuration is defined via `EXPO_PUBLIC_*` variables. These values are readable from the client bundle by design.

Development:

```text
EXPO_PUBLIC_SUPABASE_URL
EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY
EXPO_PUBLIC_API_URL
EXPO_PUBLIC_REVENUECAT_API_KEY
```

Production release environments additionally configure platform RevenueCat public SDK keys:

```text
EXPO_PUBLIC_REVENUECAT_IOS_API_KEY
EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY
```

Never put `SUPABASE_SERVICE_ROLE_KEY`, `REVENUECAT_SECRET_KEY`, webhook secrets, database credentials, or Apple private keys into mobile public variables.

## 6. EAS Profiles

`apps/mobile/eas.json` defines:

| Profile | Current contract |
|---|---|
| `development` | development client, internal distribution, Android APK, `APP_VARIANT=development` |
| `preview` | non-development-client internal distribution, Android APK |
| `production` | EAS `production` environment, `autoIncrement=true`, Android app bundle, `APP_VARIANT=production` |

EAS CLI version source is `remote`.

These profiles are release configuration; this document does not instruct evaluators to launch a new production build.

## 7. RevenueCat Release Boundary

Mobile contracts:

- Student: `pro_student` / `default` / `$rc_monthly` / `internmatch_pro_student_monthly`
- Employer: `pro_employer` / `employer_default` / `$rc_monthly` / `internmatch_pro_employer_monthly`

Development Test Store configuration is separate from public-store configuration. Store prices/products are resolved dynamically.

Server-side production configuration includes RevenueCat project/secret credentials plus webhook authentication. The backend persists subscription state, reconciles against RevenueCat, and processes authenticated provider webhooks.

The current mobile store app does not expose the removed custom promo-code Pro-unlock UI. Migration `028_promo_campaigns.sql` is not in the current production-applied baseline.

## 8. API Production Mode

FastAPI production mode intentionally sets:

- Swagger UI: disabled
- ReDoc: disabled
- OpenAPI JSON: disabled

Do not use `/openapi.json` as a production health probe.

### Health endpoints

- `GET /health` — process liveness; no DB/Redis/RQ dependency check
- `GET /api/v1/health` — operational readiness; checks PostgreSQL, Redis, and at least one RQ worker

Ready -> HTTP 200.
Required dependency unavailable -> HTTP 503.

## 9. Container Security

Repository CI builds backend/worker containers and verifies that runtime user ID is non-root. Release environments should preserve least-privilege container/runtime behavior and keep secrets outside images/source.

## 10. Admin Console

Admin browser configuration uses:

```text
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
NEXT_PUBLIC_API_URL
```

These values do not grant Admin authority. The backend still validates the authenticated user against `ADMIN_USER_IDS` for protected administration routes.

## 11. Release Checkpoint

As of 2026-09-24:

- Source release commit: `707601d93294c891d53b900d01c644200f27292b`
- iOS app version: `1.0.0`
- Build 9: associated with App Review
- Build 10: built from the release commit and uploaded to App Store Connect / TestFlight for validation
- TestFlight is not public App Store availability
- Public Google Play availability is not asserted by this document

Replace checkpoint language with verified public store URL(s) only after those releases are actually available.

## 12. Production Deployment Invariants

- Never deploy with placeholder credentials.
- Never expose private IPs/SSH/Tailscale addresses in public docs.
- Never apply database migrations blindly to an existing environment.
- Never run migration `028` as part of the current release baseline.
- Never put server secrets in mobile/Admin public configuration.
- Keep `ALLOWED_ORIGINS` explicit in production.
- Keep production API documentation endpoints disabled unless policy intentionally changes.
- Keep database, Redis, and worker readiness observable.
- Keep RevenueCat webhook authentication configured when enabling provider delivery.

## 13. Related Documentation

- [Development](DEVELOPMENT.md)
- [Architecture](ARCHITECTURE.md)
- [Security](SECURITY.md)
- [Database](DATABASE.md)
- [API Contract](API_CONTRACT.md)
- [Judge Runbook](JUDGE_RUNBOOK.md)
