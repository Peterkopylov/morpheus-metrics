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


def period_query() -> str:
    return """
WITH bounds AS (
    SELECT
        COALESCE(
            [[ {{date_from}}::date, ]]
            (SELECT MIN(period_start) FROM weekly_marketing_operational_latest)
        ) AS date_from,
        COALESCE(
            [[ {{date_to}}::date, ]]
            (SELECT MAX(period_start) FROM weekly_marketing_operational_latest)
        ) AS date_to
),
filtered AS (
    SELECT *
    FROM weekly_marketing_operational_latest
    WHERE 1 = 1
      [[AND period_start >= {{date_from}}]]
      [[AND period_start <= {{date_to}}]]
)
SELECT
    DISTINCT 'Период отчета' AS "Показатель",
    TO_CHAR((SELECT date_from FROM bounds), 'DD.MM.YYYY') || ' - ' || TO_CHAR((SELECT date_to FROM bounds), 'DD.MM.YYYY') AS "Значение"
FROM filtered
WHERE channel_name = 'total';
""".strip()


def dashboard_query() -> str:
    return """
WITH filtered AS (
    SELECT *
    FROM weekly_marketing_operational_latest
    WHERE 1 = 1
      [[AND period_start >= {{date_from}}]]
      [[AND period_start <= {{date_to}}]]
),
rollup AS (
    SELECT
        business_unit_label,
        channel_label,
        channel_name,
        row_order,
        SUM(COALESCE(marketing_costs, 0))::numeric AS marketing_costs,
        SUM(COALESCE(website_visits, 0))::numeric AS website_visits,
        SUM(COALESCE(metrica_tracked_purchase_visits, 0))::numeric AS metrica_tracked_purchase_visits,
        SUM(COALESCE(estimated_channel_orders, 0))::numeric AS estimated_channel_orders,
        SUM(COALESCE(number_of_orders, 0))::numeric AS number_of_orders,
        SUM(COALESCE(number_of_tickets, 0))::numeric AS number_of_tickets,
        SUM(COALESCE(revenue, 0))::numeric AS revenue,
        SUM(COALESCE(attributed_revenue, 0))::numeric AS attributed_revenue,
        MIN(attributed_revenue_method) AS attributed_revenue_method,
        SUM(COALESCE(survey_source_response_count, 0))::numeric AS survey_source_response_count,
        SUM(COALESCE(survey_total_response_count, 0))::numeric AS survey_total_response_count
    FROM filtered
    GROUP BY business_unit_label, channel_label, channel_name, row_order
),
display_rows AS (
    SELECT *
    FROM rollup
    WHERE channel_name = 'total'
       OR (
            ABS(marketing_costs)
          + ABS(website_visits)
          + ABS(metrica_tracked_purchase_visits)
          + ABS(estimated_channel_orders)
          + ABS(number_of_orders)
          + ABS(number_of_tickets)
          + ABS(revenue)
          + ABS(attributed_revenue)
          + ABS(survey_source_response_count)
       ) > 0
)
SELECT
    business_unit_label AS "Город",
    channel_label AS "Канал",
    CASE
        WHEN marketing_costs IS NULL OR marketing_costs = 0 THEN NULL
        ELSE REPLACE(TO_CHAR(ROUND(marketing_costs::numeric, 0), 'FM999,999,999,990'), ',', ' ') || ' р.'
    END AS "Расходы",
    ROUND(website_visits::numeric, 0) AS "Визиты",
    NULLIF(ROUND(metrica_tracked_purchase_visits::numeric, 0), 0) AS "Metrica tracked orders",
    NULLIF(ROUND(estimated_channel_orders::numeric, 0), 0) AS "Estimated channel orders",
    CASE WHEN channel_name = 'total' THEN ROUND(number_of_orders::numeric, 0) ELSE NULL END AS "Заказы",
    CASE WHEN channel_name = 'total' THEN ROUND(number_of_tickets::numeric, 0) ELSE NULL END AS "Билеты",
    CASE
        WHEN attributed_revenue IS NULL OR attributed_revenue = 0 THEN NULL
        ELSE REPLACE(TO_CHAR(ROUND(attributed_revenue::numeric, 0), 'FM999,999,999,990'), ',', ' ') || ' р.'
    END AS "Revenue",
    attributed_revenue_method AS "Revenue method",
    CASE
        WHEN attributed_revenue IS NULL OR attributed_revenue = 0 THEN NULL
        ELSE TO_CHAR(ROUND((marketing_costs / attributed_revenue * 100)::numeric, 2), 'FM999999990.00') || '%'
    END AS "ДРР",
    CASE
        WHEN channel_name = 'total' THEN
            CASE WHEN survey_total_response_count = 0 THEN NULL ELSE '100.00%' END
        WHEN survey_total_response_count = 0 THEN NULL
        ELSE TO_CHAR(ROUND((survey_source_response_count / survey_total_response_count * 100)::numeric, 2), 'FM999999990.00') || '%'
    END AS "Доля канала по опросам"
FROM display_rows
ORDER BY business_unit_label, row_order, channel_label;
""".strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--metabase-database-id", type=int, required=True)
    parser.add_argument("--metabase-collection-id", type=int)
    parser.add_argument("--update-existing-dashboard-id", type=int)
    parser.add_argument("--allow-root", action="store_true")
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    collection_id = resolve_collection_id(args)
    dashboard_name = "Weekly Marketing Operational Monitor"
    dashboard_description = "Operational marketing monitor by channel for Moscow and SPB with selectable weekly period range."
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

    cards = [
        create_card(config, args.metabase_database_id, collection_id, "Weekly Marketing Operational Monitor — Period", period_query()),
        create_card(config, args.metabase_database_id, collection_id, "Weekly Marketing Operational Monitor — Москва и СПб", dashboard_query()),
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
                "size_y": 22,
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
        ],
    )

    print(json.dumps({"dashboard_id": dashboard["id"], "dashboard_name": dashboard["name"], "card_ids": [c["id"] for c in cards]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
