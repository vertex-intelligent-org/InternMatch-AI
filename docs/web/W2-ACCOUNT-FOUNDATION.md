# W2 — Web account foundation

Baseline: W1 + W1.1 + W1.2, repository main `4ad7dc023ac09866b7b09e85c4f3d4ec8948d28b`.
No mobile/backend/landing implementation is changed. No production settings, accounts or database rows were used by the verification suite.

## Delivered routes

- `/app/sign-in`: actual password sign-in; localized errors; recovery and confirmation resend.
- `/app/sign-up`: explicit Intern/Employer selection before manual fields; confirmation-based signup.
- `/app/forgot-password`, `/app/reset-password`: same-browser PKCE recovery, single flow intent, password update and local logout.
- `/app/account`: verified account destination; student/employer role comes from backend canonical profile.
- `/app/student`, `/app/employer`: protected identity/role entry screens. Functional workspace pages are W3/W4, not implemented dashboards.
- `/app/api/session`: minimal same-origin session readiness response, no profile name/email or tokens. This supports the future landing button; the landing page has not yet been edited.
- `/app/review/auth`, `/app/foundation`, `/app/review/motion`: clearly separate interface previews.

Landing links should ultimately point to `/app/sign-in` and `/app/sign-up`, never the review route. A saved *web* session can continue through `/app/account`. An installed mobile session is not automatically a browser session.

## Local setup

The installer copies only the mobile application's public URL/publishable-key/API URL values into a new, ignored `apps/web/.env.local`, if those values exist and validate. It never prints their values, uses a service-role key, or overwrites an existing web environment file. It creates a fresh random web flow secret. No Supabase settings are changed.

If the helper reports NOT_CREATED, fill `.env.local` from `.env.example`; never paste credentials into chat. Use only the publishable or legacy anon key. Set `INTERNMATCH_API_URL` to the backend URL ending in `/api/v1`, and `WEB_ORIGIN=http://127.0.0.1:3100` locally. Restart Next after environment changes.

Password sign-in to existing accounts can be enabled with `WEB_AUTH_ENABLED=1` and valid settings. Live backend compatibility is not asserted by isolated tests: the deployed server must expose `/auth/sync`, `/profile` and `/auth/complete-signup` with the reviewed contracts.

Email flows stay disabled by default. Before enabling `WEB_EMAIL_FLOWS_ENABLED=1`, allow the exact callback `http://127.0.0.1:3100/app/api/auth/callback` in Supabase redirect settings for local use. Production uses `https://internmatch.college/app/api/auth/callback` with `WEB_ORIGIN=https://internmatch.college`. Preserve the mobile redirects. Verify the configured confirmation/recovery email templates actually redirect through the PKCE `code` flow; token-hash templates are not supported by this package. Links must be opened in the browser which initiated the flow, within ten minutes. A different device/browser needs a new flow or normal sign-in after confirmation.

Google remains disabled until the provider and exact web redirects are configured and tested. `WEB_GOOGLE_ENABLED=1` activates the implemented web OAuth path; it does not configure the provider. Apple Web stays disabled and has no activation flag: web credentials, authorization-code retention and backend token revocation require a separate implementation.

## Contracts and authority

1. Supabase `getUser()` verifies the online identity; a cookie or local user object is not authorization.
2. Backend `POST /api/v1/auth/sync` checks canonical profile existence.
3. `GET /api/v1/profile` supplies authoritative `preferences.account_type`, strictly `intern` or `employer`; missing/unknown role never defaults.
4. Only `POST /api/v1/auth/complete-signup` provisions an account. Confirmed email metadata is pending signup input only, never a role authorization source. No profile PUT is used to create/repurpose accounts.
5. Google sign-in without a canonical account follows the mobile policy: guarded backend deletion of the newly-created identity, then local logout. Existing social-account signup is rejected without deletion or changing its role.

Source reviewed: backend auth/profile and mobile auth/signup contracts at the baseline revision. Production source deployment was not changed or verified by this package.

## Session and request decisions

Supabase SSR 0.12.7 and supabase-js 2.118.0 are exact lockfile dependencies. Server-only BFF: no browser Supabase client and no tokens in localStorage, UI JSON, or logs. Cookie namespace `im-web-session`, HttpOnly, SameSite=Lax, Path=/app; Secure on HTTPS. Each request owns its client and cookie jar. Proxy persists refresh cookies, while protected server pages recheck identity and canonical profile independently.

Auth responses are private/no-store, including Set-Cookie responses. Origin + Fetch Metadata checks protect JSON POST mutations; bounded input, fixed backend paths, ten-second upstream timeout and internal-only redirects. Flow intent is encrypted/authenticated with AES-256-GCM and expires after ten minutes. Recovery grants bind to the verified user and the exchanged access token. They expire if the token refreshes; request a new link. A forged callback cannot log out an existing session. Logout clears this browser; it does not claim immediate revocation on every device.

No automatic retry of mutation requests. Configure rate limits and CAPTCHA on the auth service for production as appropriate; this package handles returned rate-limit errors but does not change provider policy.

## Visual and language decisions

W1.2 local Bricolage Grotesque/Cairo fonts, light landing-inspired canvas, dark blue surfaces, reduced motion, branded loading and preference dialogs remain. Arabic uses RTL; Turkish and Arabic are UTF-8. Auth uses the same reusable brand controls and mobile-derived labels. Actual auth browser tests cover all three locales, both themes, 320px width and axe accessibility.

## Verification and limits

- 8 unit/encoding policy checks.
- 104 existing interface/browser checks.
- 30 isolated auth/browser integration cases: password form, role gate, canonical role enforcement, confirmation PKCE, reset grants, malicious origin/callback, backend outage retry, local logout, independent browsers, refresh, Google orphan cleanup and existing-account preservation.
- ESLint zero warnings, TypeScript no emit and optimized Next production build.

The fixture starts ONLY loopback ports 4412/3111 and overrides Supabase/backend URLs with local fake services. It creates no real users or emails. Google tests simulate the provider redirect; they do not certify real OAuth credentials. No live end-to-end account flow, deployed email delivery, production session or Apple integration is claimed.

Before live testing: configure local settings and provider redirects, then verify one real account flow with the owner. W3/W4 implement the actual student/employer workflows. Production hosting, reverse-proxy routing for `/app`, landing integration and release are separate steps.
