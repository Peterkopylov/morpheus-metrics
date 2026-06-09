BEGIN;

ALTER TABLE IF EXISTS fact_metrics
    ADD COLUMN IF NOT EXISTS source_cell_a1 TEXT,
    ADD COLUMN IF NOT EXISTS source_cell_url TEXT;

ALTER TABLE IF EXISTS fact_metric_observation
    ADD COLUMN IF NOT EXISTS source_cell_a1 TEXT,
    ADD COLUMN IF NOT EXISTS source_cell_url TEXT;

COMMIT;
