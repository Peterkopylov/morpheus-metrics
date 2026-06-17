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


def template_tags() -> Dict[str, Any]:
    return {
        "date_from": {
            "id": "date-from",
            "name": "date_from",
            "display-name": "Ingestion date from",
            "type": "date",
            "required": False,
        },
        "date_to": {
            "id": "date-to",
            "name": "date_to",
            "display-name": "Ingestion date to",
            "type": "date",
            "required": False,
        },
    }


def dashboard_parameters() -> list[Dict[str, Any]]:
    return [
        {
            "id": "date-from",
            "name": "Дата ingestion c",
            "slug": "date_from",
            "type": "date/single",
            "sectionId": "date",
        },
        {
            "id": "date-to",
            "name": "Дата ingestion по",
            "slug": "date_to",
            "type": "date/single",
            "sectionId": "date",
        },
    ]


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
            "native": {
                "query": query,
                "template-tags": template_tags(),
            },
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
        "parameters": dashboard_parameters(),
    }
    return api_request(config, "POST", "/api/dashboard", payload)


def put_dashboard_cards(config: MetabaseConfig, dashboard_id: int, cards) -> Any:
    return api_request(config, "PUT", f"/api/dashboard/{dashboard_id}/cards", {"cards": cards})


def period_query() -> str:
    return """
WITH bounds AS (
    SELECT
        COALESCE(
            [[ {{date_from}}::date, ]]
            (SELECT MIN(ingestion_date) FROM fact_ingestion_technical_monitor)
        ) AS date_from,
        COALESCE(
            [[ {{date_to}}::date, ]]
            (SELECT MAX(ingestion_date) FROM fact_ingestion_technical_monitor)
        ) AS date_to
)
SELECT
    'Диапазон ingestion' AS "Показатель",
    TO_CHAR((SELECT date_from FROM bounds), 'DD.MM.YYYY')
    || ' - ' ||
    TO_CHAR((SELECT date_to FROM bounds), 'DD.MM.YYYY') AS "Значение";
""".strip()


def matrix_query() -> str:
    return """
SELECT
    ingestion_date AS "Дата ingestion",
    cadence_label AS "Контур",
    execution_mode AS "Режим",
    amo_success_pct / 100.0 AS "amo",
    erp_success_pct / 100.0 AS "erp",
    yandex_success_pct / 100.0 AS "yandex"
FROM fact_ingestion_technical_monitor
WHERE 1 = 1
  [[AND ingestion_date >= {{date_from}}]]
  [[AND ingestion_date <= {{date_to}}]]
ORDER BY ingestion_date DESC, cadence_label, execution_mode;
""".strip()


def detail_query() -> str:
    return """
SELECT
    ingestion_date AS "Дата ingestion",
    cadence_label AS "Контур",
    execution_mode AS "Режим",
    contour_period_start AS "Период start",
    contour_period_end AS "Период end",

    amo_loaded_fact_rows AS "amo loaded",
    amo_expected_fact_rows AS "amo expected",
    amo_success_pct / 100.0 AS "amo %",
    amo_attempted_step_count AS "amo steps",
    amo_successful_step_count AS "amo ok",
    amo_failed_step_count AS "amo failed",
    amo_pending_step_count AS "amo pending",

    erp_loaded_fact_rows AS "erp loaded",
    erp_expected_fact_rows AS "erp expected",
    erp_success_pct / 100.0 AS "erp %",
    erp_attempted_step_count AS "erp steps",
    erp_successful_step_count AS "erp ok",
    erp_failed_step_count AS "erp failed",
    erp_pending_step_count AS "erp pending",

    yandex_loaded_fact_rows AS "yandex loaded",
    yandex_expected_fact_rows AS "yandex expected",
    yandex_success_pct / 100.0 AS "yandex %",
    yandex_attempted_step_count AS "yandex steps",
    yandex_successful_step_count AS "yandex ok",
    yandex_failed_step_count AS "yandex failed",
    yandex_pending_step_count AS "yandex pending"
FROM fact_ingestion_technical_monitor
WHERE 1 = 1
  [[AND ingestion_date >= {{date_from}}]]
  [[AND ingestion_date <= {{date_to}}]]
ORDER BY ingestion_date DESC, cadence_label, execution_mode;
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
        "Fact Ingestion Technical Monitor",
        "Technical monitor for weekly/monthly fact ingestion runs with ingestion-date filter and source-level success percentages.",
    )

    cards = [
        create_card(config, args.metabase_database_id, collection_id, "Fact Ingestion Technical Monitor — Period", period_query()),
        create_card(config, args.metabase_database_id, collection_id, "Fact Ingestion Technical Monitor — Matrix", matrix_query()),
        create_card(config, args.metabase_database_id, collection_id, "Fact Ingestion Technical Monitor — Detail", detail_query()),
    ]

    put_dashboard_cards(
        config,
        dashboard["id"],
        [
            {
                "id": -1,
                "card_id": cards[0]["id"],
                "row": 0,
                "col": 0,
                "size_x": 24,
                "size_y": 3,
                "parameter_mappings": [
                    {
                        "parameter_id": "date-from",
                        "card_id": cards[0]["id"],
                        "target": ["variable", ["template-tag", "date_from"]],
                    },
                    {
                        "parameter_id": "date-to",
                        "card_id": cards[0]["id"],
                        "target": ["variable", ["template-tag", "date_to"]],
                    },
                ],
                "series": [],
            },
            {
                "id": -2,
                "card_id": cards[1]["id"],
                "row": 3,
                "col": 0,
                "size_x": 24,
                "size_y": 14,
                "parameter_mappings": [
                    {
                        "parameter_id": "date-from",
                        "card_id": cards[1]["id"],
                        "target": ["variable", ["template-tag", "date_from"]],
                    },
                    {
                        "parameter_id": "date-to",
                        "card_id": cards[1]["id"],
                        "target": ["variable", ["template-tag", "date_to"]],
                    },
                ],
                "series": [],
            },
            {
                "id": -3,
                "card_id": cards[2]["id"],
                "row": 17,
                "col": 0,
                "size_x": 24,
                "size_y": 16,
                "parameter_mappings": [
                    {
                        "parameter_id": "date-from",
                        "card_id": cards[2]["id"],
                        "target": ["variable", ["template-tag", "date_from"]],
                    },
                    {
                        "parameter_id": "date-to",
                        "card_id": cards[2]["id"],
                        "target": ["variable", ["template-tag", "date_to"]],
                    },
                ],
                "series": [],
            },
        ],
    )

    print(
        json.dumps(
            {
                "dashboard_id": dashboard["id"],
                "dashboard_name": dashboard["name"],
                "card_ids": [card["id"] for card in cards],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
