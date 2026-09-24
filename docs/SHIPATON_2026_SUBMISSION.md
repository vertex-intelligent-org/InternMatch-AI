# InternMatch AI — RevenueCat Shipaton 2026 Submission

**Competition:** RevenueCat Shipaton 2026
**Entry path:** Standard Track / main competition release path
**Documentation checkpoint:** 2026-09-24
**Release source:** `707601d93294c891d53b900d01c644200f27292b`
**Canonical repository:** https://github.com/vertex-intelligent-org/InternMatch-AI

> **Submission-status note:** This document is the current product/submission narrative, not proof that store eligibility has already been satisfied. At this checkpoint, iOS `1.0.0` Build 9 is associated with App Review and Build 10 has been uploaded to App Store Connect / TestFlight for validation. TestFlight is not a public App Store release. Android public-store availability is not asserted here. Final Standard Track eligibility must be checked against the live store listing and RevenueCat's current Shipaton requirements before submission.

---

## Elevator Pitch

**InternMatch AI** turns internship search into an explainable, two-sided workflow for students and employers. Students build a structured profile, enrich it from a private CV, receive deterministic hybrid match scores, understand *why* they match, identify skill gaps, prepare applications with AI assistance, and track interviews and outcomes. Employers operate through a verified organization workspace with moderated internship publishing, applicant/interview tooling, and RevenueCat-backed Free/Pro product policy. A separate Admin Trust & Safety Console keeps organization verification, compliance-evidence review, and listing moderation under human administrative control.

---

## The Problem

### Students

1. **Fragmented discovery:** internship search often depends on broad keyword browsing rather than the student's actual skills and profile context.
2. **Opaque fit:** job descriptions rarely explain how a student's strengths and gaps map to a role.
3. **Application fatigue:** repeatedly preparing tailored application material is slow and repetitive.
4. **Little actionable feedback:** students may know that they are missing requirements without knowing which gaps to address.

### Employers

1. **Unstructured screening:** candidate information, CV evidence, interviews, and application state can become disconnected.
2. **Trust requirements:** organization identity, compliance evidence, and opportunity publication are different questions and should not be collapsed into one approval flag.
3. **Human decision support:** AI can summarize grounded candidate context, but final hiring decisions need to remain human-led.

---

## The Solution

InternMatch AI combines a student career copilot, an employer recruiting workflow, and an administrative trust layer.

### Student experience

- **Structured profile + CV enrichment:** private PDF/DOCX CV upload is processed asynchronously to extract structured career data.
- **Hybrid matching:** exact/fuzzy skill overlap, semantic similarity through `pgvector`, and supported profile preferences contribute to deterministic computed match scores.
- **Why You Match:** a dedicated screen presents matching skills, missing skills, and generated guidance while keeping the numeric score separate from generative AI.
- **AI-assisted applications:** server-side Gemini workflows help draft role-specific application/cover-letter content for user review and editing.
- **Interview preparation:** eligible interview workflows can generate structured preparation material.
- **Application tracking:** state is persisted across `saved`, `applied`, `interviewing`, `accepted`, and `rejected`.
- **Notifications:** durable in-app notifications are complemented by Expo push-device registration/delivery.
- **Localization:** English, Turkish, and Arabic UI with RTL support for Arabic.

### Employer experience

- **Organization workspace:** employer identity/business and representative information is maintained under an employer role.
- **Organization verification:** employers submit the organization for human Admin review.
- **Separate compliance evidence:** jurisdiction/scope claims and private evidence use a distinct review workflow; approval is not legal certification.
- **Moderated opportunity publishing:** employer-created/edited opportunities enter `under_review` and remain non-public until Admin approval.
- **Request-changes loop:** Admin feedback returns a listing to `draft`; the owner edits the same prefilled listing and resubmits to `under_review`.
- **Applicant/interview workflows:** employers can review owned-listing applicants, access authorized candidate context/CV, schedule interviews, and make valid status transitions.
- **Employer AI/product tools:** candidate insight uses a separate AI quota; Employer Pro adds interview kits, shortlist comparison, AI-assisted internship-description drafting, pipeline analytics, and multiple published listings.

