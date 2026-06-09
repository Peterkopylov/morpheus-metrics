DROP VIEW IF EXISTS weekly_marketing_operational_latest;

CREATE VIEW weekly_marketing_operational_latest AS
WITH latest_week AS (
    SELECT
        o.business_unit,
        MAX(o.period_start)::date AS period_start
    FROM fact_metric_observation o
    JOIN metric_catalogue mc
      ON mc.metric_id = o.metric_id
    WHERE o.period_granularity = 'week'
      AND o.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND mc.metric_key IN (
          'marketing_costs',
          'website_visits',
          'number_of_orders',
          'number_of_tickets',
          'revenue',
          'metrica_tracked_purchase_visits',
          'website_orders',
          'yandex_direct_conversion_revenue'
      )
    GROUP BY o.business_unit
),
report_weeks AS (
    SELECT
        o.business_unit,
        o.period_start::date AS period_start
    FROM fact_metric_observation o
    JOIN metric_catalogue mc
      ON mc.metric_id = o.metric_id
    WHERE o.period_granularity = 'week'
      AND o.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND mc.metric_key IN (
          'marketing_costs',
          'website_visits',
          'number_of_orders',
          'number_of_tickets',
          'revenue',
          'metrica_tracked_purchase_visits',
          'website_orders',
          'yandex_direct_conversion_revenue'
      )
    GROUP BY o.business_unit, o.period_start
),
channel_dimension AS (
    SELECT 'perfomance'::text AS channel_name, 'Перформанс маркетинг'::text AS channel_label, 10 AS row_order
    UNION ALL SELECT 'social', 'SMM', 20
    UNION ALL SELECT 'partners', 'Агрегаторы / партнеры', 30
    UNION ALL SELECT 'pr', 'PR', 40
    UNION ALL SELECT 'email', 'Email', 50
    UNION ALL SELECT 'organic', 'Органика', 60
    UNION ALL SELECT 'friends', 'От друзей', 70
    UNION ALL SELECT 'referral', 'Ссылки на других сайтах', 80
    UNION ALL SELECT 'other', 'Прочее', 90
),
channel_facts AS (
    SELECT
        o.business_unit,
        o.period_start::date AS period_start,
        o.period_end::date AS period_end,
        CASE
            WHEN o.channel_name = 'direct' THEN 'perfomance'
            ELSE o.channel_name
        END AS channel_name,
        mc.metric_key,
        SUM(o.value_numeric)::numeric AS value_numeric
    FROM fact_metric_observation o
    JOIN metric_catalogue mc
      ON mc.metric_id = o.metric_id
    WHERE o.period_granularity = 'week'
      AND o.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND o.show_name IS NULL
      AND o.partner_name IS NULL
      AND o.channel_name IS NOT NULL
      AND NOT (mc.metric_key = 'marketing_costs' AND o.source_system = 'calculated_rollup')
      AND mc.metric_key IN (
          'marketing_costs',
          'website_visits',
          'metrica_tracked_purchase_visits',
          'yandex_direct_conversion_revenue'
      )
    GROUP BY o.business_unit, o.period_start, o.period_end, o.channel_name, mc.metric_key
),
channel_observed_rows AS (
    SELECT
        business_unit,
        period_start,
        period_end,
        channel_name,
        MAX(value_numeric) FILTER (WHERE metric_key = 'marketing_costs') AS marketing_costs,
        MAX(value_numeric) FILTER (WHERE metric_key = 'website_visits') AS website_visits,
        MAX(value_numeric) FILTER (WHERE metric_key = 'metrica_tracked_purchase_visits') AS metrica_tracked_purchase_visits,
        MAX(value_numeric) FILTER (WHERE metric_key = 'yandex_direct_conversion_revenue') AS direct_conversion_revenue,
        NULL::numeric AS number_of_orders,
        NULL::numeric AS number_of_tickets,
        NULL::numeric AS revenue
    FROM channel_facts
    GROUP BY business_unit, period_start, period_end, channel_name
),
partner_calculated_costs AS (
    SELECT
        v.business_unit,
        v.period_start::date AS period_start,
        SUM(v.value_numeric)::numeric AS marketing_costs
    FROM calculated_metric_value v
    WHERE v.period_granularity = 'week'
      AND v.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND v.calculated_metric_key = 'partner_commission'
      AND v.partner_name IS NOT NULL
      AND v.channel_name IS NULL
    GROUP BY v.business_unit, v.period_start
),
channel_rows AS (
    SELECT
        rw.business_unit,
        rw.period_start,
        (rw.period_start + INTERVAL '6 days')::date AS period_end,
        cd.channel_name,
        CASE
            WHEN cd.channel_name = 'partners' THEN COALESCE(o.marketing_costs, pcc.marketing_costs)
            ELSE o.marketing_costs
        END AS marketing_costs,
        o.website_visits,
        o.metrica_tracked_purchase_visits,
        o.direct_conversion_revenue,
        NULL::numeric AS number_of_orders,
        NULL::numeric AS number_of_tickets,
        NULL::numeric AS revenue
    FROM report_weeks rw
    CROSS JOIN channel_dimension cd
    LEFT JOIN channel_observed_rows o
      ON o.business_unit = rw.business_unit
     AND o.period_start = rw.period_start
     AND o.channel_name = cd.channel_name
    LEFT JOIN partner_calculated_costs pcc
      ON pcc.business_unit = rw.business_unit
     AND pcc.period_start = rw.period_start
     AND cd.channel_name = 'partners'
),
legacy_totals AS (
    SELECT
        f.unit AS business_unit,
        f.period_start::date AS period_start,
        MAX(
            CASE
                WHEN (f.metric_group = 'САЙТ' AND f.metric_name = 'билетов всего (Я.билеты)')
                  OR (f.metric_group = 'Сайт' AND f.metric_name = 'Количество билетов')
                THEN f.value::numeric
            END
        ) AS number_of_tickets
    FROM fact_metrics f
    WHERE f.aggregation_level = 'week'
      AND f.unit IN ('b2c_moscow', 'b2c_spb')
    GROUP BY f.unit, f.period_start
),
general_facts AS (
    SELECT
        o.business_unit,
        o.period_start::date AS period_start,
        o.period_end::date AS period_end,
        mc.metric_key,
        SUM(o.value_numeric)::numeric AS value_numeric
    FROM fact_metric_observation o
    JOIN metric_catalogue mc
      ON mc.metric_id = o.metric_id
    WHERE o.period_granularity = 'week'
      AND o.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND o.show_name IS NULL
      AND o.partner_name IS NULL
      AND o.channel_name IS NULL
      AND mc.metric_key IN ('revenue', 'website_orders')
      AND o.source_system = 'erp'
    GROUP BY o.business_unit, o.period_start, o.period_end, mc.metric_key
),
general_rows AS (
    SELECT
        g.business_unit,
        g.period_start,
        g.period_end,
        MAX(g.value_numeric) FILTER (WHERE g.metric_key = 'website_orders') AS number_of_orders,
        l.number_of_tickets,
        MAX(g.value_numeric) FILTER (WHERE g.metric_key = 'revenue') AS revenue
    FROM general_facts g
    LEFT JOIN legacy_totals l
      ON l.business_unit = g.business_unit
     AND l.period_start = g.period_start
    GROUP BY g.business_unit, g.period_start, g.period_end, l.number_of_tickets
),
total_rows AS (
    SELECT
        c.business_unit,
        c.period_start,
        c.period_end,
        'total'::text AS channel_name,
        SUM(c.marketing_costs) AS marketing_costs,
        SUM(c.website_visits) AS website_visits,
        SUM(c.metrica_tracked_purchase_visits) AS metrica_tracked_purchase_visits,
        SUM(c.direct_conversion_revenue) AS direct_conversion_revenue,
        g.number_of_orders,
        g.number_of_tickets,
        g.revenue
    FROM channel_rows c
    LEFT JOIN general_rows g
      ON g.business_unit = c.business_unit
     AND g.period_start = c.period_start
     AND g.period_end = c.period_end
    GROUP BY c.business_unit, c.period_start, c.period_end, g.number_of_orders, g.number_of_tickets, g.revenue
),
partner_revenue_rows AS (
    SELECT
        o.business_unit,
        o.period_start::date AS period_start,
        SUM(o.value_numeric)::numeric AS partner_revenue
    FROM fact_metric_observation o
    JOIN metric_catalogue mc
      ON mc.metric_id = o.metric_id
    WHERE o.period_granularity = 'week'
      AND o.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND mc.metric_key = 'revenue'
      AND o.source_system = 'erp'
      AND o.show_name IS NULL
      AND o.partner_name IS NOT NULL
      AND o.channel_name IS NULL
    GROUP BY o.business_unit, o.period_start
),
calculated_latest AS (
    SELECT
        v.business_unit,
        v.period_start::date AS period_start,
        COALESCE(v.channel_name, 'total') AS channel_name,
        v.value_numeric::numeric AS drr
    FROM calculated_metric_value v
    WHERE v.period_granularity = 'week'
      AND v.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND v.calculated_metric_key = 'marketing_costs_share_of_revenue'
      AND v.show_name IS NULL
      AND v.partner_name IS NULL
),
estimated_orders_latest AS (
    SELECT
        v.business_unit,
        v.period_start::date AS period_start,
        COALESCE(v.channel_name, 'total') AS channel_name,
        v.value_numeric::numeric AS estimated_channel_orders
    FROM calculated_metric_value v
    WHERE v.period_granularity = 'week'
      AND v.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND v.calculated_metric_key = 'estimated_channel_orders_from_metrica_mix'
      AND v.show_name IS NULL
      AND v.partner_name IS NULL
),
survey_general AS (
    SELECT
        o.business_unit,
        o.period_start::date AS period_start,
        CASE
            WHEN COALESCE(o.value_text, '') IN ('Реклама в интернете') THEN 'perfomance'
            WHEN COALESCE(o.value_text, '') IN ('Соц. сети') THEN 'social'
            WHEN COALESCE(o.value_text, '') IN ('Яндекс Афиша') THEN 'partners'
            WHEN COALESCE(o.value_text, '') IN ('От друзей', 'Подарили сертификат') THEN 'friends'
            WHEN COALESCE(o.value_text, '') IN ('Яндекс / Google', 'Карты Яндекс, Google, 2ГИС') THEN 'referral'
            WHEN COALESCE(o.value_text, '') IN ('Наш сайт') THEN 'organic'
            ELSE 'other'
        END AS mapped_channel_name,
        SUM(o.value_numeric)::numeric AS response_count
    FROM fact_metric_observation o
    JOIN metric_catalogue mc
      ON mc.metric_id = o.metric_id
    WHERE o.period_granularity = 'week'
      AND o.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND mc.metric_key = 'number_of_source_attribution_responses'
      AND o.show_name = 'general'
      AND COALESCE(o.value_text, '') <> ''
    GROUP BY o.business_unit, o.period_start, mapped_channel_name
),
survey_totals AS (
    SELECT
        business_unit,
        period_start,
        SUM(response_count)::numeric AS total_response_count
    FROM survey_general
    GROUP BY business_unit, period_start
),
tracked_totals AS (
    SELECT
        business_unit,
        period_start,
        metrica_tracked_purchase_visits AS total_tracked_purchase_visits,
        number_of_orders AS total_orders
    FROM total_rows
),
all_rows AS (
    SELECT * FROM channel_rows
    UNION ALL
    SELECT * FROM total_rows
),
attributed_rows AS (
    SELECT
        r.*,
        sg.response_count AS survey_source_response_count,
        st.total_response_count AS survey_total_response_count,
        CASE
            WHEN r.channel_name = 'total' THEN r.revenue
            WHEN r.channel_name = 'perfomance' THEN r.direct_conversion_revenue
            WHEN r.channel_name = 'partners' THEN pr.partner_revenue
            WHEN st.total_response_count IS NULL OR st.total_response_count = 0 THEN NULL
            WHEN gr.revenue IS NULL THEN NULL
            ELSE gr.revenue * COALESCE(sg.response_count, 0) / st.total_response_count
        END AS attributed_revenue,
        CASE
            WHEN r.channel_name = 'total' THEN 'ERP total revenue'
            WHEN r.channel_name = 'perfomance' THEN 'Yandex Metrica performance revenue'
            WHEN r.channel_name = 'partners' THEN 'ERP partner revenue'
            WHEN st.total_response_count IS NULL OR st.total_response_count = 0 THEN 'Survey share allocation unavailable'
            ELSE 'Survey share allocation'
        END AS attributed_revenue_method
    FROM all_rows r
    LEFT JOIN survey_general sg
      ON sg.business_unit = r.business_unit
     AND sg.period_start = r.period_start
     AND sg.mapped_channel_name = r.channel_name
    LEFT JOIN survey_totals st
      ON st.business_unit = r.business_unit
     AND st.period_start = r.period_start
    LEFT JOIN partner_revenue_rows pr
      ON pr.business_unit = r.business_unit
     AND pr.period_start = r.period_start
    LEFT JOIN general_rows gr
      ON gr.business_unit = r.business_unit
     AND gr.period_start = r.period_start
)
SELECT
    r.business_unit,
    CASE
        WHEN r.business_unit = 'b2c_moscow' THEN 'Москва'
        WHEN r.business_unit = 'b2c_spb' THEN 'СПб'
        ELSE r.business_unit
    END AS business_unit_label,
    r.period_start,
    r.period_end,
    TO_CHAR(r.period_start, 'DD.MM') || '-' || TO_CHAR(r.period_end, 'DD.MM') AS period_label,
    r.channel_name,
    CASE
        WHEN r.channel_name = 'perfomance' THEN 'Перформанс маркетинг'
        WHEN r.channel_name = 'direct' THEN 'Перформанс маркетинг'
        WHEN r.channel_name = 'social' THEN 'SMM'
        WHEN r.channel_name = 'partners' THEN 'Агрегаторы / партнеры'
        WHEN r.channel_name = 'email' THEN 'Email'
        WHEN r.channel_name = 'pr' THEN 'PR'
        WHEN r.channel_name = 'organic' THEN 'Органика'
        WHEN r.channel_name = 'friends' THEN 'От друзей'
        WHEN r.channel_name = 'referral' THEN 'Ссылки на других сайтах'
        WHEN r.channel_name = 'other' THEN 'Прочее'
        WHEN r.channel_name = 'total' THEN 'Общее'
        ELSE COALESCE(NULLIF(r.channel_name, ''), 'Не указан')
    END AS channel_label,
    CASE
        WHEN r.channel_name = 'perfomance' THEN 10
        WHEN r.channel_name = 'direct' THEN 10
        WHEN r.channel_name = 'social' THEN 20
        WHEN r.channel_name = 'partners' THEN 30
        WHEN r.channel_name = 'pr' THEN 40
        WHEN r.channel_name = 'email' THEN 50
        WHEN r.channel_name = 'organic' THEN 60
        WHEN r.channel_name = 'friends' THEN 70
        WHEN r.channel_name = 'referral' THEN 80
        WHEN r.channel_name = 'other' THEN 90
        WHEN r.channel_name = 'total' THEN 999
        ELSE 500
    END AS row_order,
    r.marketing_costs,
    r.website_visits,
    r.metrica_tracked_purchase_visits,
    r.direct_conversion_revenue,
    r.number_of_orders,
    r.number_of_tickets,
    r.revenue,
    r.survey_source_response_count,
    r.survey_total_response_count,
    r.attributed_revenue,
    r.attributed_revenue_method,
    COALESCE(
        c.drr,
        CASE
            WHEN r.revenue IS NULL OR r.revenue = 0 OR r.marketing_costs IS NULL THEN NULL
            ELSE r.marketing_costs / r.revenue
        END
    ) AS drr,
    COALESCE(
        e.estimated_channel_orders,
        CASE
            WHEN r.channel_name = 'total' THEN r.number_of_orders
            WHEN tt.total_tracked_purchase_visits IS NULL OR tt.total_tracked_purchase_visits = 0 THEN NULL
            WHEN tt.total_orders IS NULL OR r.metrica_tracked_purchase_visits IS NULL THEN NULL
            ELSE (r.metrica_tracked_purchase_visits / tt.total_tracked_purchase_visits) * tt.total_orders
        END,
        CASE WHEN r.channel_name = 'total' THEN r.number_of_orders ELSE NULL END
    ) AS estimated_channel_orders,
    CASE
        WHEN r.channel_name = 'total' THEN
            CASE WHEN r.survey_total_response_count IS NULL OR r.survey_total_response_count = 0 THEN NULL ELSE 1.0 END
        WHEN r.survey_total_response_count IS NULL OR r.survey_total_response_count = 0 THEN NULL
        ELSE r.survey_source_response_count / r.survey_total_response_count
    END AS survey_source_share
FROM attributed_rows r
LEFT JOIN calculated_latest c
  ON c.business_unit = r.business_unit
 AND c.period_start = r.period_start
 AND c.channel_name = r.channel_name
LEFT JOIN estimated_orders_latest e
  ON e.business_unit = r.business_unit
 AND e.period_start = r.period_start
 AND e.channel_name = r.channel_name
LEFT JOIN tracked_totals tt
  ON tt.business_unit = r.business_unit
 AND tt.period_start = r.period_start
ORDER BY business_unit, row_order, channel_label;
