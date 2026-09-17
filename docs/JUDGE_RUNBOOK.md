# InternMatch AI — Judge Reproduction Runbook

> **Target Audience:** Hackathon judges, technical evaluators, and developers testing **InternMatch AI** on a fresh development workstation.

---

## 1. What This Runbook Reproduces

This runbook guides you through reproducing the full end-to-end system:
1. **Infrastructure & Backend:** Dockerized FastAPI service, Redis task queue, Python RQ worker, and PostgreSQL with `pgvector`.
2. **Database & AI Services:** Schema migrations, demo internship datasets, semantic vector search, and Gemini AI application generation.
3. **Cross-Platform Mobile Client:** Expo SDK 54 / React Native client running on the Android Emulator or physical device.
4. **RevenueCat In-App Purchases:** Native RevenueCat Test Store integration demonstrating Candidate **Pro Student** subscription flow, RevenueCat `CustomerInfo` entitlement updates, dynamic pricing, and entitlement-driven tier updates.

---

## 2. Prerequisites

Ensure your host environment has the following software installed:

| Tool | Recommended Version | Purpose |
|---|---|---|
| **Git** | `v2.40+` | Source control & repository cloning |
| **Python** | `3.13.x` | Backend runtime & local test runner |
| **Node.js** | `v22.x` LTS | Mobile JavaScript runtime (matches CI reference runtime) |
| **npm** | `v10.x+` | Package manager for mobile app |
| **Docker Desktop** | `v24+` (with Compose v2) | Containerized backend, Redis, and database |
| **Android Studio** | Latest (Android SDK 34+) | Android Emulator & native Android build tooling |

> [!NOTE]
> **No Google Play Developer account is required.**
> RevenueCat Test Store operates natively in development builds without Google Play Console billing dependencies or merchant accounts.

---

## 3. Clone and Repository Structure

Clone the repository and enter the project root:

```bash
git clone https://github.com/AISSCLUB/InternMatch-AI.git
cd InternMatch-AI
```

The repository structure:
```
.
├── apps/
│   ├── mobile/             # React Native / Expo SDK 54 mobile application
│   └── landing/            # Next.js web landing page (optional)
├── backend/                # FastAPI application & core domain logic
├── database/               # SQL migrations, RLS policies, and seed data
├── docs/                   # System architecture, API contracts, and security guides
├── scripts/                # Utility scripts (internship seeding)
├── tests/                  # Pytest test suite (518+ tests)
├── worker/                 # Python RQ background job workers
└── docker-compose.yml      # Orchestration for backend, worker, redis, and postgres
```

---

## 4. Server Environment Setup

Copy the server environment template to `.env`:

```bash
cp .env.example .env
```

Configure your environment keys in `.env`:

```ini
# Application Runtimes
ENVIRONMENT=development
PORT=8000
LOG_LEVEL=INFO

# Supabase Credentials (from your Supabase project dashboard)
SUPABASE_URL=https://<your-project-id>.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_pub_...
SUPABASE_SERVICE_ROLE_KEY=sb_serv_...
SUPABASE_JWT_SECRET=your_supabase_jwt_secret
DATABASE_URL=postgresql://postgres:<password>@<db-host>:5432/postgres
CV_STORAGE_BUCKET=cvs
AVATAR_STORAGE_BUCKET=avatars

# Redis Task Queue (Docker Compose default)
REDIS_URL=redis://redis:6379/0

# Gemini AI (for matching explanations & cover letters)
GEMINI_API_KEY=AIzaSy...
LLM_MODEL_NAME=gemini-3.5-flash
EMBEDDING_MODEL_NAME=gemini-embedding-2
EMBEDDING_DIMENSION=1536
SKILL_FUZZY_THRESHOLD=85

# Optional/reserved server-side RevenueCat credential (Not required for mobile Test Store flow)
REVENUECAT_SECRET_KEY=

# CORS Allowed Origins
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000,http://localhost:19006
```

---

