#!/usr/bin/env python3
import argparse
import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

import psycopg2


@dataclass
class MetabaseConfig:
    base_url: str
    api_key: str


def api_request(config: MetabaseConfig, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{config.base_url.rstrip('/')}{path}"
    data = None
    headers = {
        "x-api-key": config.api_key,
        "Content-Type": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

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


def parse_month_arg(value: str) -> date:
    try:
        year_str, month_str = value.split("-", 1)
        return date(int(year_str), int(month_str), 1)
    except Exception as exc:  # pragma: no cover - cli parsing guard
        raise argparse.ArgumentTypeError(f"Invalid month '{value}', expected YYYY-MM") from exc


def get_latest_months(database_url: str, limit: int = 3) -> List[date]:
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT month_start
                FROM (
                    SELECT DISTINCT month_start
                    FROM planfact_pnl_test
                    WHERE month_start IS NOT NULL
                    ORDER BY month_start DESC
                    LIMIT %s
                ) x
                ORDER BY month_start
                """,
                (limit,),
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_months_in_range(database_url: str, month_start: date, month_end: date) -> List[date]:
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT month_start
                FROM planfact_pnl_test
                WHERE month_start BETWEEN %s AND %s
                ORDER BY month_start
                """,
                (month_start, month_end),
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def month_label(month_start: date) -> str:
    month_names = {
        1: "янв",
        2: "фев",
        3: "мар",
        4: "апр",
        5: "май",
        6: "июн",
        7: "июл",
        8: "авг",
        9: "сен",
        10: "окт",
        11: "ноя",
        12: "дек",
    }
    return f"{month_names[month_start.month]} '{str(month_start.year)[-2:]}"


def build_matrix_query(months: List[date]) -> str:
    month_columns = []
    for month_start in months:
        label = month_label(month_start)
        month_columns.append(
            f"ROUND(SUM(amount_for_display) FILTER (WHERE month_start = DATE '{month_start.isoformat()}')) AS \"{label}\""
        )
    month_sql = ",\n       ".join(month_columns)

    return f"""
WITH base AS (
    SELECT
        pnl_section,
        pnl_group,
        pnl_article,
        pnl_section_order,
        pnl_group_order,
        pnl_article_order,
        month_start,
        CASE
            WHEN pnl_section IN ('Основные расходы', 'Амортизация', 'Проценты по кредитам и займам', 'Налог на прибыль (доходы)', 'Дивиденды')
                THEN -amount_abs
            ELSE amount_abs
        END AS amount_for_display
    FROM planfact_pnl_test
),
section_rows AS (
    SELECT
        1 AS level,
        pnl_section_order AS section_sort,
        0 AS group_sort,
        0 AS article_sort,
        pnl_section AS row_label,
        NULL::text AS group_name,
        NULL::text AS article_name,
        {month_sql}
    FROM base
    GROUP BY pnl_section, pnl_section_order
),
group_rows AS (
    SELECT
        2 AS level,
        pnl_section_order AS section_sort,
        COALESCE(pnl_group_order, 0) AS group_sort,
        0 AS article_sort,
        '  ' || pnl_group AS row_label,
        pnl_group AS group_name,
        NULL::text AS article_name,
        {month_sql}
    FROM base
    GROUP BY pnl_section, pnl_section_order, pnl_group, pnl_group_order
),
article_rows AS (
    SELECT
        3 AS level,
        pnl_section_order AS section_sort,
        COALESCE(pnl_group_order, 0) AS group_sort,
        COALESCE(pnl_article_order, 0) AS article_sort,
        '    ' || pnl_article AS row_label,
        pnl_group AS group_name,
        pnl_article AS article_name,
        {month_sql}
    FROM base
    WHERE pnl_article IS NOT NULL
    GROUP BY pnl_section, pnl_section_order, pnl_group, pnl_group_order, pnl_article, pnl_article_order
)
SELECT row_label,
       {", ".join(f'"{month_label(m)}"' for m in months)}
FROM (
    SELECT * FROM section_rows
    UNION ALL
    SELECT * FROM group_rows
    UNION ALL
    SELECT * FROM article_rows
) q
ORDER BY section_sort, level, group_sort, article_sort, group_name NULLS FIRST, article_name NULLS FIRST, row_label;
""".strip()


def build_monthly_totals_query() -> str:
    return """
SELECT
    month_start,
    ROUND(SUM(CASE WHEN pnl_section = 'Выручка' THEN amount_abs ELSE 0 END)) AS revenue,
    ROUND(SUM(CASE WHEN pnl_section = 'Основные расходы' THEN amount_abs ELSE 0 END)) AS expenses,
    ROUND(
        SUM(CASE WHEN pnl_section = 'Выручка' THEN amount_abs ELSE 0 END) -
        SUM(CASE WHEN pnl_section = 'Основные расходы' THEN amount_abs ELSE 0 END)
    ) AS profit
FROM planfact_pnl_test
GROUP BY month_start
ORDER BY month_start;
""".strip()


def build_business_unit_query() -> str:
    return """
SELECT
    month_start,
    COALESCE(analytics_unit_code, COALESCE(business_unit_name, 'unmapped')) AS unit_code,
    ROUND(SUM(CASE WHEN pnl_section = 'Выручка' THEN amount_abs ELSE 0 END)) AS revenue,
    ROUND(SUM(CASE WHEN pnl_section = 'Основные расходы' THEN amount_abs ELSE 0 END)) AS expenses
FROM planfact_pnl_test
GROUP BY month_start, COALESCE(analytics_unit_code, COALESCE(business_unit_name, 'unmapped'))
ORDER BY month_start, unit_code;
""".strip()


def create_native_card(
    config: MetabaseConfig,
    database_id: int,
    collection_id: Optional[int],
    name: str,
    query: str,
    display: str = "table",
    visualization_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "display": display,
        "collection_id": collection_id,
        "dataset_query": {
            "type": "native",
            "native": {
                "query": query,
                "template-tags": {},
            },
            "database": database_id,
        },
        "visualization_settings": visualization_settings or {},
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
        "parameters": [],
    }
    return api_request(config, "POST", "/api/dashboard", payload)


def update_card(
    config: MetabaseConfig,
    card_id: int,
    database_id: int,
    name: str,
    query: str,
    display: str = "table",
    visualization_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "name": name,
        "display": display,
        "dataset_query": {
            "type": "native",
            "native": {
                "query": query,
                "template-tags": {},
            },
            "database": database_id,
        },
        "visualization_settings": visualization_settings or {},
    }
    return api_request(config, "PUT", f"/api/card/{card_id}", payload)


def put_dashboard_cards(
    config: MetabaseConfig,
    dashboard_id: int,
    cards: List[Dict[str, Any]],
) -> Any:
    payload = {
        "cards": cards,
    }
    return api_request(config, "PUT", f"/api/dashboard/{dashboard_id}/cards", payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--metabase-database-id", type=int, required=True)
    parser.add_argument("--month-start", type=parse_month_arg)
    parser.add_argument("--month-end", type=parse_month_arg)
    parser.add_argument("--update-existing-dashboard-id", type=int)
    parser.add_argument("--update-existing-matrix-card-id", type=int)
    parser.add_argument("--update-existing-monthly-card-id", type=int)
    parser.add_argument("--update-existing-business-unit-card-id", type=int)
    parser.add_argument("--metabase-collection-id", type=int)
    parser.add_argument("--allow-root", action="store_true")
    args = parser.parse_args()

    config = MetabaseConfig(base_url=args.metabase_url, api_key=args.metabase_api_key)
    collection_id = resolve_collection_id(args)

    if bool(args.month_start) != bool(args.month_end):
        raise RuntimeError("Use both --month-start and --month-end together")

    if args.month_start and args.month_end:
        months = get_months_in_range(args.database_url, args.month_start, args.month_end)
    else:
        months = get_latest_months(args.database_url, limit=3)

    if len(months) < 3:
        raise RuntimeError("Need at least 3 months in planfact_pnl_test to build the dashboard")

    if args.update_existing_dashboard_id:
        if not all(
            [
                args.update_existing_matrix_card_id,
                args.update_existing_monthly_card_id,
                args.update_existing_business_unit_card_id,
            ]
        ):
            raise RuntimeError(
                "When updating an existing dashboard, pass all three existing card ids"
            )

        dashboard = {"id": args.update_existing_dashboard_id, "name": "PlanFact P&L Test"}
        matrix_card = update_card(
            config,
            args.update_existing_matrix_card_id,
            args.metabase_database_id,
            name=f"PlanFact P&L Matrix ({month_label(months[0])} - {month_label(months[-1])})",
            query=build_matrix_query(months),
            display="table",
        )
        monthly_card = update_card(
            config,
            args.update_existing_monthly_card_id,
            args.metabase_database_id,
            name="PlanFact Monthly Revenue / Expenses / Profit",
            query=build_monthly_totals_query(),
            display="line",
        )
        business_unit_card = update_card(
            config,
            args.update_existing_business_unit_card_id,
            args.metabase_database_id,
            name="PlanFact by Business Unit",
            query=build_business_unit_query(),
            display="bar",
        )
    else:
        dashboard = create_dashboard(
            config,
            collection_id,
            name="PlanFact P&L Test",
            description="Autogenerated test dashboard for planfact_pnl_test",
        )

        matrix_card = create_native_card(
            config,
            args.metabase_database_id,
            collection_id,
            name=f"PlanFact P&L Matrix ({month_label(months[0])} - {month_label(months[-1])})",
            query=build_matrix_query(months),
            display="table",
        )
        monthly_card = create_native_card(
            config,
            args.metabase_database_id,
            collection_id,
            name="PlanFact Monthly Revenue / Expenses / Profit",
            query=build_monthly_totals_query(),
            display="line",
        )
        business_unit_card = create_native_card(
            config,
            args.metabase_database_id,
            collection_id,
            name="PlanFact by Business Unit",
            query=build_business_unit_query(),
            display="bar",
        )

        put_dashboard_cards(
            config,
            dashboard["id"],
            [
                {
                    "id": -1,
                    "card_id": matrix_card["id"],
                    "row": 0,
                    "col": 0,
                    "size_x": 24,
                    "size_y": 14,
                    "parameter_mappings": [],
                    "series": [],
                },
                {
                    "id": -2,
                    "card_id": monthly_card["id"],
                    "row": 14,
                    "col": 0,
                    "size_x": 12,
                    "size_y": 8,
                    "parameter_mappings": [],
                    "series": [],
                },
                {
                    "id": -3,
                    "card_id": business_unit_card["id"],
                    "row": 14,
                    "col": 12,
                    "size_x": 12,
                    "size_y": 8,
                    "parameter_mappings": [],
                    "series": [],
                },
            ],
        )

    print(json.dumps(
        {
            "dashboard_id": dashboard["id"],
            "dashboard_name": dashboard["name"],
            "card_ids": [matrix_card["id"], monthly_card["id"], business_unit_card["id"]],
            "months": [m.isoformat() for m in months],
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
