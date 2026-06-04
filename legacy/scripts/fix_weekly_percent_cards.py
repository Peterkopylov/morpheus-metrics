#!/usr/bin/env python3
import argparse
import json
from typing import Any, Dict, Iterable, List, Optional
from urllib import error, request


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


def fix_query(query: str) -> str:
    if "metric_value / 100.0 AS metric_value" in query:
        return query
    return query.replace(
        "    metric_value\nFROM weekly_metrics_yoy_series_6w",
        "    metric_value / 100.0 AS metric_value\nFROM weekly_metrics_yoy_series_6w",
    )


def dashboard_cards(base_url: str, api_key: str, dashboard_ids: Iterable[int]) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for dashboard_id in dashboard_ids:
        dashboard = api_request(base_url, api_key, "GET", f"/api/dashboard/{dashboard_id}")
        for dashcard in dashboard.get("dashcards", []):
            card = dashcard.get("card") or {}
            if card:
                cards.append(card)
    return cards


def is_percent_card(card: Dict[str, Any]) -> bool:
    column_settings = (card.get("visualization_settings") or {}).get("column_settings") or {}
    metric_settings = column_settings.get("[\"name\",\"metric_value\"]") or {}
    return metric_settings.get("number_style") == "percent"


def update_card(base_url: str, api_key: str, card: Dict[str, Any], new_query: str) -> None:
    dataset_query = card["dataset_query"]
    if "native" in dataset_query:
        dataset_query["native"]["query"] = new_query
    else:
        dataset_query["stages"][0]["native"] = new_query
    payload = {
        "name": card["name"],
        "display": card["display"],
        "dataset_query": dataset_query,
        "visualization_settings": card.get("visualization_settings") or {},
        "collection_id": card.get("collection_id"),
        "description": card.get("description"),
    }
    api_request(base_url, api_key, "PUT", f"/api/card/{card['id']}", payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--dashboard-id", type=int, action="append", required=True)
    args = parser.parse_args()

    updated = []
    for card in dashboard_cards(args.metabase_url, args.metabase_api_key, args.dashboard_id):
        if not is_percent_card(card):
            continue
        dataset_query = card.get("dataset_query") or {}
        if "native" in dataset_query:
            query = (dataset_query.get("native") or {}).get("query") or ""
        else:
            query = ((dataset_query.get("stages") or [{}])[0].get("native")) or ""
        new_query = fix_query(query)
        if new_query == query:
            continue
        update_card(args.metabase_url, args.metabase_api_key, card, new_query)
        updated.append({"card_id": card["id"], "name": card["name"]})

    print(json.dumps(updated, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
