DROP VIEW IF EXISTS fact_metric_observation_latest_run;

CREATE VIEW fact_metric_observation_latest_run AS
WITH latest_run AS (
    SELECT
        run_id,
        cadence,
        period_start,
        period_end,
        started_at,
        finished_at,
        trigger_mode
    FROM fact_ingestion_runs
    WHERE status = 'success'
    ORDER BY finished_at DESC
    LIMIT 1
),
step_windows AS (
    SELECT
        s.run_id,
        s.step_key,
        s.source_system,
        s.source_run_id,
        s.report_path,
        s.started_at AS step_started_at,
        s.finished_at AS step_finished_at,
        s.notes
    FROM fact_ingestion_run_steps s
    JOIN latest_run lr
      ON lr.run_id = s.run_id
    WHERE s.status = 'success'
)
SELECT
    lr.run_id,
    lr.cadence,
    lr.period_start AS run_period_start,
    lr.period_end AS run_period_end,
    lr.trigger_mode,
    lr.started_at AS run_started_at,
    lr.finished_at AS run_finished_at,
    sw.step_key,
    sw.source_system,
    sw.source_run_id,
    sw.report_path,
    sw.notes AS step_notes,
    sw.step_started_at,
    sw.step_finished_at,
    o.observation_id,
    o.metric_id,
    mc.metric_key,
    mc.metric_name,
    mc.metric_family,
    mc.value_kind,
    o.rule_id,
    o.source_record_key,
    o.business_unit,
    o.show_name,
    o.partner_name,
    o.channel_name,
    o.period_granularity,
    o.period_start,
    o.period_end,
    o.value_numeric,
    o.value_text,
    o.value_raw,
    o.currency_code,
    o.is_estimated,
    o.observed_at,
    o.loaded_at,
    o.source_cell_a1,
    o.source_cell_url,
    o.payload
FROM step_windows sw
JOIN latest_run lr
  ON lr.run_id = sw.run_id
JOIN fact_metric_observation o
  ON o.source_system = sw.source_system
 AND o.source_run_id = sw.source_run_id
 AND o.loaded_at >= sw.step_started_at
 AND o.loaded_at <= sw.step_finished_at
LEFT JOIN metric_catalogue mc
  ON mc.metric_id = o.metric_id
ORDER BY
    o.business_unit,
    sw.source_system,
    mc.metric_name,
    o.show_name,
    o.partner_name,
    o.channel_name,
    o.period_start,
    o.observation_id;
