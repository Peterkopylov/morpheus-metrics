#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import psycopg2


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
Pnl_STRUCTURE_PATH = ROOT / "catalog" / "pnl_structure_mapping_canonical.csv"


BASE_VIEW_SQL = """
DROP VIEW IF EXISTS monthly_pnl_source_overlap;
DROP VIEW IF EXISTS monthly_pnl_leaf_only_rollup_history_with_total;
DROP VIEW IF EXISTS monthly_pnl_leaf_only_operating_profit_history;
DROP VIEW IF EXISTS monthly_pnl_leaf_only_rollup_total_history;
DROP VIEW IF EXISTS monthly_pnl_leaf_only_rollup_history;
DROP VIEW IF EXISTS monthly_pnl_leaf_only_rollup_edges;
DROP VIEW IF EXISTS monthly_pnl_leaf_only_history_with_total;
DROP VIEW IF EXISTS monthly_pnl_leaf_only_total_history;
DROP VIEW IF EXISTS monthly_pnl_leaf_only_history;
DROP VIEW IF EXISTS monthly_pnl_active_history_with_total;
DROP VIEW IF EXISTS monthly_pnl_total_history;
DROP VIEW IF EXISTS monthly_pnl_active_history;
DROP VIEW IF EXISTS monthly_metric_source_bucket;
DROP VIEW IF EXISTS monthly_metric_fact_trace;

CREATE VIEW monthly_metric_fact_trace AS
SELECT
    o.observation_id,
    o.metric_id,
    mc.metric_key,
    mc.metric_name,
    mc.metric_family,
    mc.value_kind,
    o.source_system,
    o.source_run_id,
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
    o.loaded_at,
    o.payload,
    CASE o.source_system
        WHEN 'planfact' THEN 200
        WHEN 'manual_dividends_total_history' THEN 150
        WHEN 'monthly_pnl_calculated_rollup' THEN 115
        WHEN 'historical_leaf_rollup_backfill' THEN 110
        WHEN 'google_sheets_monthly_economics_historical' THEN 100
        ELSE 0
    END AS source_priority,
    CASE
        WHEN o.source_system IN ('planfact', 'manual_dividends_total_history', 'monthly_pnl_calculated_rollup', 'historical_leaf_rollup_backfill', 'google_sheets_monthly_economics_historical') THEN TRUE
        ELSE FALSE
    END AS is_active_monthly_pnl_source
FROM fact_metric_observation o
JOIN metric_catalogue mc
  ON mc.metric_id = o.metric_id
WHERE o.period_granularity = 'month';

CREATE VIEW monthly_metric_source_bucket AS
SELECT
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    source_system,
    business_unit,
    CASE
        WHEN metric_name IN ('Revenue', 'Operating profit') THEN NULL::text
        ELSE show_name
    END AS show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    currency_code,
    source_priority,
    is_active_monthly_pnl_source,
    SUM(value_numeric) AS value_numeric,
    ARRAY_AGG(observation_id ORDER BY observation_id) AS observation_ids,
    ARRAY_AGG(source_run_id ORDER BY observation_id) AS source_run_ids,
    ARRAY_AGG(source_record_key ORDER BY observation_id) AS source_record_keys,
    ARRAY_AGG(value_text ORDER BY observation_id) AS value_texts,
    ARRAY_AGG(value_raw ORDER BY observation_id) AS value_raws,
    ARRAY_AGG(loaded_at ORDER BY observation_id) AS loaded_ats,
    ARRAY_AGG(payload ORDER BY observation_id) AS payloads
FROM monthly_metric_fact_trace
GROUP BY
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    source_system,
    business_unit,
    CASE
        WHEN metric_name IN ('Revenue', 'Operating profit') THEN NULL::text
        ELSE show_name
    END,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    currency_code,
    source_priority,
    is_active_monthly_pnl_source;

CREATE VIEW monthly_pnl_active_history AS
WITH ranked AS (
    SELECT
        t.*,
        ROW_NUMBER() OVER (
            PARTITION BY
                t.metric_id,
                COALESCE(t.business_unit, ''),
                COALESCE(t.show_name, ''),
                COALESCE(t.partner_name, ''),
                COALESCE(t.channel_name, ''),
                t.period_start,
                t.period_end
            ORDER BY
                t.source_priority DESC,
                t.source_system DESC
        ) AS source_rank
    FROM monthly_metric_source_bucket t
    WHERE t.is_active_monthly_pnl_source = TRUE
)
SELECT
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    source_system,
    business_unit,
    show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    value_numeric,
    currency_code,
    source_priority,
    observation_ids,
    source_run_ids,
    source_record_keys,
    value_texts,
    value_raws,
    loaded_ats,
    payloads
FROM ranked
WHERE source_rank = 1;

CREATE VIEW monthly_pnl_source_overlap AS
SELECT
    metric_id,
    metric_key,
    metric_name,
    business_unit,
    show_name,
    partner_name,
    channel_name,
    period_start,
    period_end,
    COUNT(*) AS source_count,
    ARRAY_AGG(source_system ORDER BY source_priority DESC, source_system DESC) AS source_systems,
    ARRAY_AGG(source_run_ids ORDER BY source_priority DESC, source_system DESC) AS source_run_ids,
    ARRAY_AGG(value_numeric ORDER BY source_priority DESC, source_system DESC) AS values_numeric
FROM monthly_metric_source_bucket
WHERE is_active_monthly_pnl_source = TRUE
GROUP BY
    metric_id,
    metric_key,
    metric_name,
    business_unit,
    show_name,
    partner_name,
    channel_name,
    period_start,
    period_end
HAVING COUNT(*) > 1;

CREATE VIEW monthly_pnl_total_history AS
WITH derived_total AS (
    SELECT
        metric_id,
        metric_key,
        metric_name,
        metric_family,
        value_kind,
        'derived_total_from_business_units'::text AS source_system,
        'total'::text AS business_unit,
        show_name,
        partner_name,
        channel_name,
        period_granularity,
        period_start,
        period_end,
        SUM(value_numeric) AS value_numeric,
        currency_code,
        50 AS source_priority,
        NULL::bigint[] AS observation_ids,
        NULL::text[] AS source_run_ids,
        NULL::text[] AS source_record_keys,
        NULL::text[] AS value_texts,
        NULL::text[] AS value_raws,
        NULL::timestamptz[] AS loaded_ats,
        ARRAY_AGG(
            jsonb_build_object(
                'business_unit', business_unit,
                'source_system', source_system,
                'value_numeric', value_numeric
            )
            ORDER BY business_unit
        ) AS payloads,
        'derived_sum_across_all_business_units'::text AS total_origin,
        ARRAY_AGG(DISTINCT business_unit ORDER BY business_unit) AS source_business_units
    FROM monthly_pnl_active_history
    WHERE business_unit IS NOT NULL
      AND business_unit <> 'total'
    GROUP BY
        metric_id,
        metric_key,
        metric_name,
        metric_family,
        value_kind,
        show_name,
        partner_name,
        channel_name,
        period_granularity,
        period_start,
        period_end,
        currency_code
)
SELECT *
FROM derived_total;

CREATE VIEW monthly_pnl_active_history_with_total AS
SELECT
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    source_system,
    business_unit,
    show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    value_numeric,
    currency_code,
    source_priority,
    observation_ids,
    source_run_ids,
    source_record_keys,
    value_texts,
    value_raws,
    loaded_ats,
    payloads
FROM monthly_pnl_active_history
WHERE business_unit IS DISTINCT FROM 'total'
UNION ALL
SELECT
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    source_system,
    business_unit,
    show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    value_numeric,
    currency_code,
    source_priority,
    observation_ids,
    source_run_ids,
    source_record_keys,
    value_texts,
    value_raws,
    loaded_ats,
    payloads
FROM monthly_pnl_total_history;

CREATE VIEW monthly_pnl_leaf_only_history AS
WITH historical_leaf_only_bucket AS (
    SELECT
        metric_id,
        metric_key,
        metric_name,
        metric_family,
        value_kind,
        source_system,
        business_unit,
        show_name,
        partner_name,
        channel_name,
        period_granularity,
        period_start,
        period_end,
        value_numeric,
        currency_code,
        source_priority,
        observation_ids,
        source_run_ids,
        source_record_keys,
        value_texts,
        value_raws,
        loaded_ats,
        payloads
    FROM monthly_metric_source_bucket
        WHERE source_system = 'google_sheets_monthly_economics_historical'
),
planfact_leaf_only_raw AS (
    SELECT
        observation_id,
        metric_id,
        metric_key,
        metric_name,
        metric_family,
        value_kind,
        source_run_id,
        source_record_key,
        business_unit,
        show_name,
        partner_name,
        channel_name,
        period_granularity,
        period_start,
        period_end,
        value_numeric,
        value_text,
        value_raw,
        currency_code,
        loaded_at,
        payload
    FROM monthly_metric_fact_trace
    WHERE source_system = 'planfact'
      AND business_unit IN ('general', 'b2c_moscow', 'b2c_spb', 'b2b', 'franchise')
      AND (
        (metric_name = 'Revenue' AND COALESCE(payload ->> 'source_label', '') = 'Выручка')
        OR (
            metric_name <> 'Revenue'
            AND COALESCE(payload ->> 'source_label', '') NOT IN (
                'Переменные расходы',
                'Постоянные расходы',
                'Инвестиции',
                'Основные расходы',
                'ФОТ',
                'ФОТ - Переменные',
                'ФОТ - Постоянные',
                'ПЕРЕЕЗД',
                'ПРЕМИИ 2025',
                'Для спектаклей',
                'Маркетинг и реклама',
                'Командные',
                'Логистика',
                'Помещение и офис',
                'Сервисы и их настройка',
                'Командировочные',
                'Прочие расходы',
                'Операционная прибыль',
                'Прочие доходы',
                'EBITDA',
                'Прибыль до процентов и налогов (EBIT)',
                'Прибыль до налогов (EBT)',
                'Чистая прибыль (убыток)',
                'Дивиденды',
                'Нераспределенная прибыль'
            )
        )
      )
),
planfact_leaf_only_bucket AS (
    SELECT
        metric_id,
        metric_key,
        metric_name,
        metric_family,
        value_kind,
        'planfact_leaf_only'::text AS source_system,
        business_unit,
        show_name,
        partner_name,
        channel_name,
        period_granularity,
        period_start,
        period_end,
        SUM(value_numeric) AS value_numeric,
        currency_code,
        205 AS source_priority,
        ARRAY_AGG(observation_id ORDER BY observation_id) AS observation_ids,
        ARRAY_AGG(source_run_id ORDER BY observation_id) AS source_run_ids,
        ARRAY_AGG(source_record_key ORDER BY observation_id) AS source_record_keys,
        ARRAY_AGG(value_text ORDER BY observation_id) AS value_texts,
        ARRAY_AGG(value_raw ORDER BY observation_id) AS value_raws,
        ARRAY_AGG(loaded_at ORDER BY observation_id) AS loaded_ats,
        ARRAY_AGG(payload ORDER BY observation_id) AS payloads
    FROM planfact_leaf_only_raw
    GROUP BY
        metric_id,
        metric_key,
        metric_name,
        metric_family,
        value_kind,
        business_unit,
        show_name,
        partner_name,
        channel_name,
        period_granularity,
        period_start,
        period_end,
        currency_code
)
SELECT *
FROM historical_leaf_only_bucket
UNION ALL
SELECT *
FROM planfact_leaf_only_bucket;

CREATE VIEW monthly_pnl_leaf_only_total_history AS
SELECT
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    'derived_total_from_leaf_only_business_units'::text AS source_system,
    'total'::text AS business_unit,
    show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    SUM(value_numeric) AS value_numeric,
    currency_code,
    55 AS source_priority,
    NULL::bigint[] AS observation_ids,
    NULL::text[] AS source_run_ids,
    NULL::text[] AS source_record_keys,
    NULL::text[] AS value_texts,
    NULL::text[] AS value_raws,
    NULL::timestamptz[] AS loaded_ats,
    ARRAY_AGG(
        jsonb_build_object(
            'business_unit', business_unit,
            'source_system', source_system,
            'value_numeric', value_numeric
        )
        ORDER BY business_unit
    ) AS payloads
FROM monthly_pnl_leaf_only_history
WHERE business_unit IS NOT NULL
  AND business_unit <> 'total'
GROUP BY
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    currency_code;

CREATE VIEW monthly_pnl_leaf_only_history_with_total AS
SELECT
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    source_system,
    business_unit,
    show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    value_numeric,
    currency_code,
    source_priority,
    observation_ids,
    source_run_ids,
    source_record_keys,
    value_texts,
    value_raws,
    loaded_ats,
    payloads
FROM monthly_pnl_leaf_only_history
UNION ALL
SELECT
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    source_system,
    business_unit,
    show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    value_numeric,
    currency_code,
    source_priority,
    observation_ids,
    source_run_ids,
    source_record_keys,
    value_texts,
    value_raws,
    loaded_ats,
    payloads
FROM monthly_pnl_leaf_only_total_history;
"""


