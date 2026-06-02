DROP VIEW IF EXISTS fact_metrics_latest_import;
DROP VIEW IF EXISTS manual_tables_reference_latest_import;

CREATE VIEW manual_tables_reference_latest_import AS
WITH latest_batch AS (
    SELECT batch_id
    FROM weekly_import_runs
    WHERE status = 'success'
    ORDER BY finished_at DESC
    LIMIT 1
),
latest_runs AS (
    SELECT
        wi.batch_id,
        wi.unit,
        wi.source_tab,
        wi.source_sheet_id,
        wi.source_gid,
        wi.started_at,
        wi.finished_at,
        wi.rows_loaded,
        wi.metric_rows,
        wi.unmapped_pairs
    FROM weekly_import_runs wi
    JOIN latest_batch lb
      ON lb.batch_id = wi.batch_id
    WHERE wi.status = 'success'
)
SELECT
    lr.batch_id,
    f.unit,
    CASE
        WHEN f.unit = 'b2c_moscow' THEN 'Москва'
        WHEN f.unit = 'b2c_spb' THEN 'СПб'
        ELSE f.unit
    END AS unit_label,
    lr.source_tab,
    lr.started_at AS import_started_at,
    lr.finished_at AS import_finished_at,
    lr.rows_loaded,
    lr.metric_rows,
    lr.unmapped_pairs,
    f.source_sheet_id,
    f.source_gid,
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
    f.row_order,
    f.col_order,
    f.loaded_at,
    f.source_cell_a1,
    f.source_cell_url
FROM manual_tables_reference f
JOIN latest_runs lr
  ON lr.unit = f.unit
 AND f.loaded_at >= (lr.started_at AT TIME ZONE 'UTC')
 AND f.loaded_at <= (lr.finished_at AT TIME ZONE 'UTC')
ORDER BY f.unit, f.period_start, f.row_order, f.col_order;

CREATE VIEW fact_metrics_latest_import AS
SELECT *
FROM manual_tables_reference_latest_import;
