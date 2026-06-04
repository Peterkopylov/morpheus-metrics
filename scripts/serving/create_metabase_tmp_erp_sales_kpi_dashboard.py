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
            "native": {"query": query, "template-tags": {}},
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


def put_dashboard_cards(config: MetabaseConfig, dashboard_id: int, cards) -> Any:
    return api_request(config, "PUT", f"/api/dashboard/{dashboard_id}/cards", {"cards": cards})


def query(unit: str) -> str:
    return f"""
SELECT
    metric_name AS "Показатель",
    current_period_label AS "Текущий период",
    TO_CHAR(ROUND(current_value_rub::numeric, 0), 'FM999999999990') AS "Сейчас",
    year_ago_period_label AS "Год назад",
    TO_CHAR(ROUND(year_ago_value_rub::numeric, 0), 'FM999999999990') AS "Год назад значение"
FROM tmp_erp_sales_kpi_snapshot
WHERE unit = '{unit}'
ORDER BY display_order;
""".strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--metabase-database-id", type=int, required=True)
    parser.add_argument("--metabase-collection-id", type=int)
    parser.add_argument("--allow-root", action="store_true")
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    collection_id = resolve_collection_id(args)
    dashboard = create_dashboard(
        config,
        collection_id,
        "TEMP ERP Sales KPI Prototype",
        "Temporary prototype dashboard based on ERP sales KPI snapshot table.",
    )
    cards = [
        create_card(config, args.metabase_database_id, collection_id, "TEMP ERP Sales KPI Moscow", query("b2c_moscow")),
        create_card(config, args.metabase_database_id, collection_id, "TEMP ERP Sales KPI SPB", query("b2c_spb")),
    ]
    put_dashboard_cards(
        config,
        dashboard["id"],
        [
            {"id": -1, "card_id": cards[0]["id"], "row": 0, "col": 0, "size_x": 24, "size_y": 8, "parameter_mappings": [], "series": []},
            {"id": -2, "card_id": cards[1]["id"], "row": 8, "col": 0, "size_x": 24, "size_y": 8, "parameter_mappings": [], "series": []},
        ],
    )
    print(json.dumps({"dashboard_id": dashboard["id"], "dashboard_name": dashboard["name"], "card_ids": [c["id"] for c in cards]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
