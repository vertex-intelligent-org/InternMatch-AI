-- InternMatch AI — SUB-1 RevenueCat Backend Entitlement Foundation
-- Target Engine: Supabase PostgreSQL 15+
--
-- These tables are server-owned. Mobile clients must never write billing
-- or entitlement authority directly.

CREATE TABLE IF NOT EXISTS public.subscription_entitlements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entitlement_id TEXT NOT NULL,
    product_id TEXT,
    status TEXT NOT NULL DEFAULT 'inactive',
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    will_renew BOOLEAN NOT NULL DEFAULT FALSE,
    current_period_started_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    environment TEXT,
    store TEXT,
    original_transaction_id TEXT,
    cancellation_reason TEXT,
    expiration_reason TEXT,
    last_event_id TEXT,
    last_event_type TEXT,
    last_event_timestamp_ms BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_subscription_entitlements_user_entitlement
        UNIQUE (user_id, entitlement_id)
);

CREATE TABLE IF NOT EXISTS public.revenuecat_webhook_events (
    event_id TEXT PRIMARY KEY,
    user_id UUID,
    event_type TEXT NOT NULL,
    event_timestamp_ms BIGINT NOT NULL,
    outcome TEXT NOT NULL DEFAULT 'received',
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_subscription_entitlements_user_id
    ON public.subscription_entitlements(user_id);

CREATE INDEX IF NOT EXISTS idx_subscription_entitlements_active
    ON public.subscription_entitlements(user_id, entitlement_id, is_active);

CREATE INDEX IF NOT EXISTS idx_revenuecat_webhook_events_user_id
    ON public.revenuecat_webhook_events(user_id);

CREATE INDEX IF NOT EXISTS idx_revenuecat_webhook_events_timestamp
    ON public.revenuecat_webhook_events(event_timestamp_ms);

-- Server-owned billing state: deny direct anon/authenticated access.
ALTER TABLE public.subscription_entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.revenuecat_webhook_events ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.subscription_entitlements FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.revenuecat_webhook_events FROM PUBLIC, anon, authenticated;

GRANT ALL ON public.subscription_entitlements TO service_role;
GRANT ALL ON public.revenuecat_webhook_events TO service_role;