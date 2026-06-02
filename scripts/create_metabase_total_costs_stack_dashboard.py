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


def dashboard_query() -> str:
    return """
WITH yearly_fixed_variable AS (
    SELECT
        EXTRACT(YEAR FROM period_start)::int AS year,
        metric_name AS component,
        ROUND(SUM(value_numeric)::numeric, 2) AS amount
    FROM monthly_pnl_leaf_only_rollup_history_with_total
    WHERE business_unit = 'total'
      AND metric_name IN ('Fixed costs', 'Variable costs')
      AND period_start >= DATE '2021-01-01'
      AND period_start < DATE '2027-01-01'
    GROUP BY 1, 2
),
yearly_dividends AS (
    SELECT
        EXTRACT(YEAR FROM period_start)::int AS year,
        'Dividends'::text AS component,
        ROUND(SUM(value_numeric)::numeric, 2) AS amount
    FROM monthly_pnl_total_history
    WHERE business_unit = 'total'
      AND metric_name = 'Dividends'
      AND period_start >= DATE '2021-01-01'
      AND period_start < DATE '2027-01-01'
    GROUP BY 1
)
SELECT
    year,
    component,
    amount
FROM (
    SELECT * FROM yearly_fixed_variable
    UNION ALL
    SELECT * FROM yearly_dividends
) q
ORDER BY year, component;
""".strip()


def chart_settings() -> Dict[str, Any]:
    return {
        "graph.show_values": True,
        "graph.dimensions": ["year", "component"],
        "graph.metrics": ["amount"],
        "graph.series_order": ["Fixed costs", "Variable costs", "Dividends"],
        "stackable.stack_type": "stacked",
        "column_settings": {
            "[\"name\",\"amount\"]": {
                "number_style": "decimal",
            }
        },
        "card.title": "Total Costs Stack by Year",
    }


def create_card(
    config: MetabaseConfig,
    database_id: int,
    collection_id: Optional[int],
    name: str,
    query: str,
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "display": "bar",
        "collection_id": collection_id,
        "dataset_query": {
            "type": "native",
            "native": {
                "query": query,
                "template-tags": {},
            },
            "database": database_id,
        },
        "visualization_settings": chart_settings(),
    }
    return api_request(config, "POST", "/api/card", payload)


def update_card(
    config: MetabaseConfig,
    card_id: int,
    database_id: int,
    name: str,
    query: str,
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
        "visualization_settings": chart_settings(),
    }
    return api_request(config, "PUT", f"/api/card/{card_id}", payload)


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


def put_dashboard_cards(config: MetabaseConfig, dashboard_id: int, cards) -> Any:
    return api_request(config, "PUT", f"/api/dashboard/{dashboard_id}/cards", {"cards": cards})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--metabase-database-id", type=int, required=True)
    parser.add_argument("--metabase-collection-id", type=int)
    parser.add_argument("--allow-root", action="store_true")
    parser.add_argument("--update-existing-dashboard-id", type=int)
    parser.add_argument("--update-existing-card-id", type=int)
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    collection_id = resolve_collection_id(args)
    name = "Historical Total Costs Stack"
    description = (
        "Autogenerated stacked bar dashboard for total yearly Fixed costs, "
        "Variable costs, and Dividends."
    )
    query = dashboard_query()

    if args.update_existing_dashboard_id and args.update_existing_card_id:
        dashboard = {"id": args.update_existing_dashboard_id, "name": name}
        card = update_card(
            config,
            args.update_existing_card_id,
            args.metabase_database_id,
            name="Total Fixed / Variable / Dividends by Year",
            query=query,
        )
    else:
        dashboard = create_dashboard(config, collection_id, name, description)
        card = create_card(
            config,
            args.metabase_database_id,
            collection_id,
            name="Total Fixed / Variable / Dividends by Year",
            query=query,
        )
        put_dashboard_cards(
            config,
            dashboard["id"],
            [
                {
                    "id": -1,
                    "card_id": card["id"],
                    "row": 0,
                    "col": 0,
                    "size_x": 24,
                    "size_y": 14,
                    "parameter_mappings": [],
                    "series": [],
                }
            ],
        )

    print(
        json.dumps(
            {
                "dashboard_id": dashboard["id"],
                "dashboard_name": dashboard["name"],
                "card_id": card["id"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
