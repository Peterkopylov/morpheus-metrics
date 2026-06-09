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


def create_card(
    config: MetabaseConfig,
    database_id: int,
    name: str,
    query: str,
    display: str,
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "display": display,
        "collection_id": None,
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


def create_dashboard(config: MetabaseConfig, name: str, description: str) -> Dict[str, Any]:
    payload = {
        "name": name,
        "description": description,
        "collection_id": None,
        "parameters": [],
    }
    return api_request(config, "POST", "/api/dashboard", payload)


def put_dashboard_cards(config: MetabaseConfig, dashboard_id: int, cards):
    return api_request(config, "PUT", f"/api/dashboard/{dashboard_id}/cards", {"cards": cards})


def latest_week_query(unit: str) -> str:
    return f"""
SELECT
    metric_group,
    metric_name,
    metric_key,
    value_type,
    latest_week_start,
    ROUND(current_value::numeric, 4) AS current_value,
    ROUND(year_ago_value::numeric, 4) AS year_ago_value,
    ROUND(abs_delta::numeric, 4) AS abs_delta,
    ROUND((pct_delta * 100)::numeric, 2) AS pct_delta_pct
FROM weekly_metrics_yoy_latest_week
WHERE unit = '{unit}'
ORDER BY metric_group, metric_name;
""".strip()


def trend_query(unit: str) -> str:
    return f"""
SELECT
    display_week_start,
    metric_group || ' / ' || metric_name || ' / ' || comparison_bucket AS series_name,
    metric_value
FROM weekly_metrics_yoy_series_6w
WHERE unit = '{unit}'
ORDER BY display_week_start, series_name;
""".strip()


def matrix_query(unit: str) -> str:
    return f"""
WITH base AS (
    SELECT
        metric_group,
        metric_name,
        metric_key,
        value_type,
        current_week_start,
        comparison_bucket,
        metric_value
    FROM weekly_metrics_yoy_series_6w
    WHERE unit = '{unit}'
),
latest AS (
    SELECT DISTINCT current_week_start
    FROM base
    ORDER BY current_week_start DESC
    LIMIT 6
),
ranked AS (
    SELECT
        b.*,
        DENSE_RANK() OVER (ORDER BY b.current_week_start DESC) AS week_rank_desc
    FROM base b
    JOIN latest l ON l.current_week_start = b.current_week_start
)
SELECT
    metric_group,
    metric_name,
    metric_key,
    value_type,
    ROUND(MAX(metric_value) FILTER (WHERE comparison_bucket = 'current' AND week_rank_desc = 6)::numeric, 4) AS w_5,
    ROUND(MAX(metric_value) FILTER (WHERE comparison_bucket = 'current' AND week_rank_desc = 5)::numeric, 4) AS w_4,
    ROUND(MAX(metric_value) FILTER (WHERE comparison_bucket = 'current' AND week_rank_desc = 4)::numeric, 4) AS w_3,
    ROUND(MAX(metric_value) FILTER (WHERE comparison_bucket = 'current' AND week_rank_desc = 3)::numeric, 4) AS w_2,
    ROUND(MAX(metric_value) FILTER (WHERE comparison_bucket = 'current' AND week_rank_desc = 2)::numeric, 4) AS w_1,
    ROUND(MAX(metric_value) FILTER (WHERE comparison_bucket = 'current' AND week_rank_desc = 1)::numeric, 4) AS w_0,
    ROUND(MAX(metric_value) FILTER (WHERE comparison_bucket = 'year_ago' AND week_rank_desc = 1)::numeric, 4) AS yoy_w_0,
    ROUND((
        MAX(metric_value) FILTER (WHERE comparison_bucket = 'current' AND week_rank_desc = 1) -
        MAX(metric_value) FILTER (WHERE comparison_bucket = 'year_ago' AND week_rank_desc = 1)
    )::numeric, 4) AS yoy_abs_delta
FROM ranked
GROUP BY metric_group, metric_name, metric_key, value_type
ORDER BY metric_group, metric_name;
""".strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--metabase-database-id", type=int, required=True)
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    dashboard = create_dashboard(
        config,
        "Weekly Metrics YoY",
        "Autogenerated dashboard for Moscow and SPB weekly metrics: latest 6 weeks and same weeks a year ago.",
    )

    cards = [
        create_card(config, args.metabase_database_id, "Moscow Weekly Metrics YoY Latest", latest_week_query("b2c_moscow"), "table"),
        create_card(config, args.metabase_database_id, "SPB Weekly Metrics YoY Latest", latest_week_query("b2c_spb"), "table"),
        create_card(config, args.metabase_database_id, "Moscow Weekly Metrics 6W Matrix", matrix_query("b2c_moscow"), "table"),
        create_card(config, args.metabase_database_id, "SPB Weekly Metrics 6W Matrix", matrix_query("b2c_spb"), "table"),
        create_card(config, args.metabase_database_id, "Moscow Weekly Metrics 6W Trend", trend_query("b2c_moscow"), "line"),
        create_card(config, args.metabase_database_id, "SPB Weekly Metrics 6W Trend", trend_query("b2c_spb"), "line"),
    ]

    put_dashboard_cards(
        config,
        dashboard["id"],
        [
            {"id": -1, "card_id": cards[0]["id"], "row": 0, "col": 0, "size_x": 12, "size_y": 10, "parameter_mappings": [], "series": []},
            {"id": -2, "card_id": cards[1]["id"], "row": 0, "col": 12, "size_x": 12, "size_y": 10, "parameter_mappings": [], "series": []},
            {"id": -3, "card_id": cards[2]["id"], "row": 10, "col": 0, "size_x": 12, "size_y": 12, "parameter_mappings": [], "series": []},
            {"id": -4, "card_id": cards[3]["id"], "row": 10, "col": 12, "size_x": 12, "size_y": 12, "parameter_mappings": [], "series": []},
            {"id": -5, "card_id": cards[4]["id"], "row": 22, "col": 0, "size_x": 12, "size_y": 10, "parameter_mappings": [], "series": []},
            {"id": -6, "card_id": cards[5]["id"], "row": 22, "col": 12, "size_x": 12, "size_y": 10, "parameter_mappings": [], "series": []},
        ],
    )

    print(json.dumps({"dashboard_id": dashboard["id"], "dashboard_name": dashboard["name"], "card_ids": [c["id"] for c in cards]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
