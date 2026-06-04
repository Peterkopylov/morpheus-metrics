#!/usr/bin/env python3
import argparse
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib import error, request

import psycopg2


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
    display: str = "line",
    visualization_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "display": display,
        "collection_id": collection_id,
        "dataset_query": {
            "type": "native",
            "native": {
                "query": query,
                "template-tags": {},
            },
            "database": database_id,
        },
        "visualization_settings": visualization_settings or {},
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


def put_dashboard_cards(config: MetabaseConfig, dashboard_id: int, cards: List[Dict[str, Any]]) -> Any:
    return api_request(config, "PUT", f"/api/dashboard/{dashboard_id}/cards", {"cards": cards})


def fetch_metrics(database_url: str, unit: str) -> List[Dict[str, str]]:
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH metric_order AS (
                    SELECT
                        unit,
                        metric_key,
                        MIN(row_order) AS metric_order
                    FROM fact_metrics
                    WHERE aggregation_level = 'week'
                      AND unit = %s
                      AND metric_key IS NOT NULL
                    GROUP BY unit, metric_key
                )
                SELECT DISTINCT
                    y.unit,
                    y.metric_key,
                    y.metric_group,
                    y.metric_name,
                    y.value_type,
                    COALESCE(o.metric_order, 999999) AS metric_order
                FROM weekly_metrics_yoy_latest_week y
                LEFT JOIN metric_order o
                  ON o.unit = y.unit
                 AND o.metric_key = y.metric_key
                WHERE y.unit = %s
                ORDER BY COALESCE(o.metric_order, 999999), y.metric_group, y.metric_name, y.metric_key;
                """,
                (unit, unit),
            )
            return [
                {
                    "unit": row[0],
                    "metric_key": row[1],
                    "metric_group": row[2],
                    "metric_name": row[3],
                    "value_type": row[4],
                    "metric_order": row[5],
                }
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def trend_query(unit: str, metric_key: str, value_type: str) -> str:
    metric_value_expr = "metric_value / 100.0" if value_type == "percent" else "metric_value"
    return f"""
SELECT
    display_week_start,
    CASE
        WHEN comparison_bucket = 'current' THEN 'Последние 6 недель'
        WHEN comparison_bucket = 'year_ago' THEN 'Те же недели год назад'
        ELSE comparison_bucket
    END AS series_name,
    {metric_value_expr} AS metric_value
FROM weekly_metrics_yoy_series_6w
WHERE unit = '{unit}'
  AND metric_key = '{metric_key}'
ORDER BY display_week_start, series_name;
""".strip()


def chart_settings(metric: Dict[str, str]) -> Dict[str, Any]:
    title = f"{metric['metric_group']} / {metric['metric_name']}"
    return {
        "graph.show_values": True,
        "graph.dimensions": ["display_week_start", "series_name"],
        "graph.metrics": ["metric_value"],
        "graph.series_order": ["Последние 6 недель", "Те же недели год назад"],
        "series_settings": {
            "Те же недели год назад": {
                "line.style": "dashed",
            }
        },
        "column_settings": {
            "[\"name\",\"metric_value\"]": {
                "number_style": "percent" if metric["value_type"] == "percent" else "decimal",
            }
        },
        "card.title": title,
    }


def unit_title(unit: str) -> str:
    return {
        "b2c_moscow": "Moscow",
        "b2c_spb": "SPB",
    }.get(unit, unit)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--metabase-database-id", type=int, required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--metabase-collection-id", type=int)
    parser.add_argument("--allow-root", action="store_true")
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    collection_id = resolve_collection_id(args)
    created = []

    for unit in ["b2c_moscow", "b2c_spb"]:
        metrics = fetch_metrics(args.database_url, unit)
        dashboard = create_dashboard(
            config,
            collection_id,
            f"{unit_title(unit)} Weekly Metrics Charts",
            f"One chart per weekly metric for {unit}, comparing the last 6 weeks to the same weeks a year ago.",
        )

        card_layouts = []
        for idx, metric in enumerate(metrics):
            card = create_card(
                config,
                args.metabase_database_id,
                collection_id,
                name=f"{unit_title(unit)} {metric['metric_group']} / {metric['metric_name']}",
                query=trend_query(unit, metric["metric_key"], metric["value_type"]),
                display="line",
                visualization_settings=chart_settings(metric),
            )
            row = (idx // 2) * 8
            col = 0 if idx % 2 == 0 else 12
            card_layouts.append(
                {
                    "id": -(idx + 1),
                    "card_id": card["id"],
                    "row": row,
                    "col": col,
                    "size_x": 12,
                    "size_y": 8,
                    "parameter_mappings": [],
                    "series": [],
                }
            )
            created.append({"dashboard_id": dashboard["id"], "card_id": card["id"], "unit": unit, "metric_key": metric["metric_key"]})

        put_dashboard_cards(config, dashboard["id"], card_layouts)
        created.append({"dashboard_id": dashboard["id"], "dashboard_name": dashboard["name"], "unit": unit, "metric_count": len(metrics)})

    print(json.dumps(created, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