### Admin Trust & Safety Console

- backend-enforced Admin authorization
- organization review
- compliance evidence review
- listing moderation / approval / request changes
- user directory/search with student/employer context
- administrative audit history for verification/compliance events
- Admin-managed opportunity/applicant workflows where applicable

---

## Core Implemented Functionality

- [x] Supabase email/password authentication, confirmation/recovery, and session handling.
- [x] Candidate Google OAuth and native Sign in with Apple on iOS.
- [x] Role-aware canonical InternMatch account provisioning (`intern` / `employer`).
- [x] Structured candidate profile, skills, education, experience, projects, preferences, and avatar.
- [x] Private CV upload with asynchronous extraction and safe replacement/cancellation flows.
- [x] Internship catalog with current mobile work-type filtering and saved internships.
- [x] Exact/fuzzy/semantic hybrid matching with persisted computed scores.
- [x] Why You Match explanation and skill-gap guidance.
- [x] AI-assisted application/cover-letter generation.
- [x] Interview preparation and application lifecycle tracking.
- [x] Durable notifications + Expo push-device registration/delivery.
- [x] English, Turkish, and Arabic localization with RTL.
- [x] Employer organization workspace and Admin verification.
- [x] Separate employer compliance-claim/evidence workflow with private storage.
- [x] Mandatory employer listing moderation before public publication.
- [x] Employer applicant, CV, interview, and status workflows.
- [x] Employer Free/Pro backend product policy and Employer AI quota enforcement.
- [x] Student + Employer RevenueCat contracts with backend subscription state, reconciliation, and lifecycle webhook handling.
- [x] Account deletion with recent reauthentication and Apple authorization revocation boundary when applicable.

---

## Matching & AI Design

InternMatch AI intentionally separates **computed ranking data** from **generated explanation**.

The matching engine combines:

- normalized exact skill matching
- fuzzy skill matching using server configuration
- semantic similarity from embeddings stored in PostgreSQL with `pgvector`
- supported candidate preference contribution

The resulting match score is computed by deterministic application logic. Gemini is used for bounded server-side workflows such as CV interpretation, match explanation, application drafting, interview preparation, and employer AI assistance. Generated text does not autonomously decide whether a candidate should be hired.

This gives the product an explainability boundary: the user can see the score, matching/missing skills, and a generated explanation without treating an LLM response as the numeric scoring authority.

---

## Trust & Moderation Design

InternMatch AI keeps three trust decisions separate:

1. **Organization verification** — is the employer organization accepted by the platform's identity/business review workflow?
2. **Compliance evidence review** — was evidence for a specific claim, jurisdiction, and scope reviewed and administratively decided?
3. **Opportunity moderation** — may this specific employer-generated listing become candidate-visible?

Neither organization verification nor compliance approval automatically publishes an opportunity.

Employer listing lifecycle:

```text
Employer create/edit
      |
      v
 under_review  ---- Admin approve ----> published
      |
      +---- Admin request changes ----> draft
                                         |
                                         +--> owner-visible feedback
                                         +--> same listing prefilled
                                         +--> employer edits/resubmits
                                         v
                                    under_review
```

`employer_visible_feedback` is owner-only and is not part of the public internship response. Previous review feedback is cleared on successful employer resubmission.

---

## RevenueCat Integration Architecture

InternMatch AI uses `react-native-purchases` **10.7.2** and implements separate Student and Employer monetization contracts.

| Audience | Entitlement | Offering | Package | Canonical Product |
|---|---|---|---|---|
| Student | `pro_student` | `default` | `$rc_monthly` | `internmatch_pro_student_monthly` |
| Employer | `pro_employer` | `employer_default` | `$rc_monthly` | `internmatch_pro_employer_monthly` |

### Mobile layer

- RevenueCat is identified with the authenticated Supabase user identity.
- Visible package/pricing information is resolved from RevenueCat/store metadata instead of a hard-coded subscription price.
- Development can use a RevenueCat Test Store public SDK key.
- Release environments use platform-specific iOS/Android public SDK keys.
- The custom mobile promo-code field that directly unlocked Pro was removed from the current store application.

### Backend authority

The backend exposes:

