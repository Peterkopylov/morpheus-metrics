BEGIN;

CREATE TABLE IF NOT EXISTS calculated_metric_definition (
    definition_id BIGSERIAL PRIMARY KEY,
    calculated_metric_key TEXT NOT NULL,
    calculated_metric_name TEXT NOT NULL,
    period_granularity TEXT NOT NULL,
    business_unit TEXT NOT NULL,
    show_name TEXT,
    partner_name TEXT,
    channel_name TEXT,
    show_name_norm TEXT GENERATED ALWAYS AS (COALESCE(show_name, '')) STORED,
    partner_name_norm TEXT GENERATED ALWAYS AS (COALESCE(partner_name, '')) STORED,
    channel_name_norm TEXT GENERATED ALWAYS AS (COALESCE(channel_name, '')) STORED,
    value_kind TEXT NOT NULL,
    formula_type TEXT NOT NULL,
    numerator_metric_key TEXT,
    denominator_metric_key TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    version TEXT NOT NULL DEFAULT 'v1',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT calculated_metric_definition_granularity_chk
        CHECK (period_granularity IN ('week', 'month', 'quarter', 'year')),
    CONSTRAINT calculated_metric_definition_value_kind_chk
        CHECK (value_kind IN (
            'count',
            'currency',
            'ratio',
            'score',
            'score_or_count',
            'ratio_or_count',
            'text'
        )),
    CONSTRAINT calculated_metric_definition_formula_type_chk
        CHECK (formula_type IN ('ratio_of_sums', 'share_of_partition_total', 'allocate_total_by_partition_share', 'apply_partner_commission_rate')),
    CONSTRAINT calculated_metric_definition_status_chk
        CHECK (status IN ('active', 'pending', 'inactive')),
    CONSTRAINT calculated_metric_definition_unique
        UNIQUE (
            calculated_metric_key,
            period_granularity,
            business_unit,
            show_name_norm,
            partner_name_norm,
            channel_name_norm,
            version
        )
);

COMMENT ON TABLE calculated_metric_definition IS
'Runtime mirror of the canonical calculated metric registry.';

CREATE INDEX IF NOT EXISTS idx_calculated_metric_definition_lookup
    ON calculated_metric_definition(calculated_metric_key, period_granularity, business_unit, status);

ALTER TABLE IF EXISTS calculated_metric_definition
    DROP CONSTRAINT IF EXISTS calculated_metric_definition_formula_type_chk;

ALTER TABLE IF EXISTS calculated_metric_definition
    ADD CONSTRAINT calculated_metric_definition_formula_type_chk
        CHECK (formula_type IN ('ratio_of_sums', 'share_of_partition_total', 'allocate_total_by_partition_share', 'apply_partner_commission_rate'));

CREATE TABLE IF NOT EXISTS calculated_metric_dependency (
    dependency_id BIGSERIAL PRIMARY KEY,
    definition_id BIGINT NOT NULL REFERENCES calculated_metric_definition(definition_id) ON DELETE CASCADE,
    dependency_role TEXT NOT NULL,
    dependency_metric_key TEXT,
    dependency_granularity TEXT NOT NULL,
    dependency_source_system TEXT,
    dependency_show_scope TEXT,
    dependency_partner_scope TEXT,
    dependency_channel_scope TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT calculated_metric_dependency_role_chk
        CHECK (dependency_role IN ('numerator', 'denominator')),
    CONSTRAINT calculated_metric_dependency_granularity_chk
        CHECK (dependency_granularity IN ('week', 'month', 'quarter', 'year')),
    CONSTRAINT calculated_metric_dependency_unique
        UNIQUE (definition_id, dependency_role)
);

COMMENT ON TABLE calculated_metric_dependency IS
'Resolved operational dependency list for each calculated metric definition.';

CREATE INDEX IF NOT EXISTS idx_calculated_metric_dependency_definition
    ON calculated_metric_dependency(definition_id, dependency_role);

CREATE TABLE IF NOT EXISTS calculation_runs (
    run_id TEXT PRIMARY KEY,
    period_granularity TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    trigger_mode TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT calculation_runs_granularity_chk
        CHECK (period_granularity IN ('week', 'month', 'quarter', 'year')),
    CONSTRAINT calculation_runs_status_chk
        CHECK (status IN ('running', 'success', 'partial', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_calculation_runs_started_at
    ON calculation_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS calculation_run_steps (
    run_id TEXT NOT NULL REFERENCES calculation_runs(run_id) ON DELETE CASCADE,
    step_key TEXT NOT NULL,
    definition_id BIGINT REFERENCES calculated_metric_definition(definition_id) ON DELETE SET NULL,
    calculated_metric_key TEXT NOT NULL,
    business_unit TEXT NOT NULL,
    period_granularity TEXT NOT NULL,
    period_start DATE NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    exit_code INTEGER,
    stdout_excerpt TEXT,
    stderr_excerpt TEXT,
    notes TEXT,
    PRIMARY KEY (run_id, step_key),
    CONSTRAINT calculation_run_steps_status_chk
        CHECK (status IN ('success', 'pending', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_calculation_run_steps_metric
    ON calculation_run_steps(calculated_metric_key, business_unit, started_at DESC);

CREATE TABLE IF NOT EXISTS calculated_metric_value (
    value_id BIGSERIAL PRIMARY KEY,
    definition_id BIGINT REFERENCES calculated_metric_definition(definition_id) ON DELETE SET NULL,
    calculation_run_id TEXT REFERENCES calculation_runs(run_id) ON DELETE SET NULL,
    calculation_step_key TEXT,
    calculated_metric_key TEXT NOT NULL,
    calculated_metric_name TEXT NOT NULL,
    business_unit TEXT NOT NULL,
    show_name TEXT,
    partner_name TEXT,
    channel_name TEXT,
    show_name_norm TEXT GENERATED ALWAYS AS (COALESCE(show_name, '')) STORED,
    partner_name_norm TEXT GENERATED ALWAYS AS (COALESCE(partner_name, '')) STORED,
    channel_name_norm TEXT GENERATED ALWAYS AS (COALESCE(channel_name, '')) STORED,
    period_granularity TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    value_numeric NUMERIC(18, 6),
    value_text TEXT,
    value_raw TEXT,
    currency_code TEXT,
    version TEXT NOT NULL DEFAULT 'v1',
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload JSONB,
    CONSTRAINT calculated_metric_value_granularity_chk
        CHECK (period_granularity IN ('week', 'month', 'quarter', 'year')),
    CONSTRAINT calculated_metric_value_value_chk
        CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL OR value_raw IS NOT NULL),
    CONSTRAINT calculated_metric_value_unique
        UNIQUE (
            calculated_metric_key,
            business_unit,
            show_name_norm,
            partner_name_norm,
            channel_name_norm,
            period_granularity,
            period_start,
            period_end,
            version
        )
);

COMMENT ON TABLE calculated_metric_value IS
'Stored results of calculated metrics, separate from observed fact_metric_observation.';

CREATE INDEX IF NOT EXISTS idx_calculated_metric_value_metric_period
    ON calculated_metric_value(calculated_metric_key, period_granularity, period_start DESC);

CREATE INDEX IF NOT EXISTS idx_calculated_metric_value_run
    ON calculated_metric_value(calculation_run_id, calculation_step_key);

COMMIT;
