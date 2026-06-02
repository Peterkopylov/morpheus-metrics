#!/usr/bin/env python3
import argparse
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, request

import psycopg2


SERIES_ORDER = ["Последние 6 недель", "Те же недели год назад"]


def api_request(base_url: str, api_key: str, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    headers = {
        "x-api-key": api_key,
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


def fetch_metric_order(database_url: str) -> Dict[Tuple[str, str], int]:
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    unit,
                    metric_key,
                    MIN(row_order) AS metric_order
                FROM fact_metrics
                WHERE aggregation_level = 'week'
                  AND unit IN ('b2c_moscow', 'b2c_spb')
                  AND metric_key IS NOT NULL
                GROUP BY unit, metric_key
                """
            )
            return {(row[0], row[1]): int(row[2]) for row in cur.fetchall()}
    finally:
        conn.close()


def extract_query(card: Dict[str, Any]) -> str:
    dataset_query = card.get("dataset_query") or {}
    if "native" in dataset_query:
        return ((dataset_query.get("native") or {}).get("query")) or ""
    stages = dataset_query.get("stages") or []
    if stages:
        return stages[0].get("native") or ""
    return ""


def update_query(card: Dict[str, Any], new_query: str) -> None:
    dataset_query = card["dataset_query"]
    if "native" in dataset_query:
        dataset_query["native"]["query"] = new_query
    else:
        dataset_query["stages"][0]["native"] = new_query


def extract_unit_metric(query: str) -> Tuple[Optional[str], Optional[str]]:
    unit_match = re.search(r"WHERE unit = '([^']+)'", query)
    metric_match = re.search(r"AND metric_key = '([^']+)'", query)
    return (
        unit_match.group(1) if unit_match else None,
        metric_match.group(1) if metric_match else None,
    )


def ensure_percent_query(card: Dict[str, Any]) -> bool:
    settings = card.get("visualization_settings") or {}
    metric_settings = (settings.get("column_settings") or {}).get("[\"name\",\"metric_value\"]") or {}
    if metric_settings.get("number_style") != "percent":
        return False
    query = extract_query(card)
    new_query = query.replace(
        "    metric_value\nFROM weekly_metrics_yoy_series_6w",
        "    metric_value / 100.0 AS metric_value\nFROM weekly_metrics_yoy_series_6w",
    )
    if new_query == query:
        return False
    update_query(card, new_query)
    return True


def ensure_line_style(card: Dict[str, Any]) -> None:
    settings = dict(card.get("visualization_settings") or {})
    settings["graph.series_order"] = SERIES_ORDER
    series_settings = dict(settings.get("series_settings") or {})
    year_settings = dict(series_settings.get("Те же недели год назад") or {})
    year_settings["line.style"] = "dashed"
    series_settings["Те же недели год назад"] = year_settings
    settings["series_settings"] = series_settings
    card["visualization_settings"] = settings


def persist_card(base_url: str, api_key: str, card: Dict[str, Any]) -> None:
    payload = {
        "name": card["name"],
        "display": card["display"],
        "dataset_query": card["dataset_query"],
        "visualization_settings": card.get("visualization_settings") or {},
        "collection_id": card.get("collection_id"),
        "description": card.get("description"),
    }
    api_request(base_url, api_key, "PUT", f"/api/card/{card['id']}", payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--dashboard-id", type=int, action="append", required=True)
    args = parser.parse_args()

    metric_order_map = fetch_metric_order(args.database_url)
    results = []

    for dashboard_id in args.dashboard_id:
        dashboard = api_request(args.metabase_url, args.metabase_api_key, "GET", f"/api/dashboard/{dashboard_id}")
        dashcards = dashboard.get("dashcards", [])
        sortable: List[Tuple[int, str, Dict[str, Any]]] = []

        for dashcard in dashcards:
            card = dashcard.get("card") or {}
            if not card:
                continue
            ensure_percent_query(card)
            ensure_line_style(card)
            persist_card(args.metabase_url, args.metabase_api_key, card)

            unit, metric_key = extract_unit_metric(extract_query(card))
            metric_order = metric_order_map.get((unit or "", metric_key or ""), 999999)
            sortable.append((metric_order, card.get("name") or "", dashcard))

        sortable.sort(key=lambda item: (item[0], item[1]))
        layout_cards = []
        for idx, (_, _, dashcard) in enumerate(sortable):
            layout_cards.append(
                {
                    "id": dashcard["id"],
                    "card_id": dashcard["card_id"],
                    "row": (idx // 2) * 8,
                    "col": 0 if idx % 2 == 0 else 12,
                    "size_x": dashcard.get("size_x", 12),
                    "size_y": dashcard.get("size_y", 8),
                    "parameter_mappings": dashcard.get("parameter_mappings", []),
                    "series": dashcard.get("series", []),
                }
            )

        api_request(args.metabase_url, args.metabase_api_key, "PUT", f"/api/dashboard/{dashboard_id}/cards", {"cards": layout_cards})
        results.append({"dashboard_id": dashboard_id, "card_count": len(layout_cards)})

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
