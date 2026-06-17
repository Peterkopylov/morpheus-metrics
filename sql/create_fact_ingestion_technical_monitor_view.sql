DROP VIEW IF EXISTS fact_ingestion_technical_monitor;

CREATE VIEW fact_ingestion_technical_monitor AS
WITH raw_step_attempts AS (
    SELECT
        r.run_id,
        r.cadence,
        r.period_start,
        r.period_end,
        r.started_at,
        r.finished_at,
        r.started_at::date AS ingestion_date,
        r.trigger_mode,
        s.step_key,
        s.source_system,
        s.status AS step_status,
        s.started_at AS step_started_at,
        s.finished_at AS step_finished_at,
        CASE
            WHEN s.source_system = 'amocrm' THEN 'amo'
            WHEN s.source_system = 'erp' THEN 'erp'
            WHEN s.source_system IN ('yandex_metrica', 'yandex_direct', 'yandex_tickets') THEN 'yandex'
            ELSE NULL
        END AS source_group,
        COUNT(o.*)::numeric AS loaded_fact_rows
    FROM fact_ingestion_runs r
    JOIN fact_ingestion_run_steps s
      ON s.run_id = r.run_id
    LEFT JOIN fact_metric_observation o
      ON o.source_system = s.source_system
     AND o.source_run_id = s.source_run_id
     AND o.loaded_at >= s.started_at
     AND o.loaded_at <= s.finished_at
    WHERE s.source_system IN ('amocrm', 'erp', 'yandex_metrica', 'yandex_direct', 'yandex_tickets')
    GROUP BY
        r.run_id,
        r.cadence,
        r.period_start,
        r.period_end,
        r.started_at,
        r.finished_at,
        r.started_at::date,
        r.trigger_mode,
        s.step_key,
        s.source_system,
        s.status,
        s.started_at,
        s.finished_at
),
step_baselines AS (
    SELECT
        cadence,
        step_key,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY loaded_fact_rows) AS expected_fact_rows
    FROM raw_step_attempts
    WHERE step_status = 'success'
      AND loaded_fact_rows > 0
    GROUP BY cadence, step_key
),
latest_step_attempt_per_day AS (
    SELECT
        rsa.*,
        CASE
            WHEN COALESCE(rsa.trigger_mode, '') IN ('cron', 'scheduled', 'automation')
              OR COALESCE(rsa.trigger_mode, '') LIKE '%cron%'
              OR COALESCE(rsa.trigger_mode, '') LIKE '%automation%'
            THEN 'automated'
            ELSE 'manual'
        END AS execution_mode,
        CASE
            WHEN rsa.cadence = 'week' THEN 'weekly'
            WHEN rsa.cadence = 'month' THEN 'monthly'
            ELSE rsa.cadence
        END AS cadence_label,
        COALESCE(sb.expected_fact_rows, 0)::numeric AS expected_fact_rows,
        row_number() OVER (
            PARTITION BY
                rsa.ingestion_date,
                rsa.cadence,
                CASE
                    WHEN COALESCE(rsa.trigger_mode, '') IN ('cron', 'scheduled', 'automation')
                      OR COALESCE(rsa.trigger_mode, '') LIKE '%cron%'
                      OR COALESCE(rsa.trigger_mode, '') LIKE '%automation%'
                    THEN 'automated'
                    ELSE 'manual'
                END,
                rsa.source_group,
                rsa.step_key
            ORDER BY rsa.step_started_at DESC, rsa.run_id DESC
        ) AS rn
    FROM raw_step_attempts rsa
    LEFT JOIN step_baselines sb
      ON sb.cadence = rsa.cadence
     AND sb.step_key = rsa.step_key
    WHERE rsa.source_group IS NOT NULL
),
per_source_day AS (
    SELECT
        ingestion_date,
        cadence,
        cadence_label,
        execution_mode,
        source_group,
        MIN(period_start) AS contour_period_start,
        MAX(period_end) AS contour_period_end,
        SUM(loaded_fact_rows)::numeric AS loaded_fact_rows,
        SUM(expected_fact_rows)::numeric AS expected_fact_rows,
        COUNT(*) AS attempted_step_count,
        COUNT(*) FILTER (WHERE step_status = 'success') AS successful_step_count,
        COUNT(*) FILTER (WHERE step_status = 'failed') AS failed_step_count,
        COUNT(*) FILTER (WHERE step_status = 'pending') AS pending_step_count
    FROM latest_step_attempt_per_day
    WHERE rn = 1
    GROUP BY ingestion_date, cadence, cadence_label, execution_mode, source_group
),
wide AS (
    SELECT
        ingestion_date,
        cadence,
        cadence_label,
        execution_mode,
        MIN(contour_period_start) AS contour_period_start,
        MAX(contour_period_end) AS contour_period_end,

        MAX(CASE WHEN source_group = 'amo' THEN loaded_fact_rows END) AS amo_loaded_fact_rows,
        MAX(CASE WHEN source_group = 'amo' THEN expected_fact_rows END) AS amo_expected_fact_rows,
        MAX(CASE WHEN source_group = 'amo' THEN attempted_step_count END) AS amo_attempted_step_count,
        MAX(CASE WHEN source_group = 'amo' THEN successful_step_count END) AS amo_successful_step_count,
        MAX(CASE WHEN source_group = 'amo' THEN failed_step_count END) AS amo_failed_step_count,
        MAX(CASE WHEN source_group = 'amo' THEN pending_step_count END) AS amo_pending_step_count,

        MAX(CASE WHEN source_group = 'erp' THEN loaded_fact_rows END) AS erp_loaded_fact_rows,
        MAX(CASE WHEN source_group = 'erp' THEN expected_fact_rows END) AS erp_expected_fact_rows,
        MAX(CASE WHEN source_group = 'erp' THEN attempted_step_count END) AS erp_attempted_step_count,
        MAX(CASE WHEN source_group = 'erp' THEN successful_step_count END) AS erp_successful_step_count,
        MAX(CASE WHEN source_group = 'erp' THEN failed_step_count END) AS erp_failed_step_count,
        MAX(CASE WHEN source_group = 'erp' THEN pending_step_count END) AS erp_pending_step_count,

        MAX(CASE WHEN source_group = 'yandex' THEN loaded_fact_rows END) AS yandex_loaded_fact_rows,
        MAX(CASE WHEN source_group = 'yandex' THEN expected_fact_rows END) AS yandex_expected_fact_rows,
        MAX(CASE WHEN source_group = 'yandex' THEN attempted_step_count END) AS yandex_attempted_step_count,
        MAX(CASE WHEN source_group = 'yandex' THEN successful_step_count END) AS yandex_successful_step_count,
        MAX(CASE WHEN source_group = 'yandex' THEN failed_step_count END) AS yandex_failed_step_count,
        MAX(CASE WHEN source_group = 'yandex' THEN pending_step_count END) AS yandex_pending_step_count
    FROM per_source_day
    GROUP BY ingestion_date, cadence, cadence_label, execution_mode
)
SELECT
    ingestion_date,
    cadence,
    cadence_label,
    execution_mode,
    contour_period_start,
    contour_period_end,

    amo_loaded_fact_rows,
    amo_expected_fact_rows,
    CASE
        WHEN amo_expected_fact_rows IS NULL OR amo_expected_fact_rows = 0 THEN NULL
        ELSE LEAST(ROUND(100.0 * amo_loaded_fact_rows / amo_expected_fact_rows, 1), 100.0)
    END AS amo_success_pct,
    amo_attempted_step_count,
    amo_successful_step_count,
    amo_failed_step_count,
    amo_pending_step_count,

    erp_loaded_fact_rows,
    erp_expected_fact_rows,
    CASE
        WHEN erp_expected_fact_rows IS NULL OR erp_expected_fact_rows = 0 THEN NULL
        ELSE LEAST(ROUND(100.0 * erp_loaded_fact_rows / erp_expected_fact_rows, 1), 100.0)
    END AS erp_success_pct,
    erp_attempted_step_count,
    erp_successful_step_count,
    erp_failed_step_count,
    erp_pending_step_count,

    yandex_loaded_fact_rows,
    yandex_expected_fact_rows,
    CASE
        WHEN yandex_expected_fact_rows IS NULL OR yandex_expected_fact_rows = 0 THEN NULL
        ELSE LEAST(ROUND(100.0 * yandex_loaded_fact_rows / yandex_expected_fact_rows, 1), 100.0)
    END AS yandex_success_pct,
    yandex_attempted_step_count,
    yandex_successful_step_count,
    yandex_failed_step_count,
    yandex_pending_step_count
FROM wide
ORDER BY ingestion_date DESC, cadence, execution_mode;
