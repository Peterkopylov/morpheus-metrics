#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import error, request


UNITS = {
    "b2c_moscow": "Москва",
    "b2c_spb": "СПб",
}

VALUE_MODES = {
    "attendance_pct": "attendance_pct",
    "average_guests": "average_guests",
}


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


def template_tags(show_name_field_id: int) -> Dict[str, Any]:
    return {
        "date_from": {
            "id": "date-from",
            "name": "date_from",
            "display-name": "Период с",
            "type": "date",
            "required": False,
        },
        "date_to": {
            "id": "date-to",
            "name": "date_to",
            "display-name": "Период по",
            "type": "date",
            "required": False,
        },
        "show_name": {
            "id": "show-name",
            "name": "show_name",
            "display-name": "Спектакль",
            "type": "dimension",
            "widget-type": "category",
            "dimension": ["field", show_name_field_id, None],
            "required": False,
        },
    }


def dashboard_parameters() -> list[Dict[str, Any]]:
    return [
        {
            "id": "date-from",
            "name": "Период с",
            "slug": "date_from",
            "type": "date/single",
            "sectionId": "date",
        },
        {
            "id": "date-to",
            "name": "Период по",
            "slug": "date_to",
            "type": "date/single",
            "sectionId": "date",
        },
        {
            "id": "show-name",
            "name": "Спектакль",
            "slug": "show_name",
            "type": "category",
            "sectionId": "category",
        },
    ]


def visualization_settings() -> Dict[str, Any]:
    return {}


def create_card(
    config: MetabaseConfig,
    database_id: int,
    collection_id: Optional[int],
    name: str,
    query: str,
    show_name_field_id: int,
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "display": "table",
        "collection_id": collection_id,
        "dataset_query": {
            "type": "native",
            "native": {
                "query": query,
                "template-tags": template_tags(show_name_field_id),
            },
            "database": database_id,
        },
        "visualization_settings": visualization_settings(),
    }
    return api_request(config, "POST", "/api/card", payload)


def update_card(
    config: MetabaseConfig,
    card_id: int,
    database_id: int,
    name: str,
    query: str,
    show_name_field_id: int,
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "display": "table",
        "dataset_query": {
            "type": "native",
            "native": {
                "query": query,
                "template-tags": template_tags(show_name_field_id),
            },
            "database": database_id,
        },
        "visualization_settings": visualization_settings(),
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
        "parameters": dashboard_parameters(),
    }
    return api_request(config, "POST", "/api/dashboard", payload)


def update_dashboard(
    config: MetabaseConfig,
    dashboard_id: int,
    name: str,
    description: str,
    collection_id: Optional[int],
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "description": description,
        "collection_id": collection_id,
        "parameters": dashboard_parameters(),
    }
    api_request(config, "PUT", f"/api/dashboard/{dashboard_id}", payload)
    return {"id": dashboard_id, "name": name}


def put_dashboard_cards(config: MetabaseConfig, dashboard_id: int, cards) -> Any:
    return api_request(config, "PUT", f"/api/dashboard/{dashboard_id}/cards", {"cards": cards})


def value_expression(
    guests_expr: str,
    capacity_expr: str,
    count_expr: str,
    value_mode: str,
) -> str:
    if value_mode == VALUE_MODES["average_guests"]:
        return f"""
    CASE
        WHEN {count_expr} = 0 THEN NULL
        ELSE TRIM(TRAILING '.' FROM TRIM(TRAILING '0' FROM ROUND({guests_expr}::numeric / {count_expr}, 1)::text)) || ' (' || {count_expr}::text || ')'
    END
""".rstrip()
    return f"""
    CASE
        WHEN {count_expr} = 0 OR {capacity_expr} IS NULL OR {capacity_expr} = 0 THEN NULL
        ELSE ROUND(100.0 * {guests_expr}::numeric / {capacity_expr}, 0)::int::text || '% (' || {count_expr}::text || ')'
    END
""".rstrip()


