
CREATE TABLE user_notifications (
    id UUID PRIMARY KEY,
    recipient_user_id UUID NOT NULL,
    event_type VARCHAR NOT NULL,
    entity_type VARCHAR NULL,
    entity_id UUID NULL,
    data_json TEXT NOT NULL DEFAULT '{}',
    dedupe_key VARCHAR NULL UNIQUE,
    read_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_user_notifications_recipient_user_id
    ON user_notifications (recipient_user_id);

CREATE INDEX ix_user_notifications_event_type
    ON user_notifications (event_type);

CREATE INDEX ix_user_notifications_entity_id
    ON user_notifications (entity_id);

CREATE INDEX ix_user_notifications_created_at
    ON user_notifications (created_at);

CREATE TABLE push_devices (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    expo_push_token VARCHAR NOT NULL UNIQUE,
    platform VARCHAR NOT NULL,
    locale VARCHAR NOT NULL DEFAULT 'en',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_push_devices_user_id
    ON push_devices (user_id);
