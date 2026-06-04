#!/usr/bin/env python3
import argparse

import psycopg2


VIEW_SQL = """
DROP VIEW IF EXISTS weekly_metrics_latest_comparison;
DROP VIEW IF EXISTS weekly_metrics_yoy_latest_week;
DROP VIEW IF EXISTS weekly_metrics_yoy_series_6w;

CREATE VIEW weekly_metrics_yoy_series_6w AS
WITH latest AS (
    SELECT MAX(period_start)::date AS latest_week_start
    FROM fact_metrics
    WHERE aggregation_level = 'week'
      AND unit IN ('b2c_moscow', 'b2c_spb')
),
current_weeks AS (
    SELECT
        f.unit,
        f.metric_key,
        f.metric_group,
        f.metric_name,
        f.value_type,
        f.period_start::date AS current_week_start,
        (f.period_start::date - INTERVAL '364 day')::date AS year_ago_week_start,
        f.value::numeric AS current_value
    FROM fact_metrics f
    CROSS JOIN latest l
    WHERE f.aggregation_level = 'week'
      AND f.unit IN ('b2c_moscow', 'b2c_spb')
      AND f.metric_key IS NOT NULL
      AND f.value_type IN ('number', 'percent')
      AND f.period_start::date BETWEEN (l.latest_week_start - INTERVAL '35 day')::date AND l.latest_week_start
),
paired AS (
    SELECT
        c.unit,
        c.metric_key,
        c.metric_group,
        c.metric_name,
        c.value_type,
        c.current_week_start,
        c.year_ago_week_start,
        c.current_value,
        p.value::numeric AS year_ago_value,
        DENSE_RANK() OVER (PARTITION BY c.unit ORDER BY c.current_week_start DESC) AS week_rank_desc
    FROM current_weeks c
    LEFT JOIN fact_metrics p
      ON p.aggregation_level = 'week'
     AND p.unit = c.unit
     AND p.metric_key = c.metric_key
     AND p.period_start::date = c.year_ago_week_start
     AND p.value_type = c.value_type
)
SELECT
    unit,
    metric_key,
    metric_group,
    metric_name,
    value_type,
    current_week_start,
    year_ago_week_start,
    'current'::text AS comparison_bucket,
    current_week_start AS display_week_start,
    current_value AS metric_value,
    week_rank_desc
FROM paired
UNION ALL
SELECT
    unit,
    metric_key,
    metric_group,
    metric_name,
    value_type,
    current_week_start,
    year_ago_week_start,
    'year_ago'::text AS comparison_bucket,
    current_week_start AS display_week_start,
    year_ago_value AS metric_value,
    week_rank_desc
FROM paired
WHERE year_ago_value IS NOT NULL;

CREATE VIEW weekly_metrics_yoy_latest_week AS
WITH latest AS (
    SELECT MAX(current_week_start)::date AS latest_week_start
    FROM weekly_metrics_yoy_series_6w
),
current_rows AS (
    SELECT
        s.unit,
        s.metric_key,
        s.metric_group,
        s.metric_name,
        s.value_type,
        s.current_week_start,
        MAX(CASE WHEN s.comparison_bucket = 'current' THEN s.metric_value END) AS current_value,
        MAX(CASE WHEN s.comparison_bucket = 'year_ago' THEN s.metric_value END) AS year_ago_value
    FROM weekly_metrics_yoy_series_6w s
    JOIN latest l ON l.latest_week_start = s.current_week_start
    GROUP BY s.unit, s.metric_key, s.metric_group, s.metric_name, s.value_type, s.current_week_start
)
SELECT
    unit,
    metric_key,
    metric_group,
    metric_name,
    value_type,
    current_week_start AS latest_week_start,
    current_value,
    year_ago_value,
    current_value - year_ago_value AS abs_delta,
    CASE
        WHEN year_ago_value IS NULL OR year_ago_value = 0 THEN NULL
        ELSE (current_value - year_ago_value) / year_ago_value
    END AS pct_delta
FROM current_rows;

CREATE VIEW weekly_metrics_latest_comparison AS
WITH latest AS (
    SELECT
        unit,
        MAX(period_start)::date AS latest_week_start
    FROM fact_metrics
    WHERE aggregation_level = 'week'
      AND unit IN ('b2c_moscow', 'b2c_spb')
    GROUP BY unit
),
current_rows AS (
    SELECT
        f.unit,
        CASE
            WHEN f.unit = 'b2c_moscow' THEN 'Москва'
            WHEN f.unit = 'b2c_spb' THEN 'СПб'
            ELSE f.unit
        END AS unit_label,
        f.metric_key,
        f.metric_group,
        f.metric_name,
        f.value_type,
        f.row_order,
        f.col_order,
        f.period_start::date AS latest_week_start,
        COALESCE(f.period_end::date, (f.period_start::date + INTERVAL '6 day')::date) AS latest_week_end,
        f.value::numeric AS latest_value
    FROM fact_metrics f
    JOIN latest l
      ON l.unit = f.unit
     AND l.latest_week_start = f.period_start::date
    WHERE f.aggregation_level = 'week'
      AND f.unit IN ('b2c_moscow', 'b2c_spb')
      AND f.metric_key IS NOT NULL
      AND f.value_type IN ('number', 'percent')
),
prev_period AS (
    SELECT
        c.unit,
        c.metric_key,
        c.value_type,
        p.value::numeric AS prev_period_value
    FROM current_rows c
    LEFT JOIN fact_metrics p
      ON p.aggregation_level = 'week'
     AND p.unit = c.unit
     AND p.metric_key = c.metric_key
     AND p.value_type = c.value_type
     AND p.period_start::date = (c.latest_week_start - INTERVAL '7 day')::date
),
avg_prev_4 AS (
    SELECT
        c.unit,
        c.metric_key,
        c.value_type,
        AVG(p.value::numeric) AS avg_prev_4w_value,
        COUNT(p.value) AS avg_prev_4w_points
    FROM current_rows c
    LEFT JOIN fact_metrics p
      ON p.aggregation_level = 'week'
     AND p.unit = c.unit
     AND p.metric_key = c.metric_key
     AND p.value_type = c.value_type
     AND p.period_start::date BETWEEN (c.latest_week_start - INTERVAL '28 day')::date
                                 AND (c.latest_week_start - INTERVAL '7 day')::date
    GROUP BY c.unit, c.metric_key, c.value_type
),
year_ago AS (
    SELECT
        c.unit,
        c.metric_key,
        c.value_type,
        p.value::numeric AS year_ago_value
    FROM current_rows c
    LEFT JOIN fact_metrics p
      ON p.aggregation_level = 'week'
     AND p.unit = c.unit
     AND p.metric_key = c.metric_key
     AND p.value_type = c.value_type
     AND p.period_start::date = (c.latest_week_start - INTERVAL '364 day')::date
)
SELECT
    c.unit,
    c.unit_label,
    c.metric_key,
    c.metric_group,
    c.metric_name,
    c.value_type,
    c.row_order,
    c.col_order,
    c.latest_week_start,
    c.latest_week_end,
    TO_CHAR(c.latest_week_start, 'DD.MM') || '-' || TO_CHAR(c.latest_week_end, 'DD.MM') AS latest_week_label,
    c.latest_value,
    pp.prev_period_value,
    a.avg_prev_4w_value,
    a.avg_prev_4w_points,
    y.year_ago_value,
    c.latest_value - pp.prev_period_value AS week_over_week_abs_delta,
    CASE
        WHEN c.value_type = 'percent' OR pp.prev_period_value IS NULL OR pp.prev_period_value = 0 THEN NULL
        ELSE (c.latest_value - pp.prev_period_value) / pp.prev_period_value
    END AS week_over_week_pct_delta,
    c.latest_value - a.avg_prev_4w_value AS avg_prev_4w_abs_delta,
    CASE
        WHEN c.value_type = 'percent' OR a.avg_prev_4w_value IS NULL OR a.avg_prev_4w_value = 0 THEN NULL
        ELSE (c.latest_value - a.avg_prev_4w_value) / a.avg_prev_4w_value
    END AS avg_prev_4w_pct_delta,
    c.latest_value - y.year_ago_value AS year_over_year_abs_delta,
    CASE
        WHEN c.value_type = 'percent' OR y.year_ago_value IS NULL OR y.year_ago_value = 0 THEN NULL
        ELSE (c.latest_value - y.year_ago_value) / y.year_ago_value
    END AS year_over_year_pct_delta,
    CASE
        WHEN c.value_type = 'percent' THEN 'pp'
        ELSE '%'
    END AS delta_display_kind
FROM current_rows c
LEFT JOIN prev_period pp
  ON pp.unit = c.unit
 AND pp.metric_key = c.metric_key
 AND pp.value_type = c.value_type
LEFT JOIN avg_prev_4 a
  ON a.unit = c.unit
 AND a.metric_key = c.metric_key
 AND a.value_type = c.value_type
LEFT JOIN year_ago y
  ON y.unit = c.unit
 AND y.metric_key = c.metric_key
 AND y.value_type = c.value_type
ORDER BY c.unit, c.row_order, c.metric_group, c.metric_name;
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