def dashboard_query(unit: str, value_mode: str) -> str:
    monday_value = value_expression("monday_guests", "monday_capacity", "monday_count", value_mode)
    tuesday_value = value_expression("tuesday_guests", "tuesday_capacity", "tuesday_count", value_mode)
    wednesday_value = value_expression("wednesday_guests", "wednesday_capacity", "wednesday_count", value_mode)
    thursday_value = value_expression("thursday_guests", "thursday_capacity", "thursday_count", value_mode)
    friday_value = value_expression("friday_guests", "friday_capacity", "friday_count", value_mode)
    saturday_value = value_expression("saturday_guests", "saturday_capacity", "saturday_count", value_mode)
    sunday_value = value_expression("sunday_guests", "sunday_capacity", "sunday_count", value_mode)
    return f"""
WITH filtered AS (
    SELECT *
    FROM show_slot_attendance_dashboard_base
    WHERE business_unit = '{unit}'
      [[AND seance_date >= {{{{date_from}}}}]]
      [[AND seance_date <= {{{{date_to}}}}]]
      [[AND {{{{show_name}}}}]]
),
rollup AS (
    SELECT
        slot_label,
        slot_order,
        SUM(guests_count) FILTER (WHERE iso_weekday = 1) AS monday_guests,
        SUM(capacity_tickets) FILTER (WHERE iso_weekday = 1) AS monday_capacity,
        COUNT(*) FILTER (WHERE iso_weekday = 1) AS monday_count,
        SUM(guests_count) FILTER (WHERE iso_weekday = 2) AS tuesday_guests,
        SUM(capacity_tickets) FILTER (WHERE iso_weekday = 2) AS tuesday_capacity,
        COUNT(*) FILTER (WHERE iso_weekday = 2) AS tuesday_count,
        SUM(guests_count) FILTER (WHERE iso_weekday = 3) AS wednesday_guests,
        SUM(capacity_tickets) FILTER (WHERE iso_weekday = 3) AS wednesday_capacity,
        COUNT(*) FILTER (WHERE iso_weekday = 3) AS wednesday_count,
        SUM(guests_count) FILTER (WHERE iso_weekday = 4) AS thursday_guests,
        SUM(capacity_tickets) FILTER (WHERE iso_weekday = 4) AS thursday_capacity,
        COUNT(*) FILTER (WHERE iso_weekday = 4) AS thursday_count,
        SUM(guests_count) FILTER (WHERE iso_weekday = 5) AS friday_guests,
        SUM(capacity_tickets) FILTER (WHERE iso_weekday = 5) AS friday_capacity,
        COUNT(*) FILTER (WHERE iso_weekday = 5) AS friday_count,
        SUM(guests_count) FILTER (WHERE iso_weekday = 6) AS saturday_guests,
        SUM(capacity_tickets) FILTER (WHERE iso_weekday = 6) AS saturday_capacity,
        COUNT(*) FILTER (WHERE iso_weekday = 6) AS saturday_count,
        SUM(guests_count) FILTER (WHERE iso_weekday = 7) AS sunday_guests,
        SUM(capacity_tickets) FILTER (WHERE iso_weekday = 7) AS sunday_capacity,
        COUNT(*) FILTER (WHERE iso_weekday = 7) AS sunday_count
    FROM filtered
    GROUP BY slot_label, slot_order
)
SELECT
    slot_label AS "Время",
    {monday_value} AS "1/пн",
    {tuesday_value} AS "2/вт",
    {wednesday_value} AS "3/ср",
    {thursday_value} AS "4/чт",
    {friday_value} AS "5/пт",
    {saturday_value} AS "6/сб",
    {sunday_value} AS "7/вск"
FROM rollup
ORDER BY slot_order, slot_label;
""".strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--metabase-database-id", type=int, required=True)
    parser.add_argument("--metabase-collection-id", type=int)
    parser.add_argument("--show-name-field-id", type=int, required=True)
    parser.add_argument("--unit", required=True, choices=sorted(UNITS))
    parser.add_argument("--value-mode", choices=sorted(VALUE_MODES), default=VALUE_MODES["attendance_pct"])
    parser.add_argument("--update-existing-dashboard-id", type=int)
    parser.add_argument("--update-existing-card-id", type=int)
    parser.add_argument("--allow-root", action="store_true")
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    collection_id = resolve_collection_id(args)
    city_label = UNITS[args.unit]
    if args.value_mode == VALUE_MODES["average_guests"]:
        dashboard_name = f"{city_label} — среднее число гостей по слотам"
        dashboard_description = (
            f"Public dashboard with average-guests-by-slot matrix for {city_label}. "
            "Values are computed as AVG(guests per show), with cancelled shows contributing zero guests, plus show count in parentheses."
        )
    else:
        dashboard_name = f"{city_label} — средняя посещаемость по слотам"
        dashboard_description = (
            f"Public dashboard with attendance-by-slot matrix for {city_label}. "
            "Values are computed as SUM(guests) / SUM(full seating) within the selected date range and show set."
        )
    query = dashboard_query(args.unit, args.value_mode)
    card_name = f"{dashboard_name} — matrix"

    if args.update_existing_card_id:
        card = update_card(
            config,
            args.update_existing_card_id,
            args.metabase_database_id,
            card_name,
            query,
            args.show_name_field_id,
        )
    else:
        card = create_card(
            config,
            args.metabase_database_id,
            collection_id,
            card_name,
            query,
            args.show_name_field_id,
        )

    if args.update_existing_dashboard_id:
        dashboard = update_dashboard(
            config,
            args.update_existing_dashboard_id,
            dashboard_name,
            dashboard_description,
            collection_id,
        )
    else:
        dashboard = create_dashboard(
            config,
            collection_id,
            dashboard_name,
            dashboard_description,
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
                "size_y": 18,
                "parameter_mappings": [
                    {
                        "parameter_id": "date-from",
                        "card_id": card["id"],
                        "target": ["variable", ["template-tag", "date_from"]],
                    },
                    {
                        "parameter_id": "date-to",
                        "card_id": card["id"],
                        "target": ["variable", ["template-tag", "date_to"]],
                    },
                    {
                        "parameter_id": "show-name",
                        "card_id": card["id"],
                        "target": ["dimension", ["template-tag", "show_name"]],
                    },
                ],
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
                "value_mode": args.value_mode,
                "show_name_field_id": args.show_name_field_id,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
