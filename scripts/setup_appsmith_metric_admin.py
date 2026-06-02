#!/usr/bin/env python3
import argparse

import psycopg2


DDL = """
CREATE TABLE IF NOT EXISTS manual_metric_entries (
    id BIGSERIAL PRIMARY KEY,
    unit TEXT NOT NULL,
    aggregation_level TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE,
    period_label TEXT,
    metric_group TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_key TEXT,
    value NUMERIC,
    value_raw TEXT,
    value_type TEXT NOT NULL DEFAULT 'number',
    notes TEXT,
    created_by TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS manual_metric_entries_unique_active
ON manual_metric_entries (
    unit,
    aggregation_level,
    period_start,
    metric_group,
    metric_name
);

CREATE INDEX IF NOT EXISTS manual_metric_entries_lookup_idx
ON manual_metric_entries (
    unit,
    aggregation_level,
    period_start,
    metric_group,
    metric_name,
    metric_key
);

DROP VIEW IF EXISTS app_metric_search;

CREATE VIEW app_metric_search AS
SELECT
    'weekly_fact'::text AS record_source,
    'fact_metrics'::text AS source_table,
    f.id::text AS record_id,
    f.unit,
    f.aggregation_level,
    f.period_start,
    f.period_end,
    f.period_label,
    f.metric_group,
    f.metric_name,
    f.metric_key,
    f.value,
    f.value_raw,
    f.value_type,
    NULL::text AS notes,
    NULL::text AS created_by,
    f.loaded_at AS recorded_at,
    (f.metric_group || ' ' || f.metric_name || ' ' || COALESCE(f.metric_key, '') || ' ' || COALESCE(f.period_label, ''))::text AS search_blob,
    CASE WHEN f.aggregation_level = 'week'
         THEN ('https://docs.google.com/spreadsheets/d/' || f.source_sheet_id || '/edit#gid=' || f.source_gid::text)
         ELSE NULL
    END AS source_sheet_url
FROM fact_metrics f

UNION ALL

SELECT
    'manual_entry'::text AS record_source,
    'manual_metric_entries'::text AS source_table,
    m.id::text AS record_id,
    m.unit,
    m.aggregation_level,
    m.period_start,
    m.period_end,
    m.period_label,
    m.metric_group,
    m.metric_name,
    m.metric_key,
    m.value,
    m.value_raw,
    m.value_type,
    m.notes,
    m.created_by,
    m.updated_at AS recorded_at,
    (m.metric_group || ' ' || m.metric_name || ' ' || COALESCE(m.metric_key, '') || ' ' || COALESCE(m.period_label, ''))::text AS search_blob,
    NULL::text AS source_sheet_url
FROM manual_metric_entries m
WHERE m.is_active = TRUE;
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(DDL)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
