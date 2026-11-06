# W3-B: profile, CV and matching

This adds web consumers of the existing backend, not a new database or a separate account system. Existing mobile accounts remain canonical. No Supabase tables, policies, Auth settings, production rows, backend or mobile files are changed by this package.

## Included routes

- `/app/student/profile`: edit name, headline and skills; show CV status and existing education, experience and projects. Education/experience/project editors and avatars are not included yet.
- `/app/student/cv`: PDF/DOCX upload, explicit AI consent, progress, pause/resume status checks, cancel, and explicit confirmation/discard when the backend flags an identity conflict. Maximum 10 MiB. Server validates filename/signature; the existing backend retains final document validation and processing.
- `/app/student/matches`: read saved matches and explicitly calculate fresh matches.
- `/app/student/matches/:id`: request an explanation or prepare a draft in the selected language. Draft generation does not submit an application; the existing draft review page performs explicit submission.

Every BFF request verifies the Supabase user online and the canonical backend account role. Requests use the user's token; no service-role key exists in browser code. Same-origin mutation checks, explicit path/query/field allowlists and private/no-store responses apply. Job result presentation drops storage paths and extracted profile metadata. CV retries reuse an idempotency key for the same selected file. Matching/explanation mutations are not automatically repeated after an uncertain response. Polling pauses in hidden tabs and after ten minutes; navigation aborts browser polling, not the server job. A job ID in the URL resumes its owned status checks.

AI actions may consume existing plan allowance. No real paid AI action or real account mutation was performed while building this package. Tests use isolated sample services. Production authenticated CV/matching requires a user smoke test after local installation.

## Google web activation

The Google code already uses Supabase PKCE and the canonical backend signup/sync contracts. A provider being enabled for mobile does not prove its web callback configuration.

1. Supabase project `aoioyabrrdptrubjegkf` → Authentication → URL Configuration: retain existing mobile URLs and add the exact local callback `http://127.0.0.1:3100/app/api/auth/callback`. Do not replace the production Site URL with localhost. Use 127.0.0.1 consistently, not localhost.
2. The Google OAuth **Web application** client configured in Supabase must allow `https://aoioyabrrdptrubjegkf.supabase.co/auth/v1/callback` as an authorized redirect URI. Retain native Android/iOS OAuth clients. App secrets belong in provider settings only.
3. After those dashboard checks, stop the local dev preview. Run the supplied `Enable-Web-Google.mjs --callbacks-confirmed` from the package. It only enables the existing local `.env.local` flag, after verifying its configured local origin and project URL. It does not change dashboard settings or create a secret.
4. Restart `npm.cmd run dev` from apps/web. Test Google login with an existing InternMatch account. Test a separate new account through **Sign up**, selecting the account role explicitly. A new Google identity on Sign in must not silently become an account.
5. Before hosting, add `https://internmatch.college/app/api/auth/callback` to the same Supabase allowlist, set WEB_ORIGIN to `https://internmatch.college` in the host, and verify production redirects. Hosting and landing-page account links are not deployed here.

Email confirmation/recovery remain under their separate existing flag. Google activation does not enable those flows automatically.

## Apple web: concrete missing prerequisite

Apple web is deliberately disabled. The owner confirmed no web Services ID exists yet. Existing native Apple login must remain intact.

1. Apple Developer → Certificates, Identifiers & Profiles → Identifiers → Services IDs: create a web Services ID, for example `com.aissclub.internmatchai.web` if available. This differs from the native Bundle ID `com.aissclub.internmatchai`.
2. Enable Sign in with Apple and associate the existing primary Sign in with Apple App ID. Configure domain `aoioyabrrdptrubjegkf.supabase.co` and return URL `https://aoioyabrrdptrubjegkf.supabase.co/auth/v1/callback` for the Supabase OAuth option.
3. Configure a valid Apple web client secret securely in Supabase. Apple OAuth client secrets expire after at most six months; arrange rotation. In Supabase Apple Client IDs, put the web Services ID first and retain the native Bundle ID as another allowed ID. Never paste the private .p8 key or client secret in chat or commit them.
4. **Do not enable an Apple button just by cloning Google OAuth.** Current backend account deletion requires a fresh original Apple authorization code and exchanges it using a single configured `APPLE_SIGN_IN_CLIENT_ID`. Supabase OAuth consumes the original Apple code; its PKCE callback code is not an Apple revocation code. Web code exchange/revocation and client-ID selection need a separate coordinated backend integration before Apple web is released. Preserve native revocation throughout.
5. Next required input is the public Services ID after creation. Then implement and test web authorization/revocation with that client, existing native login, consent cancellation, account linking rules and account deletion. No Apple secret or Apple console changes are included here.

Official references:
- https://supabase.com/docs/guides/auth/social-login/auth-google
- https://supabase.com/docs/guides/auth/social-login/auth-apple
- https://supabase.com/docs/guides/auth/redirect-urls

## Remaining work

Employer opportunities/applicants/compliance pages, account settings/notifications, subscription checkout, complete profile section editors, landing-page session entry and production hosting remain subsequent stages. This package does not claim all mobile features are ported. Apple is not live. Google is locally implemented and fixture-tested; live OAuth still requires the dashboard setup and real browser account check above.
