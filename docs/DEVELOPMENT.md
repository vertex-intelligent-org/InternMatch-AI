# InternMatch AI — Development Guide

**Documentation checkpoint:** 2026-09-24
**Release source:** `707601d93294c891d53b900d01c644200f27292b`

Use development credentials and development infrastructure only. Production is not a test environment.

## 1. Reference Toolchain

The repository CI provides the most reliable runtime reference:

| Component | Reference / requirement |
|---|---|
| Python | CI runtime `3.13` |
| Node.js | CI runtime `22` |
| Git | modern Git; no repository-defined hard minimum |
| Docker / Docker Compose | needed for optional containerized services; no repository-defined hard minimum |
| Android | Android Studio / SDK tooling compatible with Expo SDK 54 |
| iOS | macOS + Xcode for local native iOS builds |

Mobile dependencies include Expo SDK 54, React Native 0.81.5, TypeScript ~5.9, and `react-native-purchases` 10.7.2.

## 2. Clone

```bash
git clone https://github.com/vertex-intelligent-org/InternMatch-AI.git
cd InternMatch-AI
```

## 3. Full-Stack Development Data Boundary

The complete application is built around Supabase PostgreSQL + Auth + Storage. Migration `001` references `auth.users`; therefore a plain PostgreSQL database alone is not a faithful complete replacement.

For full-stack development:

1. use a **development Supabase project**
2. copy `.env.example` to `.env`
3. fill only development values
4. point `DATABASE_URL` and Supabase credentials to that project
5. apply a fresh migration chain once through `027`
6. provision private storage buckets

Do not run `028_promo_campaigns.sql` for the current release baseline.

## 4. Root Environment

```bash
cp .env.example .env
```

Important groups:

- runtime: `ENVIRONMENT`, `PORT`, `LOG_LEVEL`
- Supabase/database: `SUPABASE_*`, `DATABASE_URL`
- private storage: `CV_STORAGE_BUCKET`, `AVATAR_STORAGE_BUCKET`, `COMPLIANCE_STORAGE_BUCKET`
- queue: `REDIS_URL`
- AI: `GEMINI_API_KEY`, model/embedding config, fuzzy threshold
- RevenueCat server: project/secret/environment/webhook settings
- Admin: `ADMIN_USER_IDS`, alert emails/base URL
- SMTP settings
- CORS allow-list
- Sign in with Apple server revocation settings

Never put real secrets into tracked files.

## 5. Database Migrations & Storage

Migration source: `001` through `028`.
Current release execution baseline: through `027`.

For a new development Supabase database, apply required migrations once in numeric order through `027`. Existing databases must track their applied state and must not blindly replay migrations.

Storage provisioning:

- create a private `cvs` bucket (or configured `CV_STORAGE_BUCKET`) separately for development
- apply `database/supabase_storage_setup.sql` for the private `avatars` bucket
- migration `025` provisions private `employer-compliance-evidence`

## 6. Docker Services

```bash
docker compose up --build -d
docker compose ps
```

Compose provides backend, worker, Redis, and a local pgvector PostgreSQL service. For faithful full-stack behavior, backend `DATABASE_URL`/Supabase configuration should point to your development Supabase project; the plain local PostgreSQL service does not provide Supabase Auth/Storage schemas.

Health:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/health
```

The first is process liveness. The second checks DB/Redis/RQ worker readiness and returns HTTP 503 when a required dependency is unavailable.

## 7. Mobile Development

```bash
cd apps/mobile
cp .env.example .env
npm ci
```

Development variables:

```text
EXPO_PUBLIC_SUPABASE_URL
EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY
EXPO_PUBLIC_API_URL
EXPO_PUBLIC_REVENUECAT_API_KEY
```

`EXPO_PUBLIC_*` values are publicly readable in the bundle. Never put server secrets there.

### Native development client

RevenueCat native functionality is not available in standard Expo Go.

Android:

```bash
npx expo run:android
npx expo start --dev-client
```

On macOS:

```bash
npx expo run:ios
```

For Android emulator access to a host backend, the template uses `http://10.0.2.2:8000/api/v1`. Physical devices need a reachable development API address.

## 8. RevenueCat Development

Development can use `EXPO_PUBLIC_REVENUECAT_API_KEY` with the RevenueCat Test Store. Test Store is a development path, not evidence of public-store release.

Canonical contracts:

- Student: `pro_student` / `default` / `$rc_monthly` / `internmatch_pro_student_monthly`
- Employer: `pro_employer` / `employer_default` / `$rc_monthly` / `internmatch_pro_employer_monthly`

The mobile code treats Test Store keys as not supporting store-level `restorePurchases`. Production builds use the platform public keys configured by the release environment.

## 9. Admin Console Development

```bash
cd apps/admin
cp .env.example .env.local
npm ci
npm run dev
```

Admin public variables:

```text
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
NEXT_PUBLIC_API_URL
```

The backend still decides whether the authenticated user is an Admin through `ADMIN_USER_IDS`.

## 10. Landing Page

The repository contains a Next.js landing/product surface under `apps/landing`. Use its package scripts/lockfile as source of truth for local startup. Do not conflate the landing site with backend authorization.

## 11. Quality Checks

Backend:

```bash
python -m pytest
python -m ruff check backend/app worker tests --output-format=concise
```

Mobile:

```bash
cd apps/mobile
npm ci
npx tsc --noEmit
```

Admin:

```bash
cd apps/admin
npm ci
npm run typecheck
```

CI also validates Docker Compose and non-root backend/worker container runtime.

## 12. Product-Sensitive Development Rules

- Do not bypass JWT identity/role dependencies to make local tests easier.
- Do not weaken listing moderation; verified organizations still require listing review.
- Do not expose `employer_visible_feedback` through public listing contracts.
- Do not replace backend subscription state with a local mobile flag.
- Do not hard-code store pricing.
- Do not use production DB/API/RevenueCat secrets for local testing.
- Do not run migration `028` as part of the current release baseline.
- Keep Google OAuth on the current candidate account path; employer social signup is not enabled.

## 13. Production API Documentation

Swagger/ReDoc/OpenAPI are available only when enabled by non-production configuration. Production intentionally disables `/docs`, `/redoc`, and `/openapi.json`.

## 14. Repository References

- [Architecture](ARCHITECTURE.md)
- [API Contract](API_CONTRACT.md)
- [Database](DATABASE.md)
- [Security](SECURITY.md)
- [Deployment](DEPLOYMENT.md)
- [Judge Runbook](JUDGE_RUNBOOK.md)
