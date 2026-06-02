CREATE TABLE IF NOT EXISTS weekly_import_runs (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL,
    job_name TEXT NOT NULL,
    unit TEXT NOT NULL,
    source_tab TEXT NOT NULL,
    source_sheet_id TEXT NOT NULL,
    source_gid TEXT NOT NULL,
    aggregation_level TEXT NOT NULL,
    triggered_by TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    exit_code INTEGER,
    rows_loaded INTEGER,
    metric_rows INTEGER,
    unmapped_pairs INTEGER,
    parser_stdout TEXT,
    parser_stderr TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_weekly_import_runs_batch_id
    ON weekly_import_runs(batch_id);

CREATE INDEX IF NOT EXISTS idx_weekly_import_runs_started_at
    ON weekly_import_runs(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_weekly_import_runs_unit_started_at
    ON weekly_import_runs(unit, started_at DESC);
