-- Metric catalog layer for the new normalized metric model.
--
-- Design goals:
-- 1. Store the metric catalog separately from observed facts.
-- 2. Keep collection rules ("what may exist") separate from facts ("what was observed").
-- 3. Store dictionary scopes explicitly so "b2c_show_names" / "marketing_channel_names"
--    are data, not magic strings in code.
-- 4. Never require zero-value fact rows for combinations that did not appear.

BEGIN;

-- 1. Canonical metric catalog
CREATE TABLE IF NOT EXISTS metric_catalogue (
    metric_id BIGSERIAL PRIMARY KEY,
    metric_key TEXT NOT NULL UNIQUE,
    metric_name TEXT NOT NULL UNIQUE,
    metric_family TEXT NOT NULL,
    value_kind TEXT NOT NULL,
    description TEXT,
    legacy_mapping_status TEXT,
    legacy_groups_covered TEXT,
    legacy_groups_partial TEXT,
    legacy_group_count_covered INTEGER NOT NULL DEFAULT 0,
    legacy_group_count_partial INTEGER NOT NULL DEFAULT 0,
    legacy_notes_summary TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT metric_catalogue_value_kind_chk
        CHECK (value_kind IN (
            'count',
            'currency',
            'ratio',
            'score',
            'score_or_count',
            'ratio_or_count',
            'text'
        ))
);

COMMENT ON TABLE metric_catalogue IS
'Canonical list of business metrics. One row per metric concept.';

-- 2. Scope dictionaries ("b2c_show_names", "b2c_partner_names", etc.)
CREATE TABLE IF NOT EXISTS metric_scope_dictionary (
    dictionary_id BIGSERIAL PRIMARY KEY,
    dictionary_group TEXT NOT NULL,
    dictionary_key TEXT NOT NULL UNIQUE,
    description TEXT,
    is_expandable BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE metric_scope_dictionary IS
'Named scope dictionaries used by collection rules. Example: b2c_show_names.';

CREATE TABLE IF NOT EXISTS metric_scope_dictionary_value (
    dictionary_value_id BIGSERIAL PRIMARY KEY,
    dictionary_id BIGINT NOT NULL REFERENCES metric_scope_dictionary(dictionary_id) ON DELETE CASCADE,
    value_key TEXT NOT NULL,
    value_label TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (dictionary_id, value_key)
);

COMMENT ON TABLE metric_scope_dictionary_value IS
'Actual values inside a named scope dictionary. Example: Ответ Гиппократа inside b2c_show_names.';

CREATE INDEX IF NOT EXISTS idx_metric_scope_dictionary_value_dictionary
    ON metric_scope_dictionary_value(dictionary_id, is_active, sort_order);

-- 3. Collection rules: which combinations are valid and from which source
CREATE TABLE IF NOT EXISTS metric_collection_rule (
    rule_id BIGSERIAL PRIMARY KEY,
    metric_id BIGINT NOT NULL REFERENCES metric_catalogue(metric_id) ON DELETE CASCADE,
    business_unit_scope TEXT NOT NULL,
    show_scope TEXT,
    partner_scope TEXT,
    channel_scope TEXT,
    show_scope_norm TEXT GENERATED ALWAYS AS (COALESCE(show_scope, '')) STORED,
    partner_scope_norm TEXT GENERATED ALWAYS AS (COALESCE(partner_scope, '')) STORED,
    channel_scope_norm TEXT GENERATED ALWAYS AS (COALESCE(channel_scope, '')) STORED,
    source_system TEXT,
    source_system_norm TEXT GENERATED ALWAYS AS (COALESCE(source_system, '')) STORED,
    source_label TEXT,
    minimal_frequency TEXT,
    availability_status TEXT NOT NULL DEFAULT 'available',
    credibility TEXT,
    source_row_ref TEXT,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT metric_collection_rule_frequency_chk
        CHECK (minimal_frequency IN ('', 'day', 'week', 'month', 'quarter', 'year')),
    CONSTRAINT metric_collection_rule_status_chk
        CHECK (availability_status IN (
            'available',
            'not_available_yet',
            'manual_only',
            'derived',
            'unspecified'
        )),
    CONSTRAINT metric_collection_rule_unique
        UNIQUE (
            metric_id,
            business_unit_scope,
            show_scope_norm,
            partner_scope_norm,
            channel_scope_norm,
            source_system_norm
        )
);

COMMENT ON TABLE metric_collection_rule IS
'Catalog of valid metric/source/scope combinations. This is a rules table, not a fact table.';

CREATE INDEX IF NOT EXISTS idx_metric_collection_rule_metric
    ON metric_collection_rule(metric_id, is_active);

CREATE INDEX IF NOT EXISTS idx_metric_collection_rule_source
    ON metric_collection_rule(source_system, minimal_frequency, availability_status);

-- 4. Observed facts: only store rows that actually exist in source data
CREATE TABLE IF NOT EXISTS fact_metric_observation (
    observation_id BIGSERIAL PRIMARY KEY,
    metric_id BIGINT NOT NULL REFERENCES metric_catalogue(metric_id),
    rule_id BIGINT REFERENCES metric_collection_rule(rule_id),
    source_system TEXT NOT NULL,
    source_record_key TEXT,
    source_run_id TEXT,
    source_cell_a1 TEXT,
    source_cell_url TEXT,
    business_unit TEXT NOT NULL,
    show_name TEXT,
    partner_name TEXT,
    channel_name TEXT,
    show_name_norm TEXT GENERATED ALWAYS AS (COALESCE(show_name, '')) STORED,
    partner_name_norm TEXT GENERATED ALWAYS AS (COALESCE(partner_name, '')) STORED,
    channel_name_norm TEXT GENERATED ALWAYS AS (COALESCE(channel_name, '')) STORED,
    source_record_key_norm TEXT GENERATED ALWAYS AS (COALESCE(source_record_key, '')) STORED,
    period_granularity TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    value_numeric NUMERIC(18, 6),
    value_text TEXT,
    value_raw TEXT,
    currency_code TEXT,
    is_estimated BOOLEAN NOT NULL DEFAULT FALSE,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB,
    CONSTRAINT fact_metric_observation_granularity_chk
        CHECK (period_granularity IN ('day', 'week', 'month', 'quarter', 'year')),
    CONSTRAINT fact_metric_observation_value_chk
        CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL OR value_raw IS NOT NULL),
    CONSTRAINT fact_metric_observation_unique
        UNIQUE (
            metric_id,
            source_system,
            business_unit,
            show_name_norm,
            partner_name_norm,
            channel_name_norm,
            period_granularity,
            period_start,
            period_end,
            source_record_key_norm
        )
);