- `GET /api/v1/me/subscription`
- `GET /api/v1/me/ai-usage`
- `POST /api/v1/me/subscription/reconcile`
- `POST /api/v1/webhooks/revenuecat`

The server persists provider-derived subscription state, can reconcile directly with RevenueCat using a server-only credential, and consumes RevenueCat lifecycle events. Configured Bearer webhook authentication is required; HMAC signature/timestamp verification additionally applies when the webhook signing secret is configured.

### Employer product policy

**Employer Free** supports one published internship and candidate insight; candidate insight remains subject to its separately enforced AI quota.

**Employer Pro** supports multiple published listings and enables interview kit, shortlist comparison, internship-description assistant, and pipeline analytics. AI quotas remain separately enforced even when the plan enables a feature.

---

## Technical Architecture

```text
┌──────────────────────────┐        ┌──────────────────────────┐
│ Expo / React Native      │        │ Next.js Admin Console   │
│ Student + Employer       │        │ Trust & Safety          │
└────────────┬─────────────┘        └────────────┬─────────────┘
             │ Supabase auth / Bearer JWT        │
             └────────────────┬──────────────────┘
                              v
                   ┌──────────────────────┐
                   │ FastAPI /api/v1     │
                   │ auth + policy gates │
                   └──────┬───────┬──────┘
                          │       │
              ┌───────────┘       └────────────┐
              v                                v
  ┌──────────────────────────┐      ┌──────────────────────┐
  │ Supabase PostgreSQL      │      │ Redis + RQ Worker    │
  │ Auth + pgvector + Storage│      │ async AI workflows   │
  └──────────────────────────┘      └──────────┬───────────┘
                                               v
                                      ┌────────────────────┐
                                      │ Google Gemini      │
                                      └────────────────────┘

Mobile ── RevenueCat public SDK ──> RevenueCat
FastAPI <── server reconciliation / authenticated webhook ── RevenueCat
```

Production intentionally disables Swagger, ReDoc, and OpenAPI JSON. Operational health uses `/health` for process liveness and `/api/v1/health` for database/Redis/RQ readiness.

---

## Privacy & Security Boundaries

- Protected identity comes from validated Supabase Bearer JWTs.
- Account role is persisted server-side and is not an arbitrary client-editable role flag.
- Employer access is scoped to employer-owned resources.
- Admin authority is checked server-side through `ADMIN_USER_IDS`.
- CVs, avatars, and compliance evidence are private storage objects brokered through authenticated API boundaries.
- Raw storage paths/service-role credentials are not client authorization tokens.
- Candidate saved drafts are not recruiter-visible submissions.
- Account deletion requires recent reauthentication and coordinates data/storage/subscription cleanup.
- No claim in this submission should be read as GDPR certification, legal certification, unbiased AI, or guaranteed hiring outcomes.

---

## Current Standard Track Release Position

RevenueCat's current Shipaton 2026 submission guide states that main-competition entries must be fully published in a qualifying app store, available in the United States, and use RevenueCat to power at least one qualifying purchase (or the qualifying RevenueCat Ads alternative). TestFlight/testing tracks do **not** count as the public release.

Official submission guide: https://www.revenuecat.com/blog/engineering/how-to-submit-your-app-for-shipaton

At the **2026-09-24** checkpoint:

| Item | Verified checkpoint state |
|---|---|
| Source release | Commit `707601d93294c891d53b900d01c644200f27292b` |
| iOS app version | `1.0.0` |
| iOS Build 9 | Associated with App Review |
| iOS Build 10 | Uploaded to App Store Connect / TestFlight for validation |
| Public App Store release | **Not asserted at this checkpoint** |
| Public Google Play release | **Not asserted at this checkpoint** |
| RevenueCat SDK | Integrated for Student + Employer product contracts |
| Backend RevenueCat authority | Subscription state, reconciliation, webhook implemented |

Therefore this document must not be used to claim that Standard Track public-store eligibility was already satisfied on September 24. Verify the final live store URL and purchase availability before the final submission is sent.

RevenueCat's current submission guide lists the deadline as **September 30, 2026 at 11:45 pm PDT**.

---

## Why InternMatch AI

