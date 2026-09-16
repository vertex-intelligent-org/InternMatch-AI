# InternMatch AI — RevenueCat Shipaton 2026 Submission

> **Competition:** RevenueCat Shipaton 2026 — Standard Track
> **Track:** Standard Track
> **Repository:** InternMatch AI

---

## Elevator Pitch

InternMatch AI transforms the overwhelming and opaque student internship search into a transparent, personalized, and AI-accelerated journey. By pairing deep semantic matching with automated CV parsing, actionable skill-gap analysis ("Why You Match"), and tailored cover letter generation, InternMatch AI empowers students to find roles they genuinely fit and submit standout applications—complemented by a native RevenueCat-powered subscription experience for candidate tier management.

---

## The Problem

1. **Fragmented Discovery:** Students spend hours scouring disparate job boards with keyword searches that miss transferable skills.
2. **Opaque Qualification Fit:** Job descriptions list laundry lists of requirements without clarifying how well a student's actual background matches.
3. **Application Fatigue:** Crafting tailored cover letters for dozens of applications is time-consuming, leading to generic, low-conversion submissions.
4. **No Actionable Feedback:** When students lack specific skills, they receive zero guidance on what to learn to become competitive.

---

## The Solution

InternMatch AI provides an intelligent, end-to-end candidate copilot:
- **Intelligent Profile & CV Parsing:** Students upload their CV (PDF/DOCX) which is parsed in the background to automatically populate education, experience, and structured skill vectors.
- **Hybrid Vector & Skill Matching:** Combines exact/fuzzy skill overlap with pgvector semantic similarity to compute truthful match compatibility percentages.
- **"Why You Match" Intelligence:** Breaks down exactly which candidate skills match the role, identifies missing requirements, and suggests concrete learning recommendations.
- **AI Cover Letter Drafting:** Generates job-tailored, tone-customized application drafts that emphasize candidate strengths while allowing full human review and editing.
- **Application Lifecycle Tracking:** Organizes saved opportunities and tracks application stages from Saved to Applied, Interviewing, and Accepted.

---

## Core Implemented Functionality

- [x] **Supabase Authentication:** Secure signup, sign-in, email confirmation, and session management.
- [x] **Onboarding & Profile:** Candidate profile management, headline, avatar, education, experience, and project portfolios.
- [x] **CV Upload & Background Parsing:** Asynchronous CV processing worker extracting structured career data.
- [x] **Internship Catalog & Search:** Filterable internship directory with keyword, location, and work-type search.
- [x] **Saved Internships:** One-tap bookmarking and persistent management.
- [x] **Hybrid Match Scoring:** Automated match ranking with real-time vector and skill overlap scoring.
- [x] **Skill Gap Analysis:** Interactive explanation modals breaking down match strengths and missing competencies.
- [x] **AI Cover Letter Generation:** Context-aware cover letter draft generator powered by Gemini AI.
- [x] **Application Tracker:** Interactive timeline tracking application status progression.
- [x] **RevenueCat Monetization Integration:** Pro Student candidate tier with Test Store in-app purchase flow and entitlement synchronization.
- [x] **Multilingual UI:** Full internationalization in English (`en`), Turkish (`tr`), and Arabic (`ar`) with RTL support.

---

## RevenueCat Integration Architecture

InternMatch AI implements a native RevenueCat monetization architecture:

1. **Native SDK Integration:** Integrated using `react-native-purchases` (v10.7.2) within an Expo SDK 54 Android development client.
2. **Canonical Contract:**
   - **Entitlement:** `pro_student`
   - **Offering:** `default`
   - **Monthly Package:** `$rc_monthly`
   - **Product:** `internmatch_pro_student_monthly`
3. **Zero Local Trust Authority:** Subscription status is derived solely from RevenueCat-provided `CustomerInfo.entitlements.active['pro_student']`. No local flags or unverified AsyncStorage values dictate subscription status.
4. **Identity Synchronization:** RevenueCat App User ID is strictly bound to the authenticated Supabase user UUID (`session.user.id`). Identity transitions are guarded with generation counters to prevent cross-user entitlement leaks.
5. **Dynamic Localization & Pricing:** Store package pricing is resolved dynamically from RevenueCat at runtime (`pkg.product.priceString`), supporting multi-currency and regional pricing without hardcoded strings.
6. **Graceful Error & Cancellation Handling:** Differentiates between user cancellations (`PURCHASE_CANCELLED_ERROR`) and actual store failures to maintain seamless UX without intrusive error popups.
7. **Test Store Sandbox Workflow:** Fast, seamless in-app purchase demonstration without live merchant or console billing dependencies.

---

## Technical Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Mobile Client                        │
│          React Native 0.81.5 / Expo SDK 54              │
│       RevenueCat SDK 10.7.2  •  Supabase Auth JS        │
└────────────┬───────────────────────────────┬────────────┘
             │ Bearer JWT                    │ SDK Sync
             v                               v
┌─────────────────────────┐     ┌─────────────────────────┐
│     FastAPI Gateway     │     │    RevenueCat Engine    │
│  REST API / Auth Verify │     │ Test Store / Entitlement│
└────────────┬────────────┘     └─────────────────────────┘
             │
      ┌──────┴──────────────────────┐
      ▼                             ▼
