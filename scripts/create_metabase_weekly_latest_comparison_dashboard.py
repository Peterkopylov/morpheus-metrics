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
            "native": {
                "query": query,
                "template-tags": {},
            },
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


def comparison_query(unit: str) -> str:
    return f"""
SELECT
    metric_group AS "Группа",
    metric_name AS "Показатель",
    CASE
        WHEN value_type = 'percent' THEN TO_CHAR(ROUND(latest_value::numeric, 2), 'FM999999990.00') || '%'
        ELSE TO_CHAR(ROUND(latest_value::numeric, 0), 'FM999999999990')
    END AS "Результат недели",
    CASE
        WHEN value_type = 'percent' THEN
            CASE
                WHEN week_over_week_abs_delta IS NULL THEN NULL
                ELSE
                    CASE WHEN week_over_week_abs_delta > 0 THEN '+' ELSE '' END ||
                    TO_CHAR(ROUND(week_over_week_abs_delta::numeric, 2), 'FM999999990.00') || ' п.п.'
            END
        ELSE
            CASE
                WHEN week_over_week_pct_delta IS NULL THEN NULL
                ELSE
                    CASE WHEN week_over_week_pct_delta > 0 THEN '+' ELSE '' END ||
                    TO_CHAR(ROUND((week_over_week_pct_delta * 100)::numeric, 1), 'FM999999990.0') || '%'
            END
    END AS "Динамика неделя к неделе",
    CASE
        WHEN value_type = 'percent' THEN
            CASE
                WHEN avg_prev_4w_abs_delta IS NULL THEN NULL
                ELSE
                    CASE WHEN avg_prev_4w_abs_delta > 0 THEN '+' ELSE '' END ||
                    TO_CHAR(ROUND(avg_prev_4w_abs_delta::numeric, 2), 'FM999999990.00') || ' п.п.'
            END
        ELSE
            CASE
                WHEN avg_prev_4w_pct_delta IS NULL THEN NULL
                ELSE
                    CASE WHEN avg_prev_4w_pct_delta > 0 THEN '+' ELSE '' END ||
                    TO_CHAR(ROUND((avg_prev_4w_pct_delta * 100)::numeric, 1), 'FM999999990.0') || '%'
            END
    END AS "Динамика к среднему за предыдущие 4 недели",
    CASE
        WHEN value_type = 'percent' THEN
            CASE
                WHEN year_over_year_abs_delta IS NULL THEN NULL
                ELSE
                    CASE WHEN year_over_year_abs_delta > 0 THEN '+' ELSE '' END ||
                    TO_CHAR(ROUND(year_over_year_abs_delta::numeric, 2), 'FM999999990.00') || ' п.п.'
            END
        ELSE
            CASE
                WHEN year_over_year_pct_delta IS NULL THEN NULL
                ELSE
                    CASE WHEN year_over_year_pct_delta > 0 THEN '+' ELSE '' END ||
                    TO_CHAR(ROUND((year_over_year_pct_delta * 100)::numeric, 1), 'FM999999990.0') || '%'
            END
    END AS "Динамика год к году",
    latest_week_label AS "Период"
FROM weekly_metrics_latest_comparison
WHERE unit = '{unit}'
ORDER BY row_order, metric_group, metric_name;
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
        "Weekly Metrics Latest Comparison",
        "Latest weekly metrics with WoW, avg previous 4 weeks, and YoY comparisons for Moscow and SPB.",
    )

    cards = [
        create_card(config, args.metabase_database_id, "Moscow Weekly Latest Comparison", comparison_query("b2c_moscow")),
        create_card(config, args.metabase_database_id, "SPB Weekly Latest Comparison", comparison_query("b2c_spb")),
    ]

    put_dashboard_cards(
        config,
        dashboard["id"],
        [
            {"id": -1, "card_id": cards[0]["id"], "row": 0, "col": 0, "size_x": 12, "size_y": 18, "parameter_mappings": [], "series": []},
            {"id": -2, "card_id": cards[1]["id"], "row": 0, "col": 12, "size_x": 12, "size_y": 18, "parameter_mappings": [], "series": []},
        ],
    )

    print(json.dumps({"dashboard_id": dashboard["id"], "dashboard_name": dashboard["name"], "card_ids": [c["id"] for c in cards]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
