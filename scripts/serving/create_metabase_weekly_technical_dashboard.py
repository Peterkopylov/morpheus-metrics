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


def create_card(
    config: MetabaseConfig,
    database_id: int,
    collection_id: Optional[int],
    name: str,
    query: str,
    display: str = "table",
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
        "parameters": [],
    }
    return api_request(config, "POST", "/api/dashboard", payload)


def put_dashboard_cards(config: MetabaseConfig, dashboard_id: int, cards) -> Any:
    return api_request(config, "PUT", f"/api/dashboard/{dashboard_id}/cards", {"cards": cards})


def status_query() -> str:
    return """
SELECT
    unit_label AS "Юнит",
    latest_week_start AS "Последняя загруженная неделя",
    last_rows_loaded AS "Строк загружено",
    last_import_started_at AS "Импорт стартовал",
    last_import_finished_at AS "Импорт завершился",
    last_dashboard_refresh_started_at AS "Рефреш дэшбордов стартовал",
    last_dashboard_refresh_at AS "Рефреш дэшбордов завершился"
FROM weekly_dashboard_status
ORDER BY unit;
""".strip()


def latest_week_sanity_query() -> str:
    return """
WITH latest AS (
    SELECT
        unit,
        MAX(period_start)::date AS latest_week_start
    FROM fact_metrics
    WHERE aggregation_level = 'week'
      AND unit IN ('b2c_moscow', 'b2c_spb')
    GROUP BY unit
)
SELECT
    CASE
        WHEN f.unit = 'b2c_moscow' THEN 'Москва'
        WHEN f.unit = 'b2c_spb' THEN 'СПб'
        ELSE f.unit
    END AS "Юнит",
    l.latest_week_start AS "Неделя",
    COUNT(*) AS "Строк фактов",
    COUNT(*) FILTER (WHERE f.metric_key IS NOT NULL) AS "Строк с metric_key",
    COUNT(DISTINCT f.metric_key) FILTER (WHERE f.metric_key IS NOT NULL) AS "Уникальных metric_key",
    COUNT(*) FILTER (WHERE f.value IS NULL) AS "Пустых значений",
    COUNT(*) FILTER (WHERE f.value = 0) AS "Нулевых значений",
    COUNT(*) FILTER (WHERE f.value_type = 'percent') AS "Percent-метрик",
    MIN(f.loaded_at) AS "Первый loaded_at",
    MAX(f.loaded_at) AS "Последний loaded_at"
FROM fact_metrics f
JOIN latest l
  ON l.unit = f.unit
 AND l.latest_week_start = f.period_start::date
WHERE f.aggregation_level = 'week'
GROUP BY f.unit, l.latest_week_start
ORDER BY f.unit;
""".strip()


def latest_import_runs_query() -> str:
    return """
SELECT
    CASE
        WHEN unit = 'b2c_moscow' THEN 'Москва'
        WHEN unit = 'b2c_spb' THEN 'СПб'
        ELSE unit
    END AS "Юнит",
    source_tab AS "Источник",
    status AS "Статус",
    exit_code AS "Exit code",
    rows_loaded AS "Rows loaded",
    metric_rows AS "Metric rows",
    unmapped_pairs AS "Unmapped pairs",
    started_at AS "Started at",
    finished_at AS "Finished at"
FROM weekly_import_runs
WHERE status IS NOT NULL
ORDER BY finished_at DESC NULLS LAST, started_at DESC
LIMIT 10;
""".strip()


def latest_week_fact_query(unit: str) -> str:
    return f"""
WITH latest AS (
    SELECT MAX(period_start)::date AS latest_week_start
    FROM fact_metrics
    WHERE aggregation_level = 'week'
      AND unit = '{unit}'
)
SELECT
    period_label AS "Период",
    metric_group AS "Группа",
    metric_name AS "Метрика",
    metric_key AS "Metric key",
    value AS "Value",
    value_raw AS "Value raw",
    value_type AS "Value type",
    row_order AS "Row",
    col_order AS "Col",
    loaded_at AS "Loaded at"
FROM fact_metrics
WHERE aggregation_level = 'week'
  AND unit = '{unit}'
  AND period_start::date = (SELECT latest_week_start FROM latest)
ORDER BY row_order, metric_group, metric_name;
""".strip()


def latest_week_trace_query(unit: str) -> str:
    return f"""
WITH latest AS (
    SELECT MAX(period_start)::date AS latest_week_start
    FROM weekly_metrics_trace
    WHERE unit = '{unit}'
)
SELECT
    period_label AS "Период",
    metric_group AS "Группа",
    metric_name AS "Метрика",
    metric_key AS "Metric key",
    value AS "Value",
    value_raw AS "Value raw",
    value_type AS "Value type",
    row_order AS "Row",
    value_a1 AS "Value cell",
    value_url AS "Value URL",
    metric_group_url AS "Group URL",
    metric_name_url AS "Name URL",
    loaded_at AS "Loaded at"
FROM weekly_metrics_trace
WHERE unit = '{unit}'
  AND period_start::date = (SELECT latest_week_start FROM latest)
ORDER BY row_order, metric_group, metric_name;
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
        "Weekly Metrics Technical Check",
        "Technical validation dashboard for the latest loaded weekly metrics by unit.",
    )

    cards = [
        create_card(config, args.metabase_database_id, collection_id, "Weekly Load Status", status_query()),
        create_card(config, args.metabase_database_id, collection_id, "Weekly Latest Sanity Checks", latest_week_sanity_query()),
        create_card(config, args.metabase_database_id, collection_id, "Weekly Import Runs Recent", latest_import_runs_query()),
        create_card(config, args.metabase_database_id, collection_id, "Moscow Latest Week Facts", latest_week_fact_query("b2c_moscow")),
        create_card(config, args.metabase_database_id, collection_id, "SPB Latest Week Facts", latest_week_fact_query("b2c_spb")),
        create_card(config, args.metabase_database_id, collection_id, "Moscow Latest Week Trace", latest_week_trace_query("b2c_moscow")),
        create_card(config, args.metabase_database_id, collection_id, "SPB Latest Week Trace", latest_week_trace_query("b2c_spb")),
    ]

    put_dashboard_cards(
        config,
        dashboard["id"],
        [
            {"id": -1, "card_id": cards[0]["id"], "row": 0, "col": 0, "size_x": 8, "size_y": 5, "parameter_mappings": [], "series": []},
            {"id": -2, "card_id": cards[1]["id"], "row": 0, "col": 8, "size_x": 8, "size_y": 5, "parameter_mappings": [], "series": []},
            {"id": -3, "card_id": cards[2]["id"], "row": 0, "col": 16, "size_x": 8, "size_y": 5, "parameter_mappings": [], "series": []},
            {"id": -4, "card_id": cards[3]["id"], "row": 5, "col": 0, "size_x": 12, "size_y": 12, "parameter_mappings": [], "series": []},
            {"id": -5, "card_id": cards[4]["id"], "row": 5, "col": 12, "size_x": 12, "size_y": 12, "parameter_mappings": [], "series": []},
            {"id": -6, "card_id": cards[5]["id"], "row": 17, "col": 0, "size_x": 12, "size_y": 14, "parameter_mappings": [], "series": []},
            {"id": -7, "card_id": cards[6]["id"], "row": 17, "col": 12, "size_x": 12, "size_y": 14, "parameter_mappings": [], "series": []},
        ],
    )

    print(
        json.dumps(
            {
                "dashboard_id": dashboard["id"],
                "dashboard_name": dashboard["name"],
                "card_ids": [c["id"] for c in cards],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
