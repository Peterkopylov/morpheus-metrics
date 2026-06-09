DROP VIEW IF EXISTS show_performance_dashboard_quality_checks;

CREATE VIEW show_performance_dashboard_quality_checks AS
WITH expected_sources AS (
    SELECT 'website_visits'::text AS metric_key, 'yandex_metrica'::text AS expected_source_system
    UNION ALL SELECT 'number_of_orders', 'erp'
    UNION ALL SELECT 'number_of_tickets', 'erp'
    UNION ALL SELECT 'number_of_shows', 'erp'
    UNION ALL SELECT 'number_of_show_visitors', 'erp'
    UNION ALL SELECT 'number_of_show_rating_responses', 'erp'
    UNION ALL SELECT 'sum_of_post_show_ratings', 'erp'
    UNION ALL SELECT 'revenue', 'erp'
    UNION ALL SELECT 'costs_salary_variable', 'erp'
),
source_scope AS (
    SELECT
        o.business_unit,
        o.period_start::date AS period_start,
        o.period_end::date AS period_end,
        mc.metric_key,
        o.source_system,
        SUM(o.value_numeric)::numeric AS value_numeric,
        COUNT(*) AS row_count
    FROM fact_metric_observation o
    JOIN metric_catalogue mc
      ON mc.metric_id = o.metric_id
    JOIN expected_sources e
      ON e.metric_key = mc.metric_key
    WHERE o.period_granularity = 'week'
      AND o.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND o.show_name IS NOT NULL
      AND o.partner_name IS NULL
      AND o.channel_name IS NULL
      AND o.value_numeric IS NOT NULL
      AND o.show_name NOT IN ('general', 'сертификаты')
    GROUP BY
        o.business_unit,
        o.period_start::date,
        o.period_end::date,
        mc.metric_key,
        o.source_system
),
source_violations AS (
    SELECT
        'source_integrity'::text AS check_key,
        'Source integrity'::text AS check_name,
        business_unit,
        period_start,
        period_end,
        s.metric_key AS subject,
        CASE WHEN COUNT(*) = 0 THEN 'pass' ELSE 'warn' END AS status,
        SUM(row_count)::numeric AS observed_value,
        NULL::numeric AS reference_value,
        NULL::numeric AS diff_value,
        'Non-primary show-level rows exist in the dashboard source scope. The dashboard base view should exclude them, but their presence is a reconciliation risk.'::text AS notes
    FROM source_scope s
    JOIN expected_sources e
      ON e.metric_key = s.metric_key
    WHERE s.source_system <> e.expected_source_system
    GROUP BY business_unit, period_start, period_end, s.metric_key
),
weekly_revenue AS (
    SELECT
        d.business_unit,
        d.period_start,
        d.period_end,
        SUM(d.revenue)::numeric AS dashboard_show_revenue
    FROM show_performance_dashboard_base d
    GROUP BY d.business_unit, d.period_start, d.period_end
),
erp_general_revenue AS (
    SELECT
        o.business_unit,
        o.period_start::date AS period_start,
        o.period_end::date AS period_end,
        SUM(o.value_numeric)::numeric AS erp_general_revenue
    FROM fact_metric_observation o
    JOIN metric_catalogue mc
      ON mc.metric_id = o.metric_id
    WHERE o.period_granularity = 'week'
      AND o.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND o.source_system = 'erp'
      AND mc.metric_key = 'revenue'
      AND o.show_name IS NULL
      AND o.partner_name IS NULL
      AND o.channel_name IS NULL
    GROUP BY o.business_unit, o.period_start::date, o.period_end::date
),
weekly_revenue_reconciliation AS (
    SELECT
        'weekly_show_vs_general_revenue'::text AS check_key,
        'Weekly show revenue <= ERP general revenue'::text AS check_name,
        w.business_unit,
        w.period_start,
        w.period_end,
        'revenue'::text AS subject,
        CASE
            WHEN w.dashboard_show_revenue > COALESCE(g.erp_general_revenue, 0) + 1 THEN 'fail'
            WHEN g.erp_general_revenue IS NULL THEN 'warn'
            ELSE 'pass'
        END AS status,
        w.dashboard_show_revenue AS observed_value,
        g.erp_general_revenue AS reference_value,
        w.dashboard_show_revenue - COALESCE(g.erp_general_revenue, 0) AS diff_value,
        'Show-level revenue should not exceed ERP general revenue for the same week.'::text AS notes
    FROM weekly_revenue w
    LEFT JOIN erp_general_revenue g
      ON g.business_unit = w.business_unit
     AND g.period_start = w.period_start
     AND g.period_end = w.period_end
),
required_metrics AS (
    SELECT metric_key
    FROM expected_sources
    WHERE metric_key IN (
        'website_visits',
        'number_of_orders',
        'number_of_tickets',
        'number_of_shows',
        'number_of_show_visitors',
        'revenue',
        'costs_salary_variable'
    )
),
show_weeks AS (
    SELECT DISTINCT
        business_unit,
        period_start,
        period_end,
        show_name
    FROM show_performance_dashboard_base
),
show_metric_presence AS (
    SELECT
        sw.business_unit,
        sw.period_start,
        sw.period_end,
        sw.show_name,
        rm.metric_key,
        EXISTS (
            SELECT 1
            FROM show_performance_dashboard_base d
            WHERE d.business_unit = sw.business_unit
              AND d.period_start = sw.period_start
              AND d.period_end = sw.period_end
              AND d.show_name = sw.show_name
              AND (
                  (rm.metric_key = 'website_visits' AND d.website_visits IS NOT NULL)
                  OR (rm.metric_key = 'number_of_orders' AND d.number_of_orders IS NOT NULL)
                  OR (rm.metric_key = 'number_of_tickets' AND d.number_of_tickets IS NOT NULL)
                  OR (rm.metric_key = 'number_of_shows' AND d.number_of_shows IS NOT NULL)
                  OR (rm.metric_key = 'number_of_show_visitors' AND d.number_of_show_visitors IS NOT NULL)
                  OR (rm.metric_key = 'revenue' AND d.revenue IS NOT NULL)
                  OR (rm.metric_key = 'costs_salary_variable' AND d.costs_salary_variable IS NOT NULL)
              )
        ) AS has_metric
    FROM show_weeks sw
    CROSS JOIN required_metrics rm
),
missing_required_metrics AS (
    SELECT
        'missing_required_metric'::text AS check_key,
        'Missing required show-week metric'::text AS check_name,
        business_unit,
        period_start,
        period_end,
        show_name || ' / ' || metric_key AS subject,
        'warn'::text AS status,
        NULL::numeric AS observed_value,
        NULL::numeric AS reference_value,
        NULL::numeric AS diff_value,
        'Metric is null for a show-week that appears in the dashboard base view.'::text AS notes
    FROM show_metric_presence
    WHERE NOT has_metric
),
monthly_revenue_windows AS (
    SELECT
        month_start,
        business_unit,
        SUM(revenue)::numeric AS dashboard_show_revenue_4w
    FROM (
        SELECT
            DATE_TRUNC('month', d.period_start)::date AS month_start,
            d.business_unit,
            d.revenue
        FROM show_performance_dashboard_base d
        WHERE EXTRACT(ISODOW FROM d.period_start) = 1
          AND d.period_start < DATE_TRUNC('month', d.period_start)::date + INTERVAL '28 days'
          AND d.period_end = d.period_start + INTERVAL '6 days'
    ) x
    GROUP BY month_start, business_unit
),
planfact_monthly_revenue AS (
    SELECT
        o.period_start::date AS month_start,
        o.business_unit,
        SUM(o.value_numeric)::numeric AS planfact_revenue
    FROM fact_metric_observation o
    JOIN metric_catalogue mc
      ON mc.metric_id = o.metric_id
    WHERE o.period_granularity = 'month'
      AND o.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND o.source_system = 'planfact'
      AND mc.metric_key = 'revenue'
      AND o.show_name IS NULL
      AND o.partner_name IS NULL
      AND o.channel_name IS NULL
    GROUP BY o.period_start::date, o.business_unit
),
monthly_revenue_reconciliation AS (
    SELECT
        'monthly_4w_vs_planfact_revenue'::text AS check_key,
        '4-week dashboard revenue vs PlanFact monthly revenue'::text AS check_name,
        d.business_unit,
        d.month_start AS period_start,
        (d.month_start + INTERVAL '1 month - 1 day')::date AS period_end,
        'revenue'::text AS subject,
        CASE
            WHEN p.planfact_revenue IS NULL THEN 'warn'
            WHEN ABS(d.dashboard_show_revenue_4w - p.planfact_revenue) / NULLIF(p.planfact_revenue, 0) > 0.25 THEN 'warn'
            ELSE 'pass'
        END AS status,
        d.dashboard_show_revenue_4w AS observed_value,
        p.planfact_revenue AS reference_value,
        d.dashboard_show_revenue_4w - COALESCE(p.planfact_revenue, 0) AS diff_value,
        'Expected to differ by composition: dashboard is show-level ERP revenue and excludes certificates; PlanFact is broader monthly P&L revenue.'::text AS notes
    FROM monthly_revenue_windows d
    LEFT JOIN planfact_monthly_revenue p
      ON p.business_unit = d.business_unit
     AND p.month_start = d.month_start
)
SELECT * FROM source_violations
UNION ALL
SELECT * FROM weekly_revenue_reconciliation
UNION ALL
SELECT * FROM missing_required_metrics
UNION ALL
SELECT * FROM monthly_revenue_reconciliation;
