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


def template_tags() -> Dict[str, Any]:
    return {
        "business_unit": {
            "id": "business-unit",
            "name": "business_unit",
            "display-name": "Бизнес-юнит",
            "type": "dimension",
            "widget-type": "category",
            "dimension": ["field", 1523, None],
            "required": False,
        },
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
            "id": "business-unit",
            "name": "Бизнес-юнит",
            "slug": "business_unit",
            "type": "category",
            "sectionId": "category",
        },
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


def put_dashboard_cards(config: MetabaseConfig, dashboard_id: int, cards: list[Dict[str, Any]]) -> Any:
    return api_request(config, "PUT", f"/api/dashboard/{dashboard_id}/cards", {"cards": cards})


def dashboard_query() -> str:
    return """
WITH filtered AS (
    SELECT *
    FROM show_performance_dashboard_base
    WHERE 1 = 1
      [[AND period_end >= {{date_from}}]]
      [[AND period_start <= {{date_to}}]]
      [[AND {{business_unit}}]]
),
show_rollup AS (
    SELECT
        show_name,
        SUM(website_visits)::numeric AS website_visits,
        SUM(number_of_orders)::numeric AS number_of_orders,
        SUM(number_of_tickets)::numeric AS number_of_tickets,
        SUM(number_of_shows)::numeric AS number_of_shows,
        SUM(number_of_show_visitors)::numeric AS number_of_show_visitors,
        SUM(number_of_show_rating_responses)::numeric AS number_of_show_rating_responses,
        SUM(sum_of_post_show_ratings)::numeric AS sum_of_post_show_ratings,
        SUM(revenue)::numeric AS revenue,
        SUM(costs_salary_variable)::numeric AS costs_salary_variable
    FROM filtered
    GROUP BY show_name
),
metric_rows AS (
    SELECT
        10 AS row_order,
        'Количество визитов на сайте'::text AS metric_name,
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = '22''07' THEN website_visits END), 0), 'FM999999990') AS "22'07",
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'ВДОХ' THEN website_visits END), 0), 'FM999999990') AS "ВДОХ",
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN website_visits END), 0), 'FM999999990') AS "До свадьбы доживёт",
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Загадка Амулета' THEN website_visits END), 0), 'FM999999990') AS "Загадка Амулета",
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Иное место' THEN website_visits END), 0), 'FM999999990') AS "Иное место",
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN website_visits END), 0), 'FM999999990') AS "Ответ Гиппократа",
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN website_visits END), 0), 'FM999999990') AS "Поезд, Чехов, два орла",
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Судный день' THEN website_visits END), 0), 'FM999999990') AS "Судный день"
    FROM show_rollup
    UNION ALL
    SELECT
        20,
        'Количество заказов',
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = '22''07' THEN number_of_orders END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'ВДОХ' THEN number_of_orders END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN number_of_orders END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Загадка Амулета' THEN number_of_orders END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Иное место' THEN number_of_orders END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN number_of_orders END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN number_of_orders END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Судный день' THEN number_of_orders END), 0), 'FM999999990')
    FROM show_rollup
    UNION ALL
    SELECT
        30,
        'Конверсия визит-заказ',
        CASE WHEN MAX(CASE WHEN show_name = '22''07' THEN website_visits END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = '22''07' THEN number_of_orders / NULLIF(website_visits, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'ВДОХ' THEN website_visits END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'ВДОХ' THEN number_of_orders / NULLIF(website_visits, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN website_visits END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN number_of_orders / NULLIF(website_visits, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'Загадка Амулета' THEN website_visits END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Загадка Амулета' THEN number_of_orders / NULLIF(website_visits, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'Иное место' THEN website_visits END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Иное место' THEN number_of_orders / NULLIF(website_visits, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN website_visits END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN number_of_orders / NULLIF(website_visits, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN website_visits END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN number_of_orders / NULLIF(website_visits, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'Судный день' THEN website_visits END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Судный день' THEN number_of_orders / NULLIF(website_visits, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END
    FROM show_rollup
    UNION ALL
    SELECT
        40,
        'Количество билетов',
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = '22''07' THEN number_of_tickets END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'ВДОХ' THEN number_of_tickets END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN number_of_tickets END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Загадка Амулета' THEN number_of_tickets END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Иное место' THEN number_of_tickets END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN number_of_tickets END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN number_of_tickets END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Судный день' THEN number_of_tickets END), 0), 'FM999999990')
    FROM show_rollup
    UNION ALL
    SELECT
        50,
        'Среднее билетов в заказе',
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = '22''07' THEN number_of_tickets / NULLIF(number_of_orders, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'ВДОХ' THEN number_of_tickets / NULLIF(number_of_orders, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN number_of_tickets / NULLIF(number_of_orders, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Загадка Амулета' THEN number_of_tickets / NULLIF(number_of_orders, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Иное место' THEN number_of_tickets / NULLIF(number_of_orders, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN number_of_tickets / NULLIF(number_of_orders, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN number_of_tickets / NULLIF(number_of_orders, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Судный день' THEN number_of_tickets / NULLIF(number_of_orders, 0) END), 2), 'FM999999990.00')
    FROM show_rollup
    UNION ALL
    SELECT
        60,
        'Всего шоу',
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = '22''07' THEN number_of_shows END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'ВДОХ' THEN number_of_shows END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN number_of_shows END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Загадка Амулета' THEN number_of_shows END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Иное место' THEN number_of_shows END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN number_of_shows END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN number_of_shows END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Судный день' THEN number_of_shows END), 0), 'FM999999990')
    FROM show_rollup
    UNION ALL
    SELECT
        70,
        'Всего зрителей по факту',
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = '22''07' THEN number_of_show_visitors END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'ВДОХ' THEN number_of_show_visitors END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN number_of_show_visitors END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Загадка Амулета' THEN number_of_show_visitors END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Иное место' THEN number_of_show_visitors END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN number_of_show_visitors END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN number_of_show_visitors END), 0), 'FM999999990'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Судный день' THEN number_of_show_visitors END), 0), 'FM999999990')
    FROM show_rollup
    UNION ALL
    SELECT
        80,
        'Средняя загрузка факт',
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = '22''07' THEN number_of_show_visitors / NULLIF(number_of_shows, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'ВДОХ' THEN number_of_show_visitors / NULLIF(number_of_shows, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN number_of_show_visitors / NULLIF(number_of_shows, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Загадка Амулета' THEN number_of_show_visitors / NULLIF(number_of_shows, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Иное место' THEN number_of_show_visitors / NULLIF(number_of_shows, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN number_of_show_visitors / NULLIF(number_of_shows, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN number_of_show_visitors / NULLIF(number_of_shows, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Судный день' THEN number_of_show_visitors / NULLIF(number_of_shows, 0) END), 2), 'FM999999990.00')
    FROM show_rollup
    UNION ALL
    SELECT
        90,
        'Средняя оценка по опросам',
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = '22''07' THEN sum_of_post_show_ratings / NULLIF(number_of_show_rating_responses, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'ВДОХ' THEN sum_of_post_show_ratings / NULLIF(number_of_show_rating_responses, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN sum_of_post_show_ratings / NULLIF(number_of_show_rating_responses, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Загадка Амулета' THEN sum_of_post_show_ratings / NULLIF(number_of_show_rating_responses, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Иное место' THEN sum_of_post_show_ratings / NULLIF(number_of_show_rating_responses, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN sum_of_post_show_ratings / NULLIF(number_of_show_rating_responses, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN sum_of_post_show_ratings / NULLIF(number_of_show_rating_responses, 0) END), 2), 'FM999999990.00'),
        TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Судный день' THEN sum_of_post_show_ratings / NULLIF(number_of_show_rating_responses, 0) END), 2), 'FM999999990.00')
    FROM show_rollup
    UNION ALL
    SELECT
        100,
        'Выручка от спектакля',
        REPLACE(TO_CHAR(ROUND(MAX(CASE WHEN show_name = '22''07' THEN revenue END), 0), 'FM999G999G999G990'), ',', ' ') || ' р.',
        REPLACE(TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'ВДОХ' THEN revenue END), 0), 'FM999G999G999G990'), ',', ' ') || ' р.',
        REPLACE(TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN revenue END), 0), 'FM999G999G999G990'), ',', ' ') || ' р.',
        REPLACE(TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Загадка Амулета' THEN revenue END), 0), 'FM999G999G999G990'), ',', ' ') || ' р.',
        REPLACE(TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Иное место' THEN revenue END), 0), 'FM999G999G999G990'), ',', ' ') || ' р.',
        REPLACE(TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN revenue END), 0), 'FM999G999G999G990'), ',', ' ') || ' р.',
        REPLACE(TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN revenue END), 0), 'FM999G999G999G990'), ',', ' ') || ' р.',
        REPLACE(TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Судный день' THEN revenue END), 0), 'FM999G999G999G990'), ',', ' ') || ' р.'
    FROM show_rollup
    UNION ALL
    SELECT
        110,
        'Доля ЗП актеров в выручке',
        CASE WHEN MAX(CASE WHEN show_name = '22''07' THEN revenue END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = '22''07' THEN costs_salary_variable / NULLIF(revenue, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'ВДОХ' THEN revenue END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'ВДОХ' THEN costs_salary_variable / NULLIF(revenue, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN revenue END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'До свадьбы доживёт' THEN costs_salary_variable / NULLIF(revenue, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'Загадка Амулета' THEN revenue END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Загадка Амулета' THEN costs_salary_variable / NULLIF(revenue, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'Иное место' THEN revenue END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Иное место' THEN costs_salary_variable / NULLIF(revenue, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN revenue END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Ответ Гиппократа' THEN costs_salary_variable / NULLIF(revenue, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN revenue END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Поезд, Чехов, два орла' THEN costs_salary_variable / NULLIF(revenue, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END,
        CASE WHEN MAX(CASE WHEN show_name = 'Судный день' THEN revenue END) > 0
            THEN TO_CHAR(ROUND(MAX(CASE WHEN show_name = 'Судный день' THEN costs_salary_variable / NULLIF(revenue, 0) * 100 END), 2), 'FM999999990.00') || '%'
            ELSE NULL END
    FROM show_rollup
)
SELECT
    metric_name AS "Метрика",
    "22'07",
    "ВДОХ",
    "До свадьбы доживёт",
    "Загадка Амулета",
    "Иное место",
    "Ответ Гиппократа",
    "Поезд, Чехов, два орла",
    "Судный день"
FROM metric_rows
ORDER BY row_order;
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
        "Спектакли — эффективность",
        "Сводка по спектаклям с фильтрами по периоду и бизнес-юниту. Пустой фильтр бизнес-юнита означает оба юнита.",
    )
    card = create_card(
        config,
        args.metabase_database_id,
        collection_id,
        "Спектакли — эффективность",
        dashboard_query(),
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
                "size_y": 16,
                "parameter_mappings": [
                    {
                        "parameter_id": "business-unit",
                        "card_id": card["id"],
                        "target": ["dimension", ["template-tag", "business_unit"]],
                    },
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
                "collection_id": collection_id,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
