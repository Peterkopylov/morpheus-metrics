BEGIN;

CREATE TABLE IF NOT EXISTS raw_amocrm_pipeline_statuses (
    pipeline_id BIGINT NOT NULL,
    pipeline_name TEXT,
    status_id BIGINT NOT NULL,
    status_name TEXT NOT NULL,
    sort_order INTEGER,
    status_type INTEGER,
    is_editable BOOLEAN,
    color TEXT,
    raw_json JSONB NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (pipeline_id, status_id)
);

CREATE TABLE IF NOT EXISTS raw_amocrm_leads (
    lead_id BIGINT PRIMARY KEY,
    pipeline_id BIGINT NOT NULL,
    status_id BIGINT NOT NULL,
    name TEXT,
    price NUMERIC(18, 2),
    responsible_user_id BIGINT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    raw_json JSONB NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_amocrm_leads_pipeline_created
    ON raw_amocrm_leads (pipeline_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_amocrm_leads_pipeline_updated
    ON raw_amocrm_leads (pipeline_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_amocrm_leads_status
    ON raw_amocrm_leads (pipeline_id, status_id);

CREATE TABLE IF NOT EXISTS raw_amocrm_lead_status_events (
    event_id TEXT PRIMARY KEY,
    lead_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    created_by BIGINT,
    account_id BIGINT,
    pipeline_before_id BIGINT,
    status_before_id BIGINT,
    pipeline_after_id BIGINT,
    status_after_id BIGINT,
    value_before_json JSONB,
    value_after_json JSONB,
    raw_json JSONB NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_amocrm_status_events_lead_created
    ON raw_amocrm_lead_status_events (lead_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_amocrm_status_events_pipeline_after_created
    ON raw_amocrm_lead_status_events (pipeline_after_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_amocrm_status_events_status_after_created
    ON raw_amocrm_lead_status_events (status_after_id, created_at DESC);

COMMIT;