## 5. Database & Storage Initialization

If using an external Supabase instance, execute the SQL migration scripts in order:

```
1. database/migrations/001_initial_schema.sql
2. database/migrations/002_rls_policies.sql
3. database/migrations/003_add_processing_job_progress.sql
4. database/migrations/004_add_application_applied_date.sql
5. database/migrations/005_add_avatar_storage_path.sql
6. database/migrations/006_add_saved_internships.sql
7. database/migrations/007_add_application_status_events.sql
8. database/migrations/008_add_internship_employer_ownership.sql
9. database/migrations/009_add_internship_lifecycle_status.sql
10. database/migrations/010_add_application_interview_schedule.sql
11. database/supabase_storage_setup.sql
```

For complete database schema details, see [docs/DATABASE.md](docs/DATABASE.md).

---

## 6. Backend / Worker / Redis Startup

Start the backend services using Docker Compose:

```bash
docker compose up --build -d
```

### Health Verification

Check container health:
```bash
docker compose ps
```

Verify the root liveness probe:
```bash
curl http://localhost:8000/health
# Expected Output: {"status":"healthy","version":"1.0.0","environment":"development",...}
```

Verify component readiness (Database, Redis, Worker):
```bash
curl http://localhost:8000/api/v1/health
# Expected Output: {"status":"ready","database":"connected","redis":"connected","worker":"active",...}
```

Interactive Swagger documentation is accessible at:
👉 **`http://localhost:8000/docs`**

---

## 7. Seed Demo Internships

Populate the database with curated demo internships:

```bash
# Using the Python seeding script (requires local Python environment with dependencies)
python scripts/seed_internships.py

# Alternatively, execute the SQL seed directly in your database:
# database/seeds/001_demo_internships.sql
```

---

## 8. Mobile Application Configuration

Navigate to the mobile directory and copy the environment template:

```bash
cd apps/mobile
cp .env.example .env
```

Configure `apps/mobile/.env`:

```ini
# Public Supabase credentials
EXPO_PUBLIC_SUPABASE_URL=https://<your-project-id>.supabase.co
EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_pub_...

# Backend API URL (Must include /api/v1)
# For Android Emulator communicating with host machine:
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000/api/v1

# For Physical Device on local Wi-Fi:
# EXPO_PUBLIC_API_URL=http://<YOUR_COMPUTER_LAN_IP>:8000/api/v1

# Public RevenueCat Test Store API Key (from RevenueCat Project Settings)
EXPO_PUBLIC_REVENUECAT_API_KEY=<YOUR_REVENUECAT_TEST_STORE_PUBLIC_SDK_KEY>
```

---

## 9. Install Mobile Dependencies

```bash
npm ci
```

---

## 10. Native Android Runtime & RevenueCat Testing

> [!IMPORTANT]
> **RevenueCat Native In-App Purchases require a native development build.**
> Standard Expo Go does not bundle native store billing modules. To test real purchase flows and entitlement verification, launch the native Android development client.

### Launching with Native Android Development Client

1. **Start an Android Emulator** in Android Studio (or connect an Android device via USB debugging).
2. **Build and run the development client locally:**
   ```bash
   npx expo run:android
   ```
3. **Start the Metro bundler in development client mode:**
   ```bash
   npx expo start --dev-client
   ```

---

## 11. RevenueCat Test Store Configuration

InternMatch AI follows the canonical RevenueCat contract:

| Entity | Canonical Identifier | Description |
|---|---|---|
| **Entitlement** | `pro_student` | Candidate Pro Student tier & subscription status badge |
| **Offering** | `default` | Primary offering container |
| **Package** | `$rc_monthly` | Monthly subscription package |
| **Product** | `internmatch_pro_student_monthly` | In-app purchase product |

