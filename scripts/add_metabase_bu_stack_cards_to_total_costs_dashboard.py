#!/usr/bin/env python3
import argparse
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib import error, request


@dataclass
class MetabaseConfig:
    base_url: str
    api_key: str


BU_CONFIGS = [
    ("b2c_moscow", "Moscow"),
    ("b2c_spb", "SPB"),
    ("b2b", "B2B"),
    ("franchise", "Franchise"),
]


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


def card_query(business_unit: str) -> str:
    return f"""
WITH yearly_costs AS (
    SELECT
        EXTRACT(YEAR FROM period_start)::int AS year,
        metric_name AS component,
        ROUND(SUM(value_numeric)::numeric, 2) AS amount
    FROM monthly_pnl_leaf_only_rollup_history_with_total
    WHERE business_unit = '{business_unit}'
      AND metric_name IN ('Fixed costs', 'Variable costs')
      AND period_start >= DATE '2021-01-01'
      AND period_start < DATE '2027-01-01'
    GROUP BY 1, 2
),
yearly_profit AS (
    SELECT
        EXTRACT(YEAR FROM period_start)::int AS year,
        'Net profit'::text AS component,
        ROUND(SUM(value_numeric)::numeric, 2) AS amount
    FROM monthly_pnl_active_history_with_total
    WHERE business_unit = '{business_unit}'
      AND metric_name = 'Net profit'
      AND period_start >= DATE '2021-01-01'
      AND period_start < DATE '2027-01-01'
    GROUP BY 1
)
SELECT
    year,
    component,
    amount
FROM (
    SELECT * FROM yearly_costs
    UNION ALL
    SELECT * FROM yearly_profit
) q
ORDER BY year, component;
""".strip()


def chart_settings(title: str) -> Dict[str, Any]:
    return {
        "graph.show_values": True,
        "graph.dimensions": ["year", "component"],
        "graph.metrics": ["amount"],
        "graph.series_order": ["Fixed costs", "Variable costs", "Net profit"],
        "stackable.stack_type": "stacked",
        "column_settings": {
            "[\"name\",\"amount\"]": {
                "number_style": "decimal",
            }
        },
        "card.title": title,
    }


def create_card(
    config: MetabaseConfig,
    database_id: int,
    name: str,
    query: str,
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "display": "bar",
        "dataset_query": {
            "type": "native",
            "native": {
                "query": query,
                "template-tags": {},
            },
            "database": database_id,
        },
        "visualization_settings": settings,
    }
    return api_request(config, "POST", "/api/card", payload)


def update_card(
    config: MetabaseConfig,
    card_id: int,
    database_id: int,
    name: str,
    query: str,
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "display": "bar",
        "dataset_query": {
            "type": "native",
            "native": {
                "query": query,
                "template-tags": {},
            },
            "database": database_id,
        },
        "visualization_settings": settings,
    }
    return api_request(config, "PUT", f"/api/card/{card_id}", payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--metabase-database-id", type=int, required=True)
    parser.add_argument("--dashboard-id", type=int, required=True)
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    dashboard = api_request(config, "GET", f"/api/dashboard/{args.dashboard_id}")
    existing_dashcards = dashboard.get("dashcards", [])

    existing_by_name = {}
    for dashcard in existing_dashcards:
        card = dashcard.get("card") or {}
        name = card.get("name")
        if name:
            existing_by_name[name] = dashcard

    results: List[Dict[str, Any]] = []
    new_dashcards: List[Dict[str, Any]] = []

    for dashcard in existing_dashcards:
        card = dashcard.get("card") or {}
        name = card.get("name") or ""
        if name.startswith("BU Stack / "):
            continue
        new_dashcards.append(
            {
                "id": dashcard["id"],
                "card_id": card["id"],
                "row": dashcard["row"],
                "col": dashcard["col"],
                "size_x": dashcard["size_x"],
                "size_y": dashcard["size_y"],
                "parameter_mappings": dashcard.get("parameter_mappings", []),
                "series": dashcard.get("series", []),
            }
        )

    positions = [
        (14, 0),
        (14, 12),
        (26, 0),
        (26, 12),
    ]

    for (business_unit, title_suffix), (row, col) in zip(BU_CONFIGS, positions):
        card_name = f"BU Stack / {title_suffix}"
        settings = chart_settings(card_name)
        query = card_query(business_unit)
        existing = existing_by_name.get(card_name)
        if existing:
            card = update_card(
                config,
                existing["card"]["id"],
                args.metabase_database_id,
                card_name,
                query,
                settings,
            )
            dashcard_id = existing["id"]
            card_id = card["id"]
        else:
            card = create_card(
                config,
                args.metabase_database_id,
                card_name,
                query,
                settings,
            )
            dashcard_id = -100 - len(results)
            card_id = card["id"]

        new_dashcards.append(
            {
                "id": dashcard_id,
                "card_id": card_id,
                "row": row,
                "col": col,
                "size_x": 12,
                "size_y": 12,
                "parameter_mappings": [],
                "series": [],
            }
        )
        results.append({"business_unit": business_unit, "card_id": card_id})

    api_request(config, "PUT", f"/api/dashboard/{args.dashboard_id}/cards", {"cards": new_dashcards})
    print(json.dumps({"dashboard_id": args.dashboard_id, "cards": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
