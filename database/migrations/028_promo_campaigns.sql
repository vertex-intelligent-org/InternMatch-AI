-- ============================================================
-- InternMatch AI
-- Migration 028 - Secure one-time promotional access
-- ============================================================
--
-- IMPORTANT:
--   * This migration is intentionally NOT idempotent.
--   * Apply exactly once through the controlled production process.
--   * Never rerun migration 027.
--   * Plaintext promo codes are NEVER persisted.
-- ============================================================

CREATE TABLE public.promo_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    audience TEXT NOT NULL
        CHECK (audience IN ('student', 'employer')),

    code_digest VARCHAR(64) NOT NULL UNIQUE,
    code_hint VARCHAR(32) NOT NULL,

    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'published', 'retired')),

    duration_days INTEGER NOT NULL DEFAULT 7
        CHECK (duration_days = 7),

    created_by_admin_user_id UUID NOT NULL,
    retired_by_admin_user_id UUID NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retired_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX uq_promo_campaigns_published_audience
    ON public.promo_campaigns (audience)
    WHERE status = 'published';

CREATE INDEX ix_promo_campaigns_audience_created
    ON public.promo_campaigns (
        audience,
        created_at DESC
    );


CREATE TABLE public.promo_redemptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    campaign_id UUID NOT NULL
        REFERENCES public.promo_campaigns(id)
        ON DELETE RESTRICT,

    user_id UUID NOT NULL,

    audience TEXT NOT NULL
        CHECK (audience IN ('student', 'employer')),

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'redeemed', 'failed')),

    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    access_started_at TIMESTAMPTZ NULL,
    access_expires_at TIMESTAMPTZ NULL,

    provider_subscription_id VARCHAR(255) NULL,
    last_error_code VARCHAR(64) NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_promo_redemptions_user_audience
        UNIQUE (user_id, audience),

    CONSTRAINT ck_promo_redeemed_has_access_window
        CHECK (
            status <> 'redeemed'
            OR (
                access_started_at IS NOT NULL
                AND access_expires_at IS NOT NULL
                AND access_expires_at > access_started_at
            )
        )
);

CREATE INDEX ix_promo_redemptions_campaign
    ON public.promo_redemptions (campaign_id);

CREATE INDEX ix_promo_redemptions_user
    ON public.promo_redemptions (user_id);

-- These tables are backend-only.
-- Mobile/web authenticated clients must never directly read campaign
-- digests or redemption internals through PostgREST.
ALTER TABLE public.promo_campaigns
    ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.promo_redemptions
    ENABLE ROW LEVEL SECURITY;

REVOKE ALL
    ON TABLE public.promo_campaigns
    FROM anon, authenticated;

REVOKE ALL
    ON TABLE public.promo_redemptions
    FROM anon, authenticated;
