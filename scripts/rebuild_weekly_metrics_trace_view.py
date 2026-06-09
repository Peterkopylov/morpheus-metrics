#!/usr/bin/env python3
import argparse

import psycopg2


VIEW_SQL = """
DROP VIEW IF EXISTS weekly_metrics_trace;
DROP FUNCTION IF EXISTS excel_col_name(integer);

CREATE OR REPLACE FUNCTION excel_col_name(col_num integer)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    n integer := col_num;
    result text := '';
BEGIN
    IF n IS NULL OR n < 1 THEN
        RETURN NULL;
    END IF;

    WHILE n > 0 LOOP
        result := chr(((n - 1) % 26) + 65) || result;
        n := (n - 1) / 26;
    END LOOP;

    RETURN result;
END;
$$;

CREATE VIEW weekly_metrics_trace AS
SELECT
    f.id,
    f.source_sheet_id,
    f.source_gid,
    f.source_tab,
    f.unit,
    f.aggregation_level,
    f.period_start,
    f.period_end,
    f.period_label,
    f.metric_group,
    f.metric_name,
    f.metric_key,
    f.row_order,
    f.col_order,
    f.value,
    f.value_raw,
    f.value_type,
    f.loaded_at,
    ('A' || f.row_order::text) AS metric_group_a1,
    ('B' || f.row_order::text) AS metric_name_a1,
    (excel_col_name(f.col_order) || f.row_order::text) AS value_a1,
    ('https://docs.google.com/spreadsheets/d/' || f.source_sheet_id || '/edit#gid=' || f.source_gid || '&range=' || ('A' || f.row_order::text)) AS metric_group_url,
    ('https://docs.google.com/spreadsheets/d/' || f.source_sheet_id || '/edit#gid=' || f.source_gid || '&range=' || ('B' || f.row_order::text)) AS metric_name_url,
    ('https://docs.google.com/spreadsheets/d/' || f.source_sheet_id || '/edit#gid=' || f.source_gid || '&range=' || (excel_col_name(f.col_order) || f.row_order::text)) AS value_url,
    CASE
        WHEN f.metric_group IS NULL OR btrim(f.metric_group) = '' THEN true
        ELSE false
    END AS metric_group_blank_in_fact,
    lag(f.metric_group) OVER (
        PARTITION BY f.source_sheet_id, f.source_gid, f.source_tab, f.unit
        ORDER BY f.row_order, f.col_order
    ) AS previous_metric_group_in_fact
FROM fact_metrics f
WHERE f.aggregation_level = 'week'
  AND f.metric_key IS NOT NULL;
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(VIEW_SQL)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