InternMatch AI differentiates itself through the combination of:

- explainable hybrid candidate matching instead of opaque LLM-only scoring
- a complete student journey from profile/CV to matching, application, interview, and outcome tracking
- an implemented employer recruiting workflow integrated with trust and monetization policy
- human-administered organization, compliance, and listing trust boundaries
- backend-controlled Student and Employer monetization policy
- multilingual English/Turkish/Arabic product support
- privacy-preserving document access and account-deletion controls

The product is designed so AI accelerates preparation and decision support while identity, publication, product entitlement, and hiring-state authority stay in deterministic/server-controlled boundaries.

---

## Team

InternMatch AI is an independent two-person student project by **Mohamad Barakat** and **Selanur Yurdakul**, Software / Computer Engineering students at Üsküdar University and members of AISS (Artificial Intelligence and Intelligent Systems Club).

Selanur originated the product vision, and Mohamad established the technical architecture and engineering foundation. Together, they designed, implemented, tested, and refined the product.

InternMatch AI is submitted as an independent student project, not as an official Üsküdar University or AISS Club product.

---

## Demo Video Storyboard (< 2 Minutes)

The final video should show only behavior that works in the submitted build and should use the actual final store/RevenueCat state rather than presenting Test Store as public-release proof.

| Time | Scene | What to show |
|---|---|---|
| `0:00–0:10` | Problem / hook | InternMatch AI, student fit problem, quick product overview |
| `0:10–0:32` | Profile + CV | Candidate profile, private CV upload, structured enrichment |
| `0:32–0:52` | Matching | Match score + **Why You Match** strengths/missing skills/guidance |
| `0:52–1:08` | Application journey | AI-assisted draft, human review/edit, application tracker/interview state |
| `1:08–1:28` | Employer + moderation | Employer opportunity submission -> `under_review`; Admin approve/request-changes; owner feedback/resubmit |
| `1:28–1:40` | Trust layer | Organization verification vs separate compliance-evidence review |
| `1:40–1:52` | RevenueCat | Actual final Student/Employer subscription surface and a qualifying purchase/access flow available in the shipped app |
| `1:52–1:58` | Global UX + close | English/Turkish/Arabic + RTL, repo/product link, team names |

Do not show a custom InternMatch promo-code field; that mobile unlock mechanism was removed. If the final judging requirement uses a free trial or store/platform promo code, configure and document that through the actual store-compatible mechanism.

---

## Submission Deliverables Checklist

### Product / release

- [ ] Verify at least one qualifying **public** store listing is live and available in the United States before final Standard Track submission.
- [ ] Verify the public build works as shown in the final video.
- [ ] Verify RevenueCat powers the qualifying purchase in that public build.
- [ ] Provide the final live store URL in the submission.
- [ ] Provide judge access to paid functionality using the mechanism required by the current official submission guide (for example, free trial or store-compatible promo access).

### Submission assets

- [x] Public source repository: https://github.com/vertex-intelligent-org/InternMatch-AI
- [x] MIT-licensed repository.
- [ ] Public YouTube or Vimeo demo video with the essential product demo contained within the first 2 minutes.
- [ ] Final `1024 × 1024` application icon.
- [ ] At least one `1179 × 2556` application screenshot without a device frame, matching the released product.
- [ ] RevenueCat project ID.
- [ ] Final live store URL and any judge-access instructions after store release is verified.
- [ ] Submission text and testing instructions are in English or include an English translation.

### Technical evidence

- [x] Student + Employer RevenueCat contracts in source.
- [x] Backend RevenueCat subscription/reconciliation/webhook integration.
- [x] Hybrid matching and AI workflows.
- [x] Employer organization verification + separate compliance review.
- [x] Mandatory employer listing moderation.
- [x] Admin Trust & Safety Console.
- [x] Development/test documentation and reproducible source baseline.

---

## Related Judge Documentation

- [Judge Reproduction Runbook](JUDGE_RUNBOOK.md)
- [Architecture](ARCHITECTURE.md)
- [API Contract](API_CONTRACT.md)
- [Security](SECURITY.md)
- [Database](DATABASE.md)
- [Development](DEVELOPMENT.md)
