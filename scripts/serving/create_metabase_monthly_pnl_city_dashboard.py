#!/usr/bin/env python3
import argparse
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import error, request


@dataclass
class MetabaseConfig:
    base_url: str
    api_key: str


def api_request(config: MetabaseConfig, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{config.base_url.rstrip('/')}{path}"
    headers = {
        "x-api-key": config.api_key,
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else None
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc


def resolve_collection_id(args: argparse.Namespace) -> Optional[int]:
    if args.allow_root:
        return None
    if args.metabase_collection_id is None:
        raise RuntimeError(
            "Refusing to create Metabase objects in root by default. "
            "Pass --metabase-collection-id or explicitly opt in with --allow-root."
        )
    return args.metabase_collection_id


def create_card(
    config: MetabaseConfig,
    database_id: int,
    collection_id: Optional[int],
    name: str,
    query: str,
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "display": "table",
        "collection_id": collection_id,
        "dataset_query": {
            "type": "native",
            "native": {
                "query": query,
                "template-tags": {},
            },
            "database": database_id,
        },
        "visualization_settings": {},
    }
    return api_request(config, "POST", "/api/card", payload)


def create_dashboard(
    config: MetabaseConfig,
    collection_id: Optional[int],
    name: str,
    description: str,
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "description": description,
        "collection_id": collection_id,
        "parameters": [],
    }
    return api_request(config, "POST", "/api/dashboard", payload)


def update_dashboard(
    config: MetabaseConfig,
    dashboard_id: int,
    name: str,
    description: str,
    collection_id: Optional[int],
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "description": description,
        "collection_id": collection_id,
        "parameters": [],
    }
    api_request(config, "PUT", f"/api/dashboard/{dashboard_id}", payload)
    return {"id": dashboard_id, "name": name}


def put_dashboard_cards(config: MetabaseConfig, dashboard_id: int, cards) -> Any:
    return api_request(config, "PUT", f"/api/dashboard/{dashboard_id}/cards", {"cards": cards})


def period_query() -> str:
    return """
WITH complete_months AS (
    SELECT period_start
    FROM monthly_pnl_city_analytics_base
    WHERE row_label = 'Выручка'
      AND value_numeric IS NOT NULL
    GROUP BY period_start
),
ranked AS (
    SELECT
        period_start,
        ROW_NUMBER() OVER (ORDER BY period_start DESC) AS month_rank
    FROM complete_months
)
SELECT
    'Период отчета' AS "Показатель",
    TO_CHAR(MAX(period_start) FILTER (WHERE month_rank = 1), 'MM.YYYY') AS "Последний месяц",
    TO_CHAR(MAX(period_start) FILTER (WHERE month_rank = 2), 'MM.YYYY') AS "Предыдущий месяц",
    TO_CHAR(MIN(period_start) FILTER (WHERE month_rank BETWEEN 2 AND 7), 'MM.YYYY')
    || ' - ' ||
    TO_CHAR(MAX(period_start) FILTER (WHERE month_rank BETWEEN 2 AND 7), 'MM.YYYY') AS "Окно среднего за 6 месяцев"
FROM ranked;
""".strip()


def city_query(unit: str) -> str:
    return f"""
WITH complete_months AS (
    SELECT period_start
    FROM monthly_pnl_city_analytics_base
    WHERE business_unit = '{unit}'
      AND row_label = 'Выручка'
      AND value_numeric IS NOT NULL
),
city_rows AS (
    SELECT *
    FROM monthly_pnl_city_analytics_base
    WHERE business_unit = '{unit}'
      AND period_start IN (SELECT period_start FROM complete_months)
),
ranked_months AS (
    SELECT
        period_start,
        ROW_NUMBER() OVER (ORDER BY period_start DESC) AS month_rank
    FROM complete_months
),
last_month AS (
    SELECT period_start
    FROM ranked_months
    WHERE month_rank = 1
),
previous_month AS (
    SELECT period_start
    FROM ranked_months
    WHERE month_rank = 2
),
avg_window AS (
    SELECT period_start
    FROM ranked_months
    WHERE month_rank BETWEEN 2 AND 7
),
aggregated AS (
    SELECT
        row_order,
        row_label,
        value_type,
        MAX(value_numeric) FILTER (WHERE period_start = (SELECT period_start FROM last_month)) AS latest_value,
        MAX(value_numeric) FILTER (WHERE period_start = (SELECT period_start FROM previous_month)) AS previous_value,
        AVG(value_numeric) FILTER (WHERE period_start IN (SELECT period_start FROM avg_window)) AS avg_6m_value
    FROM city_rows
    GROUP BY row_order, row_label, value_type
),
filtered AS (
    SELECT *
    FROM aggregated
    WHERE latest_value IS NOT NULL
       OR previous_value IS NOT NULL
       OR avg_6m_value IS NOT NULL
)
SELECT
    row_label AS "Строка",
    CASE
        WHEN value_type = 'percent' THEN
            TO_CHAR(ROUND((latest_value * 100)::numeric, 1), 'FM999999990.0') || '%'
        WHEN latest_value IS NULL THEN NULL
        ELSE REPLACE(TO_CHAR(ROUND(latest_value::numeric, 0), 'FM999,999,999,990'), ',', ' ') || ' р.'
    END AS "Последний месяц",
    CASE
        WHEN value_type = 'percent' THEN
            TO_CHAR(ROUND((previous_value * 100)::numeric, 1), 'FM999999990.0') || '%'
        WHEN previous_value IS NULL THEN NULL
        ELSE REPLACE(TO_CHAR(ROUND(previous_value::numeric, 0), 'FM999,999,999,990'), ',', ' ') || ' р.'
    END AS "Предыдущий месяц",
    CASE
        WHEN value_type = 'percent' THEN
            TO_CHAR(ROUND((avg_6m_value * 100)::numeric, 1), 'FM999999990.0') || '%'
        WHEN avg_6m_value IS NULL THEN NULL
        ELSE REPLACE(TO_CHAR(ROUND(avg_6m_value::numeric, 0), 'FM999,999,999,990'), ',', ' ') || ' р.'
    END AS "В среднем за последние 6 месяцев"
FROM filtered
ORDER BY row_order, row_label;
""".strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--metabase-database-id", type=int, required=True)
    parser.add_argument("--metabase-collection-id", type=int)
    parser.add_argument("--update-existing-dashboard-id", type=int)
    parser.add_argument("--allow-root", action="store_true")
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    collection_id = resolve_collection_id(args)
    dashboard_name = "Monthly P&L Analytics by City"
    dashboard_description = (
        "Admin-only monthly P&L analytics dashboard for Moscow and SPB. "
        "Built from active monthly P&L facts in fact_metric_observation with level 1 and 2 rollups plus margin/cost-share rows."
    )

    if args.update_existing_dashboard_id:
        dashboard = update_dashboard(
            config,
            args.update_existing_dashboard_id,
            dashboard_name,
            dashboard_description,
            collection_id,
        )
    else:
        dashboard = create_dashboard(config, collection_id, dashboard_name, dashboard_description)

    period_card = create_card(config, args.metabase_database_id, collection_id, "Monthly P&L City Analytics — Period", period_query())
    moscow_card = create_card(config, args.metabase_database_id, collection_id, "Monthly P&L Analytics — Moscow", city_query("b2c_moscow"))
    spb_card = create_card(config, args.metabase_database_id, collection_id, "Monthly P&L Analytics — SPB", city_query("b2c_spb"))

    put_dashboard_cards(
        config,
        dashboard["id"],
        [
            {"id": -1, "card_id": period_card["id"], "row": 0, "col": 0, "size_x": 24, "size_y": 4, "parameter_mappings": [], "series": []},
            {"id": -2, "card_id": moscow_card["id"], "row": 4, "col": 0, "size_x": 24, "size_y": 16, "parameter_mappings": [], "series": []},
            {"id": -3, "card_id": spb_card["id"], "row": 20, "col": 0, "size_x": 24, "size_y": 16, "parameter_mappings": [], "series": []},
        ],
    )

    print(
        json.dumps(
            {
                "dashboard_id": dashboard["id"],
                "dashboard_name": dashboard["name"],
                "card_ids": [period_card["id"], moscow_card["id"], spb_card["id"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
