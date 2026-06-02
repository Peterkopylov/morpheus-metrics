CREATE TABLE IF NOT EXISTS dashboard_refresh_runs (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL,
    job_name TEXT NOT NULL,
    dashboard_scope TEXT NOT NULL,
    triggered_by TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    exit_code INTEGER,
    yoy_refresh_ok BOOLEAN,
    trace_refresh_ok BOOLEAN,
    stdout TEXT,
    stderr TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_dashboard_refresh_runs_started_at
    ON dashboard_refresh_runs(started_at DESC);
