DROP VIEW IF EXISTS calculated_metric_latest_run;

CREATE VIEW calculated_metric_latest_run AS
WITH latest_run AS (
    SELECT
        run_id,
        period_granularity,
        period_start,
        period_end,
        trigger_mode,
        started_at,
        finished_at
    FROM calculation_runs
    WHERE status = 'success'
    ORDER BY finished_at DESC
    LIMIT 1
),
step_windows AS (
    SELECT
        s.run_id,
        s.step_key,
        s.definition_id,
        s.calculated_metric_key,
        s.business_unit,
        s.period_granularity,
        s.period_start,
        s.status,
        s.started_at AS step_started_at,
        s.finished_at AS step_finished_at,
        s.notes
    FROM calculation_run_steps s
    JOIN latest_run lr
      ON lr.run_id = s.run_id
    WHERE s.status = 'success'
)
SELECT
    lr.run_id,
    lr.period_granularity AS run_period_granularity,
    lr.period_start AS run_period_start,
    lr.period_end AS run_period_end,
    lr.trigger_mode,
    lr.started_at AS run_started_at,
    lr.finished_at AS run_finished_at,
    sw.step_key,
    sw.definition_id,
    sw.calculated_metric_key,
    sw.business_unit,
    sw.notes AS step_notes,
    sw.step_started_at,
    sw.step_finished_at,
    v.value_id,
    v.calculated_metric_name,
    v.show_name,
    v.partner_name,
    v.channel_name,
    v.period_granularity,
    v.period_start,
    v.period_end,
    v.value_numeric,
    v.value_text,
    v.value_raw,
    v.currency_code,
    v.version,
    v.calculated_at,
    v.loaded_at,
    v.payload
FROM step_windows sw
JOIN latest_run lr
  ON lr.run_id = sw.run_id
JOIN calculated_metric_value v
  ON v.calculation_run_id = sw.run_id
 AND v.calculation_step_key = sw.step_key
ORDER BY
    v.business_unit,
    v.calculated_metric_key,
    v.period_start,
    v.value_id;
