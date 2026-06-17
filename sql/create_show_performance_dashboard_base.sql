CREATE OR REPLACE VIEW show_performance_dashboard_base AS
WITH weekly_show_facts AS (
    SELECT
        o.business_unit,
        o.period_start::date AS period_start,
        o.period_end::date AS period_end,
        NULLIF(BTRIM(o.show_name), '') AS show_name,
        mc.metric_key,
        SUM(o.value_numeric)::numeric AS value_numeric
    FROM fact_metric_observation o
    JOIN metric_catalogue mc
      ON mc.metric_id = o.metric_id
    WHERE o.period_granularity = 'week'
      AND o.business_unit IN ('b2c_moscow', 'b2c_spb')
      AND o.show_name IS NOT NULL
      AND o.partner_name IS NULL
      AND o.channel_name IS NULL
      AND o.value_numeric IS NOT NULL
      AND (
          (mc.metric_key = 'website_visits' AND o.source_system = 'yandex_metrica')
          OR (
              mc.metric_key IN (
                  'number_of_orders',
                  'number_of_tickets',
                  'number_of_shows',
                  'number_of_show_visitors',
                  'number_of_show_rating_responses',
                  'sum_of_post_show_ratings',
                  'revenue',
                  'costs_salary_variable'
              )
              AND o.source_system = 'erp'
          )
      )
      AND mc.metric_key IN (
          'website_visits',
          'number_of_orders',
          'number_of_tickets',
          'number_of_shows',
          'number_of_show_visitors',
          'number_of_show_rating_responses',
          'sum_of_post_show_ratings',
          'revenue',
          'costs_salary_variable'
      )
    GROUP BY
        o.business_unit,
        o.period_start::date,
        o.period_end::date,
        NULLIF(BTRIM(o.show_name), ''),
        mc.metric_key
),
pivoted AS (
    SELECT
        business_unit,
        period_start,
        period_end,
        show_name,
        MAX(value_numeric) FILTER (WHERE metric_key = 'website_visits') AS website_visits,
        MAX(value_numeric) FILTER (WHERE metric_key = 'number_of_orders') AS number_of_orders,
        MAX(value_numeric) FILTER (WHERE metric_key = 'number_of_tickets') AS number_of_tickets,
        MAX(value_numeric) FILTER (WHERE metric_key = 'number_of_shows') AS number_of_shows,
        MAX(value_numeric) FILTER (WHERE metric_key = 'number_of_show_visitors') AS number_of_show_visitors,
        MAX(value_numeric) FILTER (WHERE metric_key = 'number_of_show_rating_responses') AS number_of_show_rating_responses,
        MAX(value_numeric) FILTER (WHERE metric_key = 'sum_of_post_show_ratings') AS sum_of_post_show_ratings,
        MAX(value_numeric) FILTER (WHERE metric_key = 'revenue') AS revenue,
        MAX(value_numeric) FILTER (WHERE metric_key = 'costs_salary_variable') AS costs_salary_variable
    FROM weekly_show_facts
    GROUP BY business_unit, period_start, period_end, show_name
)
SELECT
    business_unit,
    CASE
        WHEN business_unit = 'b2c_moscow' THEN 'Москва'
        WHEN business_unit = 'b2c_spb' THEN 'СПб'
        ELSE business_unit
    END AS city_label,
    period_start,
    period_end,
    TO_CHAR(period_start, 'DD.MM.YYYY') || ' - ' || TO_CHAR(period_end, 'DD.MM.YYYY') AS period_label,
    show_name,
    website_visits,
    number_of_orders,
    number_of_tickets,
    number_of_shows,
    number_of_show_visitors,
    number_of_show_rating_responses,
    sum_of_post_show_ratings,
    revenue,
    costs_salary_variable,
    CASE
        WHEN website_visits IS NULL OR website_visits = 0 OR number_of_orders IS NULL THEN NULL
        ELSE number_of_orders / website_visits
    END AS visit_to_order_conversion,
    CASE
        WHEN number_of_orders IS NULL OR number_of_orders = 0 OR number_of_tickets IS NULL THEN NULL
        ELSE number_of_tickets / number_of_orders
    END AS average_tickets_per_order,
    CASE
        WHEN number_of_shows IS NULL OR number_of_shows = 0 OR number_of_show_visitors IS NULL THEN NULL
        ELSE number_of_show_visitors / number_of_shows
    END AS average_show_load_actual,
    CASE
        WHEN number_of_show_rating_responses IS NULL OR number_of_show_rating_responses = 0 OR sum_of_post_show_ratings IS NULL THEN NULL
        ELSE sum_of_post_show_ratings / number_of_show_rating_responses
    END AS average_post_show_rating,
    revenue - COALESCE(costs_salary_variable, 0) AS contribution_margin_after_actor_salary
FROM pivoted
WHERE show_name IS NOT NULL
  AND show_name NOT IN ('general', 'сертификаты');