COMMENT ON TABLE fact_metric_observation IS
'Observed metric values only. No synthetic zero rows for missing combinations.';

CREATE INDEX IF NOT EXISTS idx_fact_metric_observation_metric_period
    ON fact_metric_observation(metric_id, period_granularity, period_start DESC);

CREATE INDEX IF NOT EXISTS idx_fact_metric_observation_scope
    ON fact_metric_observation(business_unit, show_name, partner_name, channel_name);

CREATE INDEX IF NOT EXISTS idx_fact_metric_observation_source
    ON fact_metric_observation(source_system, loaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_fact_metric_observation_payload_gin
    ON fact_metric_observation USING GIN (payload);

-- 5. Optional mapping table for legacy weekly metrics -> canonical metrics
CREATE TABLE IF NOT EXISTS metric_legacy_mapping (
    legacy_mapping_id BIGSERIAL PRIMARY KEY,
    legacy_group_name TEXT NOT NULL,
    legacy_metric_name TEXT,
    legacy_metric_name_norm TEXT GENERATED ALWAYS AS (COALESCE(legacy_metric_name, '')) STORED,
    metric_id BIGINT NOT NULL REFERENCES metric_catalogue(metric_id) ON DELETE CASCADE,
    mapping_status TEXT NOT NULL DEFAULT 'partial',
    mapping_notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (
        legacy_group_name,
        legacy_metric_name_norm,
        metric_id
    ),
    CONSTRAINT metric_legacy_mapping_status_chk
        CHECK (mapping_status IN ('covered', 'partial', 'not_migrated'))
);

COMMENT ON TABLE metric_legacy_mapping IS
'Explicit bridge from old weekly metric labels/groups into the canonical metric catalog.';

COMMIT;
