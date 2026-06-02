#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional
from urllib import error, request


@dataclass
class MetabaseConfig:
    base_url: str
    api_key: str


def api_request(
    config: MetabaseConfig,
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
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


def list_collections(config: MetabaseConfig) -> list[Dict[str, Any]]:
    return api_request(config, "GET", "/api/collection")


def find_collection(
    collections: Iterable[Dict[str, Any]],
    *,
    name: str,
    parent_id: Optional[int],
) -> Optional[Dict[str, Any]]:
    for collection in collections:
        if collection.get("name") == name and collection.get("parent_id") == parent_id:
            return collection
    return None


def ensure_collection_path(config: MetabaseConfig, path: str) -> Dict[str, Any]:
    current_parent_id: Optional[int] = None
    current_collection: Optional[Dict[str, Any]] = None

    for part in [segment.strip() for segment in path.split("/") if segment.strip()]:
        collections = list_collections(config)
        current_collection = find_collection(collections, name=part, parent_id=current_parent_id)
        if current_collection is None:
            payload: Dict[str, Any] = {"name": part}
            if current_parent_id is not None:
                payload["parent_id"] = current_parent_id
            current_collection = api_request(config, "POST", "/api/collection", payload)
        current_parent_id = int(current_collection["id"])

    if current_collection is None:
        raise RuntimeError(f"Invalid collection path: {path}")
    return current_collection


def fetch_dashboard(config: MetabaseConfig, dashboard_id: int) -> Dict[str, Any]:
    return api_request(config, "GET", f"/api/dashboard/{dashboard_id}")


def update_dashboard_collection(config: MetabaseConfig, dashboard: Dict[str, Any], collection_id: int) -> None:
    payload = {
        "name": dashboard["name"],
        "description": dashboard.get("description"),
        "collection_id": collection_id,
        "parameters": dashboard.get("parameters") or [],
    }
    api_request(config, "PUT", f"/api/dashboard/{dashboard['id']}", payload)


def update_card_collection(config: MetabaseConfig, card: Dict[str, Any], collection_id: int) -> None:
    payload = {
        "name": card["name"],
        "display": card["display"],
        "dataset_query": card["dataset_query"],
        "visualization_settings": card.get("visualization_settings") or {},
        "collection_id": collection_id,
        "description": card.get("description"),
    }
    api_request(config, "PUT", f"/api/card/{card['id']}", payload)


def parse_dashboard_args(values: list[str]) -> list[tuple[int, str]]:
    parsed: list[tuple[int, str]] = []
    for value in values:
        if ":" not in value:
            raise RuntimeError(f"Expected dashboard mapping in <id>:<collection/path> format, got: {value}")
        dashboard_id_raw, collection_path = value.split(":", 1)
        parsed.append((int(dashboard_id_raw), collection_path.strip()))
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument(
        "--dashboard-target",
        action="append",
        default=[],
        help="Dashboard relocation mapping in <dashboard_id>:<collection/path> format.",
    )
    parser.add_argument(
        "--cards-target-path",
        help="If set, moves all cards referenced by the selected dashboards into this collection path.",
    )
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    dashboard_targets = parse_dashboard_args(args.dashboard_target)
    target_collections = {
        path: ensure_collection_path(config, path)
        for path in {path for _, path in dashboard_targets}
    }
    cards_target = ensure_collection_path(config, args.cards_target_path) if args.cards_target_path else None

    moved_dashboards = []
    moved_cards = []
    seen_card_ids: set[int] = set()

    for dashboard_id, collection_path in dashboard_targets:
        dashboard = fetch_dashboard(config, dashboard_id)
        collection = target_collections[collection_path]
        update_dashboard_collection(config, dashboard, int(collection["id"]))
        moved_dashboards.append(
            {
                "dashboard_id": dashboard_id,
                "dashboard_name": dashboard.get("name"),
                "target_collection_id": collection["id"],
                "target_collection_path": collection_path,
            }
        )

        if cards_target is None:
            continue

        for dashcard in dashboard.get("dashcards", []):
            card = dashcard.get("card") or {}
            card_id = card.get("id")
            if not card_id or card_id in seen_card_ids:
                continue
            seen_card_ids.add(card_id)
            update_card_collection(config, card, int(cards_target["id"]))
            moved_cards.append(
                {
                    "dashboard_id": dashboard_id,
                    "card_id": card_id,
                    "card_name": card.get("name"),
                    "target_collection_id": cards_target["id"],
                    "target_collection_path": args.cards_target_path,
                }
            )

    print(
        json.dumps(
            {
                "moved_dashboards": moved_dashboards,
                "moved_cards": moved_cards,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
