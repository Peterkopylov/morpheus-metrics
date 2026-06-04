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


def list_collections(config: MetabaseConfig) -> List[Dict[str, Any]]:
    return api_request(config, "GET", "/api/collection")


def ensure_collection(config: MetabaseConfig, name: str, parent_id: Optional[int]) -> Dict[str, Any]:
    for collection in list_collections(config):
        if collection.get("name") == name and collection.get("parent_id") == parent_id:
            return collection
    payload: Dict[str, Any] = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    return api_request(config, "POST", "/api/collection", payload)


def fetch_dashboard(config: MetabaseConfig, dashboard_id: int) -> Dict[str, Any]:
    return api_request(config, "GET", f"/api/dashboard/{dashboard_id}")


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--dashboard-id", type=int, action="append", required=True)
    parser.add_argument("--target-collection-name", required=True)
    parser.add_argument("--parent-collection-id", type=int)
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    target_collection = ensure_collection(config, args.target_collection_name, args.parent_collection_id)

    moved = []
    seen_card_ids = set()
    for dashboard_id in args.dashboard_id:
        dashboard = fetch_dashboard(config, dashboard_id)
        for dashcard in dashboard.get("dashcards", []):
            card = dashcard.get("card") or {}
            card_id = card.get("id")
            if not card_id or card_id in seen_card_ids:
                continue
            seen_card_ids.add(card_id)
            update_card_collection(config, card, int(target_collection["id"]))
            moved.append(
                {
                    "dashboard_id": dashboard_id,
                    "card_id": card_id,
                    "card_name": card.get("name"),
                    "target_collection_id": target_collection["id"],
                    "target_collection_name": target_collection["name"],
                }
            )

    print(
        json.dumps(
            {
                "target_collection_id": target_collection["id"],
                "target_collection_name": target_collection["name"],
                "moved_cards": moved,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
