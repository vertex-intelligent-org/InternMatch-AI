# W1 — Web foundation implementation checkpoint

Date: 2026-10-30

Parent baseline: `4ad7dc023ac09866b7b09e85c4f3d4ec8948d28b`.

## Scope

Add `apps/web` as an independent Next.js project, this document and a standalone `web-quality.yml` workflow. This phase adds files only. It does not modify any existing tracked file, convert the repository to npm workspaces or install dependencies in `apps/mobile`.

## Decisions implemented

1. Web code remains in the private application repository.
2. `/app` is the build-time URL prefix; local port is 3100.
3. Use the current mobile semantic colors and solid navigation frame.
4. Keep `en`, `tr` and `ar` dictionaries in strict UTF-8, with typed identical keys and encoding tests.
5. Apply real RTL to Arabic using logical CSS properties. Preserve LTR email and bidi-isolated filenames.
6. Resolve appearance before paint; persist only locale and appearance preferences in cookies scoped to `/app`.
7. Use responsive desktop sidebar and mobile bottom bar, visible language/theme controls and opaque dialogs.
8. Treat keyboard, focus, error messages and small screens as foundation requirements.
9. Keep W1 preview data explicit. Do not collect passwords or make production requests.
10. Introduce web CI independently; adding it to required repository checks is a separate release administration task.

## Design review routes

| Route | Purpose |
|---|---|
| `/app` | Redirects to the interface review in W1 only |
| `/app/foundation` | Overview and component review with student/employer preview switch |
| `/app/sign-in` | Explicit account boundary; no authentication fields yet |

The preview role switch changes sample presentation only and must never be reused as an authorization mechanism. W2 replaces `/app` routing with validated session/account logic.

## Token policy

Background/surface/accent/navigation colors follow mobile. Web status text has dedicated readable foreground tokens instead of using low-contrast light-mode status accents as small text. Small secondary text and input borders also receive readability-specific tokens. These choices are centralized and reviewable.

No transparency is applied to the navigation frame or dialog panel. The dialog backdrop dims/blurs the background. Reduced motion is respected.

## Validation boundaries

Local builds and UI tests are not proof of production API compatibility. W2 must verify actual deployed endpoints, Supabase redirect configuration, OAuth web setup, server-side account authority, file upload transport limits and private response caching.

Chrome automation is not a substitute for manual Safari/iPhone testing. Firefox and WebKit coverage is a follow-up browser gate before public release. Root landing rewrites and shared-origin preference behavior must also be tested before domain integration.

## Completion criteria

- Pinned clean install works and npm lockfile stays unchanged.
- Encoding, lint, TypeScript and production build pass.
- Browser interaction/layout/accessibility suite passes.
- Manual visual review of Arabic/Turkish/English and both themes is documented.
- No repository files outside this package's allowlisted additions change.
- No credentials, test reports, dependency directories or build outputs are included in the release package payload.
