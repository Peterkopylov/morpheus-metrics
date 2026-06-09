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


def create_card(config: MetabaseConfig, database_id: int, name: str, query: str) -> Dict[str, Any]:
    payload = {
        "name": name,
        "display": "table",
        "collection_id": None,
        "dataset_query": {
            "type": "native",
            "native": {"query": query, "template-tags": {}},
            "database": database_id,
        },
        "visualization_settings": {},
    }
    return api_request(config, "POST", "/api/card", payload)


def create_dashboard(config: MetabaseConfig, name: str, description: str) -> Dict[str, Any]:
    payload = {
        "name": name,
        "description": description,
        "collection_id": None,
        "parameters": [],
    }
    return api_request(config, "POST", "/api/dashboard", payload)


def put_dashboard_cards(config: MetabaseConfig, dashboard_id: int, cards) -> Any:
    return api_request(config, "PUT", f"/api/dashboard/{dashboard_id}/cards", {"cards": cards})


def query(unit: str) -> str:
    final_occupancy_pct = {
        "b2c_moscow": 56.7,
        "b2c_spb": 52.4,
    }[unit]
    return f"""
WITH show_codes AS (
    SELECT
        as_of_msk,
        event_title,
        show_start,
        tickets_count,
        sold_tickets_orders,
        CASE event_title
            WHEN 'Ответ Гиппократа' THEN 'ОГ'
            WHEN 'До свадьбы доживёт' THEN 'ДСД'
            WHEN 'Судный день' THEN 'СД'
            WHEN '22''07' THEN '22''07'
            WHEN 'ВДОХ' THEN 'В'
            WHEN 'Иное место' THEN 'ИМ'
            WHEN 'Загадка Амулета' THEN 'ЗА'
            ELSE event_title
        END AS show_code
    FROM tmp_erp_sellout_next_30d_snapshot
    WHERE unit = '{unit}'
),
daily AS (
    SELECT
        show_date,
        as_of_date,
        show_code,
        COUNT(*) AS seance_count,
        SUM(sold_tickets_orders) AS sold_tickets,
        SUM(tickets_count) AS max_tickets
    FROM (
        SELECT
            (as_of_msk AT TIME ZONE 'Europe/Moscow')::date AS as_of_date,
            (show_start AT TIME ZONE 'Europe/Moscow')::date AS show_date,
            show_code,
            sold_tickets_orders,
            tickets_count
        FROM show_codes
    ) s
    GROUP BY 1, 2, 3
),
daily_total AS (
    SELECT
        show_date,
        as_of_date,
        SUM(sold_tickets) AS sold_tickets_total,
        SUM(max_tickets) AS max_tickets_total,
        (show_date - as_of_date) AS days_out
    FROM daily
    GROUP BY 1, 2
),
daily_total_with_norm AS (
    SELECT
        *,
        (
        CASE
            WHEN days_out <= 0 THEN 100.0
            WHEN days_out = 1 THEN 84.4
            WHEN days_out = 2 THEN 73.0
            WHEN days_out = 3 THEN 64.2
            WHEN days_out = 4 THEN 58.0
            WHEN days_out = 5 THEN 51.9
            WHEN days_out = 6 THEN 45.7
            WHEN days_out = 7 THEN 39.5
            WHEN days_out = 8 THEN 36.6
            WHEN days_out = 9 THEN 33.7
            WHEN days_out = 10 THEN 30.8
            WHEN days_out = 11 THEN 27.9
            WHEN days_out = 12 THEN 25.0
            WHEN days_out = 13 THEN 22.1
            WHEN days_out = 14 THEN 19.2
            WHEN days_out = 15 THEN 18.2
            WHEN days_out = 16 THEN 17.2
            WHEN days_out = 17 THEN 16.2
            WHEN days_out = 18 THEN 15.2
            WHEN days_out = 19 THEN 14.1
            WHEN days_out = 20 THEN 13.1
            WHEN days_out = 21 THEN 12.1
            WHEN days_out = 22 THEN 11.1
            WHEN days_out = 23 THEN 10.1
            WHEN days_out = 24 THEN 9.1
            WHEN days_out = 25 THEN 8.1
            WHEN days_out = 26 THEN 7.1
            WHEN days_out = 27 THEN 6.0
            WHEN days_out = 28 THEN 5.0
            WHEN days_out = 29 THEN 4.0
            WHEN days_out >= 30 THEN 3.0
        END
        ) * {final_occupancy_pct} / 100.0 AS booking_norm_pct
    FROM daily_total
)
SELECT
    TO_CHAR(show_date, 'DD.MM.YYYY')
        || ' (' ||
        CASE EXTRACT(ISODOW FROM show_date)
            WHEN 1 THEN 'пн'
            WHEN 2 THEN 'вт'
            WHEN 3 THEN 'ср'
            WHEN 4 THEN 'чт'
            WHEN 5 THEN 'пт'
            WHEN 6 THEN 'сб'
            WHEN 7 THEN 'вс'
        END
        || ')' AS "Дата",
    TO_CHAR(ROUND(booking_norm_pct, 0), 'FM990') || '%' AS "Норма",
    CASE
        WHEN (
            (100.0 * sold_tickets_total::numeric / NULLIF(max_tickets_total, 0)) - booking_norm_pct
        ) / NULLIF(booking_norm_pct, 0) > -0.20
            THEN '🟢 '
        ELSE '🔴 '
    END
    || TO_CHAR(
        ROUND(100.0 * sold_tickets_total::numeric / NULLIF(max_tickets_total, 0), 0),
        'FM990'
    ) || '%' AS "Средняя",
    MAX(CASE WHEN show_code = 'ОГ' THEN seance_count END) AS "ОГ с",
    MAX(CASE WHEN show_code = 'ОГ' THEN TO_CHAR(ROUND(100.0 * sold_tickets::numeric / NULLIF(max_tickets, 0), 0), 'FM990') || '%' END) AS "ОГ%",
    MAX(CASE WHEN show_code = 'ДСД' THEN seance_count END) AS "ДСД с",
    MAX(CASE WHEN show_code = 'ДСД' THEN TO_CHAR(ROUND(100.0 * sold_tickets::numeric / NULLIF(max_tickets, 0), 0), 'FM990') || '%' END) AS "ДСД%",
    MAX(CASE WHEN show_code = 'СД' THEN seance_count END) AS "СД с",
    MAX(CASE WHEN show_code = 'СД' THEN TO_CHAR(ROUND(100.0 * sold_tickets::numeric / NULLIF(max_tickets, 0), 0), 'FM990') || '%' END) AS "СД%",
    MAX(CASE WHEN show_code = '22''07' THEN seance_count END) AS "22'07 с",
    MAX(CASE WHEN show_code = '22''07' THEN TO_CHAR(ROUND(100.0 * sold_tickets::numeric / NULLIF(max_tickets, 0), 0), 'FM990') || '%' END) AS "22'07%",
    MAX(CASE WHEN show_code = 'В' THEN seance_count END) AS "В с",
    MAX(CASE WHEN show_code = 'В' THEN TO_CHAR(ROUND(100.0 * sold_tickets::numeric / NULLIF(max_tickets, 0), 0), 'FM990') || '%' END) AS "В%",
    MAX(CASE WHEN show_code = 'ИМ' THEN seance_count END) AS "ИМ с",
    MAX(CASE WHEN show_code = 'ИМ' THEN TO_CHAR(ROUND(100.0 * sold_tickets::numeric / NULLIF(max_tickets, 0), 0), 'FM990') || '%' END) AS "ИМ%",
    MAX(CASE WHEN show_code = 'ЗА' THEN seance_count END) AS "ЗА с",
    MAX(CASE WHEN show_code = 'ЗА' THEN TO_CHAR(ROUND(100.0 * sold_tickets::numeric / NULLIF(max_tickets, 0), 0), 'FM990') || '%' END) AS "ЗА%"
FROM daily
JOIN daily_total_with_norm USING (show_date, as_of_date)
GROUP BY show_date
    , booking_norm_pct, sold_tickets_total, max_tickets_total
ORDER BY show_date;
""".strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--metabase-database-id", type=int, required=True)
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    dashboard = create_dashboard(
        config,
        "TEMP ERP Sellout Next 30 Days",
        "Temporary prototype dashboard for ticket sellout percentages over the next 30 days from ERP future shows.",
    )
    cards = [
        create_card(config, args.metabase_database_id, "TEMP ERP Sellout Next 30 Days Moscow", query("b2c_moscow")),
        create_card(config, args.metabase_database_id, "TEMP ERP Sellout Next 30 Days SPB", query("b2c_spb")),
    ]
    put_dashboard_cards(
        config,
        dashboard["id"],
        [
            {"id": -1, "card_id": cards[0]["id"], "row": 0, "col": 0, "size_x": 24, "size_y": 15, "parameter_mappings": [], "series": []},
            {"id": -2, "card_id": cards[1]["id"], "row": 15, "col": 0, "size_x": 24, "size_y": 15, "parameter_mappings": [], "series": []},
        ],
    )
    print(json.dumps({"dashboard_id": dashboard["id"], "dashboard_name": dashboard["name"], "card_ids": [c["id"] for c in cards]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
