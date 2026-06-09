#!/usr/bin/env python3
from __future__ import annotations

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


def update_card(
    config: MetabaseConfig,
    card_id: int,
    database_id: int,
    name: str,
    query: str,
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "display": "table",
        "dataset_query": {
            "type": "native",
            "native": {"query": query, "template-tags": {}},
            "database": database_id,
        },
        "visualization_settings": {},
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


def query(unit: str, show_name: str) -> str:
    show_sql = show_name.replace("'", "''")
    return f"""
SELECT
    CASE EXTRACT(ISODOW FROM seance_start_msk)
        WHEN 1 THEN 'Пн'
        WHEN 2 THEN 'Вт'
        WHEN 3 THEN 'Ср'
        WHEN 4 THEN 'Чт'
        WHEN 5 THEN 'Пт'
        WHEN 6 THEN 'Сб'
        WHEN 7 THEN 'Вс'
    END AS "День недели",
    seance_label AS "Сеанс",
    bought_tickets_count AS "Количество купленных на него билетов",
    actual_tickets_count AS "Актуально на сеансе"
FROM tmp_erp_show_seance_buyout_snapshot
WHERE unit = '{unit}'
  AND show_name = '{show_sql}'
ORDER BY seance_start_msk;
""".strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--metabase-database-id", type=int, required=True)
    parser.add_argument("--show-name", required=True)
    parser.add_argument("--unit", default="b2c_moscow")
    parser.add_argument("--update-existing-card-id", type=int)
    parser.add_argument("--metabase-collection-id", type=int)
    parser.add_argument("--allow-root", action="store_true")
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    card_name = f"TEMP {args.show_name} — seance buyout"
    sql = query(args.unit, args.show_name)

    if args.update_existing_card_id:
        card = update_card(
            config,
            args.update_existing_card_id,
            args.metabase_database_id,
            card_name,
            sql,
        )
        print(
            json.dumps(
                {
                    "card_id": card["id"],
                    "card_name": card["name"],
                    "unit": args.unit,
                    "show_name": args.show_name,
                    "mode": "updated_existing_card",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    collection_id = resolve_collection_id(args)

    dashboard = create_dashboard(
        config,
        collection_id,
        f"TEMP Выкупленность по сеансам — {args.show_name}",
        "Temporary dashboard with future seance-level bought ticket counts for a selected show.",
    )
    card = create_card(
        config,
        args.metabase_database_id,
        collection_id,
        card_name,
        sql,
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
                "size_y": 12,
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
                "unit": args.unit,
                "show_name": args.show_name,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