### Setting Up a Test Store Project in RevenueCat Dashboard:
1. Create a project on [RevenueCat Dashboard](https://app.revenuecat.com/).
2. Create an App under your project (e.g. Android Test Store).
3. Create Entitlement: `pro_student`.
4. Create Product: `internmatch_pro_student_monthly` (attach to `pro_student`).
5. Create Offering: `default` with package `$rc_monthly` containing `internmatch_pro_student_monthly`.
6. Copy the **Public API Key** for your Test Store app and set it in `apps/mobile/.env` as `EXPO_PUBLIC_REVENUECAT_API_KEY`.

---

## 12. End-to-End Candidate Evaluation Checklist

Follow this workflow in the mobile app to evaluate features:

1. **Authentication:**
   - Tap **Sign Up** -> Enter email/password -> Confirm email or sign in.
   - User UUID is automatically bound as the RevenueCat App User ID.
2. **Candidate Profile & CV:**
   - Navigate to **Profile** -> Add headline, university, skills.
   - Upload a PDF CV on **CV Upload** screen -> Processing job parses experience and extracts skill keywords.
3. **Internship Discovery:**
   - Go to **Internships** tab -> Browse curated listings -> Filter by keyword or work type.
   - Tap heart icon to save internships -> Check **Saved Internships** screen.
4. **Matching & Why You Match:**
   - Navigate to **Matchups** -> View real-time match compatibility scores (e.g., 94%).
   - Tap a match to open **Why You Match** -> View skill alignment breakdown and personalized skill gap recommendations.
5. **AI Application Preparation:**
   - From internship detail, tap **Draft Application** -> Select tone (e.g., Enthusiastic, Professional) -> Generate job-tailored cover letter.
   - Track status in **Applications** tab (Applied, Interviewing, Accepted).
6. **RevenueCat Pro Student Subscription Flow:**
   - Open **Settings** -> **Plans & Upgrade** (or tap the Pro badge on Profile).
   - Verify dynamic pricing is loaded from RevenueCat (e.g., `$4.99 / month`).
   - Tap **Upgrade to Pro** -> Complete Test Store transaction.
   - Observe entitlement state update: `CustomerInfo` updates `pro_student` to active, Pro Student becomes the current plan, and PlanBadge reflects Pro status.
   - *Note on Test Store Behavior:* Test Store subscriptions use accelerated test renewal cycles and expire quickly by design. In Test Store mode, store receipt restoration is disabled; direct sandbox purchases drive the entitlement state used by the demo flow.

---

## 13. Employer Feature Scope Note

* **Active in this Release:** Candidate internship discovery, semantic matching, CV parsing, AI cover letters, and RevenueCat subscription management.
* **Preview in this Release:** Employer workspace screens (job posting, applicant pipeline management) are role-aware feature previews and will connect to employer billing in future milestones.

---

## 14. Running Automated Tests

### Backend Unit & Integration Tests
```bash
python -m pytest
```

### Python Linting & Formatting
```bash
python -m ruff check backend/app worker tests --output-format=concise
```

### Mobile TypeScript Validation
```bash
cd apps/mobile
npx tsc --noEmit
```

---

## 15. Troubleshooting Common Issues

| Problem | Cause | Solution |
|---|---|---|
| **Android Emulator cannot connect to API** | `localhost` points to the emulator itself, not host | Use `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000/api/v1` in `apps/mobile/.env` |
| **Physical device cannot connect to API** | Device cannot reach host computer | Ensure both are on same Wi-Fi; use `http://<YOUR_LAN_IP>:8000/api/v1` |
| **RevenueCat shows "No Offering"** | Package/Offering mismatch in dashboard | Ensure offering identifier is `default` and package is `$rc_monthly` |
| **RevenueCat native error in Expo Go** | `react-native-purchases` requires native binary | Run `npx expo run:android` or use `npx expo start --dev-client` |
| **Backend health check returns 500** | Postgres or Redis not running | Check `docker compose ps` and verify database migrations |

---

## 16. Security & Sensitive Files

- Never commit `.env` or files containing secret keys.
- For complete security posture and threat mitigation details, refer to [docs/SECURITY.md](docs/SECURITY.md).