def load_rollup_edges() -> list[tuple[str, str]]:
    with Pnl_STRUCTURE_PATH.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    path_to_metric = {
        (row.get("pnl_node_path") or "").strip(): (row.get("canonical_metric") or "").strip()
        for row in rows
        if (row.get("pnl_node_path") or "").strip() and (row.get("canonical_metric") or "").strip()
    }

    edges: list[tuple[str, str]] = []
    for row in rows:
        parent_path = (row.get("parent_pnl_node_path") or "").strip()
        child_metric = (row.get("canonical_metric") or "").strip()
        if not parent_path or not child_metric:
            continue
        parent_metric = path_to_metric.get(parent_path, "").strip()
        if not parent_metric or parent_metric == child_metric:
            continue
        edges.append((parent_metric, child_metric))

    edges = sorted(set(edges))
    return edges


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_leaf_rollup_sql() -> str:
    edges = load_rollup_edges()
    values_sql = ",\n        ".join(f"({sql_literal(parent)}, {sql_literal(child)})" for parent, child in edges)
    return f"""
CREATE VIEW monthly_pnl_leaf_only_rollup_edges AS
SELECT *
FROM (
    VALUES
        {values_sql}
) AS t(parent_metric_name, child_metric_name);

CREATE VIEW monthly_pnl_leaf_only_rollup_history AS
WITH RECURSIVE rollup_chain AS (
    SELECT
        h.metric_name AS source_metric_name,
        h.metric_name AS rolled_metric_name,
        h.business_unit,
        h.show_name,
        h.partner_name,
        h.channel_name,
        h.period_granularity,
        h.period_start,
        h.period_end,
        h.currency_code,
        h.value_numeric,
        h.source_system AS base_source_system
    FROM monthly_pnl_leaf_only_history h

    UNION ALL

    SELECT
        c.source_metric_name,
        e.parent_metric_name AS rolled_metric_name,
        c.business_unit,
        NULL::text AS show_name,
        c.partner_name,
        NULL::text AS channel_name,
        c.period_granularity,
        c.period_start,
        c.period_end,
        c.currency_code,
        c.value_numeric,
        c.base_source_system
    FROM rollup_chain c
    JOIN monthly_pnl_leaf_only_rollup_edges e
      ON e.child_metric_name = c.rolled_metric_name
)
SELECT
    mc.metric_id,
    mc.metric_key,
    mc.metric_name,
    mc.metric_family,
    mc.value_kind,
    'derived_leaf_only_rollup'::text AS source_system,
    r.business_unit,
    r.show_name,
    r.partner_name,
    r.channel_name,
    r.period_granularity,
    r.period_start,
    r.period_end,
    SUM(r.value_numeric) AS value_numeric,
    r.currency_code,
    60 AS source_priority,
    NULL::bigint[] AS observation_ids,
    NULL::text[] AS source_run_ids,
    NULL::text[] AS source_record_keys,
    NULL::text[] AS value_texts,
    NULL::text[] AS value_raws,
    NULL::timestamptz[] AS loaded_ats,
    ARRAY_AGG(
        jsonb_build_object(
            'source_metric_name', r.source_metric_name,
            'base_source_system', r.base_source_system,
            'value_numeric', r.value_numeric
        )
        ORDER BY r.source_metric_name
    ) AS payloads
FROM rollup_chain r
JOIN metric_catalogue mc
  ON mc.metric_name = r.rolled_metric_name
GROUP BY
    mc.metric_id,
    mc.metric_key,
    mc.metric_name,
    mc.metric_family,
    mc.value_kind,
    r.business_unit,
    r.show_name,
    r.partner_name,
    r.channel_name,
    r.period_granularity,
    r.period_start,
    r.period_end,
    r.currency_code;

CREATE VIEW monthly_pnl_leaf_only_rollup_total_history AS
SELECT
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    'derived_total_from_leaf_only_rollup_business_units'::text AS source_system,
    'total'::text AS business_unit,
    show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    SUM(value_numeric) AS value_numeric,
    currency_code,
    65 AS source_priority,
    NULL::bigint[] AS observation_ids,
    NULL::text[] AS source_run_ids,
    NULL::text[] AS source_record_keys,
    NULL::text[] AS value_texts,
    NULL::text[] AS value_raws,
    NULL::timestamptz[] AS loaded_ats,
    ARRAY_AGG(
        jsonb_build_object(
            'business_unit', business_unit,
            'source_system', source_system,
            'value_numeric', value_numeric
        )
        ORDER BY business_unit
    ) AS payloads
FROM monthly_pnl_leaf_only_rollup_history
WHERE business_unit IS NOT NULL
  AND business_unit <> 'total'
GROUP BY
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    currency_code;

CREATE VIEW monthly_pnl_leaf_only_operating_profit_history AS
WITH rollup_inputs AS (
    SELECT
        metric_name,
        business_unit,
        show_name,
        partner_name,
        channel_name,
        period_granularity,
        period_start,
        period_end,
        currency_code,
        value_numeric
    FROM monthly_pnl_leaf_only_rollup_history
    WHERE metric_name IN ('Revenue', 'Variable costs', 'Fixed costs')

    UNION ALL

    SELECT
        metric_name,
        business_unit,
        show_name,
        partner_name,
        channel_name,
        period_granularity,
        period_start,
        period_end,
        currency_code,
        value_numeric
    FROM monthly_pnl_leaf_only_rollup_total_history
    WHERE metric_name IN ('Revenue', 'Variable costs', 'Fixed costs')
),
components AS (
    SELECT
        business_unit,
        show_name,
        partner_name,
        channel_name,
        period_granularity,
        period_start,
        period_end,
        currency_code,
        SUM(CASE WHEN metric_name = 'Revenue' THEN value_numeric ELSE 0 END) AS revenue_value,
        SUM(CASE WHEN metric_name = 'Variable costs' THEN value_numeric ELSE 0 END) AS variable_costs_value,
        SUM(CASE WHEN metric_name = 'Fixed costs' THEN value_numeric ELSE 0 END) AS fixed_costs_value
    FROM rollup_inputs
    GROUP BY
        business_unit,
        show_name,
        partner_name,
        channel_name,
        period_granularity,
        period_start,
        period_end,
        currency_code
)
SELECT
    mc.metric_id,
    mc.metric_key,
    mc.metric_name,
    mc.metric_family,
    mc.value_kind,
    'derived_leaf_only_formula'::text AS source_system,
    c.business_unit,
    c.show_name,
    c.partner_name,
    c.channel_name,
    c.period_granularity,
    c.period_start,
    c.period_end,
    c.revenue_value - c.variable_costs_value - c.fixed_costs_value AS value_numeric,
    c.currency_code,
    70 AS source_priority,
    NULL::bigint[] AS observation_ids,
    NULL::text[] AS source_run_ids,
    NULL::text[] AS source_record_keys,
    NULL::text[] AS value_texts,
    NULL::text[] AS value_raws,
    NULL::timestamptz[] AS loaded_ats,
    ARRAY[
        jsonb_build_object('component_metric_name', 'Revenue', 'value_numeric', c.revenue_value),
        jsonb_build_object('component_metric_name', 'Variable costs', 'value_numeric', c.variable_costs_value),
        jsonb_build_object('component_metric_name', 'Fixed costs', 'value_numeric', c.fixed_costs_value)
    ] AS payloads
FROM components c
JOIN metric_catalogue mc
  ON mc.metric_name = 'Operating profit'
WHERE c.revenue_value <> 0
   OR c.variable_costs_value <> 0
   OR c.fixed_costs_value <> 0;

CREATE VIEW monthly_pnl_leaf_only_rollup_history_with_total AS
SELECT
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    source_system,
    business_unit,
    show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    value_numeric,
    currency_code,
    source_priority,
    observation_ids,
    source_run_ids,
    source_record_keys,
    value_texts,
    value_raws,
    loaded_ats,
    payloads
FROM monthly_pnl_leaf_only_rollup_history
UNION ALL
SELECT
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    source_system,
    business_unit,
    show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    value_numeric,
    currency_code,
    source_priority,
    observation_ids,
    source_run_ids,
    source_record_keys,
    value_texts,
    value_raws,
    loaded_ats,
    payloads
FROM monthly_pnl_leaf_only_rollup_total_history
UNION ALL
SELECT
    metric_id,
    metric_key,
    metric_name,
    metric_family,
    value_kind,
    source_system,
    business_unit,
    show_name,
    partner_name,
    channel_name,
    period_granularity,
    period_start,
    period_end,
    value_numeric,
    currency_code,
    source_priority,
    observation_ids,
    source_run_ids,
    source_record_keys,
    value_texts,
    value_raws,
    loaded_ats,
    payloads
FROM monthly_pnl_leaf_only_operating_profit_history;
"""


def build_view_sql() -> str:
    return BASE_VIEW_SQL + "\n" + build_leaf_rollup_sql()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(build_view_sql())
    finally:
        conn.close()


if __name__ == "__main__":
    main()