┌──────────────────────────┐  ┌───────────────────────────┐
│ PostgreSQL + pgvector │  │     Redis + RQ Worker     │
│ Supabase DB & Storage    │  │ CV Parsing & AI Matching  │
└──────────────────────────┘  └───────────────────────────┘
```

---

## Current Standard Track Release Position

InternMatch AI is being prepared as a live Standard Track submission rather than relying on a student-track publication exemption.

The final submission path includes:

- publicly distributed iOS and Android builds;
- RevenueCat production/store purchase validation in addition to sandbox testing;
- candidate, employer, and Admin Trust Console workflows;
- employer organization verification and separate compliance evidence review;
- mandatory opportunity moderation before public publication;
- account deletion, legal/privacy surfaces, and operational security controls;
- live product infrastructure at `internmatch.college` and `api.internmatch.college`.

Earlier Test Store and sandbox results remain part of the engineering evidence, but they are not presented as substitutes for the final public-store release.

## Why InternMatch AI

InternMatch AI was conceived and developed by a collaborative two-person student team, **Mohamad Barakat** and **Selanur Yurdakul**. Both are Software / Computer Engineering students at Üsküdar University and members of AISS (Artificial Intelligence and Intelligent Systems Club), where Mohamad serves as President and Selanur as Vice President.

Selanur originated the product vision, and Mohamad established the technical architecture and engineering foundation. Together, they designed, implemented, and refined a complete student career copilot that solves the fundamental fit problem: helping students understand *why* they match, identifying skill gaps before applying, and providing practical AI tools that turn aspirations into interview invitations.

*Independent Project Note:* InternMatch AI is an independent student entry created directly by the authors for the RevenueCat Shipaton 2026 standard track. It is not an official AISS Club or Üsküdar University project, and neither institution provided financial, technical, development, or material support.

---

## Demo Video Storyboard (< 2 Minutes)

* **Target Duration:** 1 minute 55 seconds
* **Target Aspect Ratio:** 16:9 (1080p / 4K)

| Timestamp | Scene | Audio / Voiceover Narrative | On-Screen Action |
|---|---|---|---|
| **0:00 – 0:10** | **Hook & Problem** | *"Finding the right internship shouldn't feel like sending resumes into a black hole. Meet InternMatch AI."* | Rapid montage: app logo, student profile, and internship match score orb. |
| **0:10 – 0:30** | **Profile & CV Enrichment** | *"Students start by uploading their CV. Our background parser automatically extracts skills and experience into a rich career profile."* | Show candidate profile, tap CV Upload, PDF parses, and extracted skills appear on profile. |
| **0:30 – 0:50** | **Matching & Why You Match** | *"InternMatch calculates personalized compatibility scores and shows exactly why you match—highlighting key strengths and missing skills."* | Open Matchups tab, tap 94% match, explore **Why You Match** skill alignment and recommendations. |
| **0:50 – 1:10** | **AI Cover Letter & Tracking** | *"Generate a customized, role-specific cover letter draft in seconds, edit it, and track your application status from Applied through Interviewing to Accepted."* | Tap Draft Application, select tone, generate letter, view application in Application Tracker. |
| **1:10 – 1:30** | **Localization & Interface** | *"Built for global students with seamless switching between English, Turkish, and Arabic with full RTL support."* | Switch language in settings to Turkish and Arabic, demonstrating fluid RTL layout. |
| **1:30 – 1:50** | **RevenueCat Pro Subscription** | *"With RevenueCat, candidates upgrade to Pro Student with one tap to manage their premium candidate subscription."* | Open Plans screen, show dynamic Test Store price, tap Upgrade, complete Test Store transaction, see Pro Student tier activate. |
| **1:50 – 1:55** | **Conclusion & Call to Action** | *"InternMatch AI: smarter matching, better applications, faster careers. Built for RevenueCat Shipaton 2026."* | Closing title screen with GitHub link and team credits. |

---

## Submission Deliverables

1. **Public Repository:**
   - Canonical open-source repository: [https://github.com/AISSCLUB/InternMatch-AI](https://github.com/AISSCLUB/InternMatch-AI)
   - Licensed under the OSI-approved **MIT License**.

2. **Demonstration Video:**
   - Designed as a concise walkthrough under 2 minutes (1:55 storyboard).
   - Covers the principal candidate experience: CV upload, profile enrichment, hybrid matching, Why You Match explanations, AI cover letter drafting, multilingual RTL switching, and native RevenueCat Test Store purchase / Pro Student entitlement activation.

3. **High-Resolution Application Icon:**
   - 1024×1024 PNG asset conforming to hackathon submission standards without an alpha channel.

4. **Mobile Screenshots:**
   - High-resolution screen captures showcasing primary user flows including Matchups, Why You Match skill analysis, AI application workflow, and RevenueCat subscription plans.

5. **Student Eligibility Verification:**
   - Developed by student creators Mohamad Barakat and Selanur Yurdakul, both Software / Computer Engineering students at Üsküdar University.
   - The current submission is prepared for the Shipaton 2026 Standard Track and follows the public-store release path described above.

6. **GitHub Release Baseline:**
   - The final GitHub release serves as the stable, reproducible Shipaton 2026 submission milestone.
