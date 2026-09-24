# InternMatch AI — Mobile Client

Expo / React Native application for both **Student / Candidate** and **Employer** product surfaces.

**Release source:** `707601d93294c891d53b900d01c644200f27292b`
**App version:** `1.0.0`

## Current Stack

- Expo SDK `54`
- React Native `0.81.5`
- React `19.1.0`
- TypeScript `~5.9`
- Supabase JS `^2.45.0`
- RevenueCat `react-native-purchases` `10.7.2`
- Expo Notifications
- Expo Apple Authentication
- Expo Web Browser / Supabase OAuth
- React Navigation
- i18next / react-i18next

## Product Roles

### Student / Candidate

Candidate accounts support email/password, Google OAuth, and Sign in with Apple on iOS. The mobile experience includes profile/CV workflows, internship discovery, saved opportunities, matchups/Why You Match, AI application assistance, application tracking, notifications, multilingual UI, and Student Pro.

### Employer

Employer accounts use the email/password workflow. Employer screens cover organization identity/verification, compliance evidence, opportunity creation/ownership, applicant/interview workflows, moderation status, and Employer Pro.

Candidate Google/Apple social signup is not an employer signup path.

## Localization

The UI supports:

- English (`en`)
- Turkish (`tr`)
- Arabic (`ar`)

Arabic uses RTL layout behavior. Generated AI content accepts explicit supported content locales in relevant API workflows; UI locale remains a client responsibility.

## Environment

Copy the template:

```bash
cp .env.example .env
```

Development configuration:

```text
EXPO_PUBLIC_SUPABASE_URL
EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY
EXPO_PUBLIC_API_URL
EXPO_PUBLIC_REVENUECAT_API_KEY
```

Production release environments configure:

```text
EXPO_PUBLIC_REVENUECAT_IOS_API_KEY
EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY
```

All `EXPO_PUBLIC_*` values are bundled into the client and are publicly readable. Never put Supabase service-role credentials, RevenueCat server secrets/webhook secrets, database credentials, or Apple private keys here.

## API Base URL

`EXPO_PUBLIC_API_URL` must include the `/api/v1` prefix.

Typical development examples:

- Android emulator -> `http://10.0.2.2:8000/api/v1`
- iOS simulator/web -> `http://localhost:8000/api/v1`
- physical device -> reachable development API address

Release configuration points to the production API (`https://api.internmatch.college/api/v1`).

## RevenueCat

Canonical contracts:

| Audience | Entitlement | Offering | Package | Product |
|---|---|---|---|---|
| Student | `pro_student` | `default` | `$rc_monthly` | `internmatch_pro_student_monthly` |
| Employer | `pro_employer` | `employer_default` | `$rc_monthly` | `internmatch_pro_employer_monthly` |

Development Test Store uses the development public key. Release builds use platform-specific public SDK keys. Prices are loaded dynamically from RevenueCat/store package metadata.

The client synchronizes its RevenueCat App User ID to the authenticated Supabase user. Backend subscription state/reconciliation remains authoritative for server-side product policy.

The removed custom promo-code Pro unlock is not part of the current mobile store application.

## Native Development Client Required

Standard Expo Go does not include the native RevenueCat billing module.

```bash
npm ci
npx expo run:android
npx expo start --dev-client
```

On macOS:

```bash
npx expo run:ios
```

## Notifications

The app integrates an authenticated durable notification inbox with Expo push-device registration. Push delivery supplements persisted notification state; no realtime delivery guarantee is assumed.

## EAS Profiles

`eas.json` currently defines:

- `development`: development client, internal, Android APK, `APP_VARIANT=development`
- `preview`: internal non-dev-client build, Android APK
- `production`: EAS production environment, `autoIncrement`, Android app bundle, `APP_VARIANT=production`
- CLI version source: `remote`

## Type Check

```bash
npm ci
npx tsc --noEmit
```

## Release Checkpoint

At the 2026-09-24 documentation checkpoint, iOS Build 9 is associated with App Review and Build 10 from the release commit has been uploaded to App Store Connect/TestFlight for validation. TestFlight is not public App Store availability.

## Full Project Documentation

- [Project README](../../README.md)
- [Judge Runbook](../../docs/JUDGE_RUNBOOK.md)
- [Architecture](../../docs/ARCHITECTURE.md)
- [API Contract](../../docs/API_CONTRACT.md)
- [Security](../../docs/SECURITY.md)
