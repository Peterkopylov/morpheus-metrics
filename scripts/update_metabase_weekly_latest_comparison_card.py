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


def api_request(
    config: MetabaseConfig,
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
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


COMBINED_QUERY = """
WITH base AS (
    SELECT
        CASE
            WHEN unit = 'b2c_moscow' THEN 'Москва'
            WHEN unit = 'b2c_spb' THEN 'СПб'
            ELSE unit
        END AS city,
        row_order,
        metric_group,
        metric_name,
        latest_week_label,
        value_type,
        latest_value,
        week_over_week_abs_delta,
        week_over_week_pct_delta,
        avg_prev_4w_abs_delta,
        avg_prev_4w_pct_delta,
        year_over_year_abs_delta,
        year_over_year_pct_delta
    FROM weekly_metrics_latest_comparison
    WHERE unit IN ('b2c_moscow', 'b2c_spb')
)
SELECT
    city AS "Город",
    metric_name AS "Показатель",
    latest_week_label AS "Период",
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
    END AS "Неделя к неделе",
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
    END AS "К среднему 4 нед.",
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
    END AS "Год к году"
FROM base
ORDER BY
    CASE city WHEN 'Москва' THEN 1 WHEN 'СПб' THEN 2 ELSE 99 END,
    row_order,
    metric_group,
    metric_name;
""".strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument("--card-id", type=int, default=174)
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    card = api_request(config, "GET", f"/api/card/{args.card_id}")

    payload = {
        "name": card["name"],
        "display": card["display"],
        "collection_id": card["collection_id"],
        "description": card.get("description"),
        "dataset_query": {
            "type": "native",
            "native": {
                "query": COMBINED_QUERY,
                "template-tags": {},
            },
            "database": card["database_id"],
        },
        "visualization_settings": card.get("visualization_settings", {}),
    }
    updated = api_request(config, "PUT", f"/api/card/{args.card_id}", payload)
    print(json.dumps({"card_id": updated["id"], "name": updated["name"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
