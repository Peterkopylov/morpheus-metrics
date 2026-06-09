DROP VIEW IF EXISTS weekly_dashboard_status;

CREATE VIEW weekly_dashboard_status AS
WITH latest_import AS (
    SELECT
        unit,
        MAX(finished_at) FILTER (WHERE status = 'success') AS last_import_finished_at,
        MAX(started_at) FILTER (WHERE status = 'success') AS last_import_started_at,
        MAX(rows_loaded) FILTER (
            WHERE status = 'success'
              AND finished_at = (
                  SELECT MAX(finished_at)
                  FROM weekly_import_runs wi2
                  WHERE wi2.unit = wi.unit
                    AND wi2.status = 'success'
              )
        ) AS last_rows_loaded
    FROM weekly_import_runs wi
    GROUP BY unit
),
latest_period AS (
    SELECT
        unit,
        MAX(period_start) FILTER (WHERE aggregation_level = 'week') AS latest_week_start
    FROM fact_metrics
    WHERE unit IN ('b2c_moscow', 'b2c_spb')
    GROUP BY unit
),
refresh AS (
    SELECT
        MAX(finished_at) FILTER (WHERE status = 'success') AS last_dashboard_refresh_at,
        MAX(started_at) FILTER (WHERE status = 'success') AS last_dashboard_refresh_started_at
    FROM dashboard_refresh_runs
)
SELECT
    u.unit,
    CASE
        WHEN u.unit = 'b2c_moscow' THEN 'Москва'
        WHEN u.unit = 'b2c_spb' THEN 'Спб'
        ELSE u.unit
    END AS unit_label,
    li.last_import_started_at,
    li.last_import_finished_at,
    li.last_rows_loaded,
    lp.latest_week_start,
    r.last_dashboard_refresh_started_at,
    r.last_dashboard_refresh_at
FROM (
    SELECT 'b2c_moscow'::text AS unit
    UNION ALL
    SELECT 'b2c_spb'::text AS unit
) u
LEFT JOIN latest_import li ON li.unit = u.unit
LEFT JOIN latest_period lp ON lp.unit = u.unit
CROSS JOIN refresh r;
