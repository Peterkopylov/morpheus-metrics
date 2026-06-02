#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

from import_yandex_metrica_weekly_to_fact import (
    B2B_PAGE_PATH,
    COUNTERS,
    MSK,
    SHOW_PATHS,
    channel_rows,
    fetch_metric_id,
    insert_rows,
    path_filter,
    path_visits,
    read_env_token,
    show_pageviews,
)
from monthly_kpi_period_utils import month_bounds


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "yandex_metrica_monthly_to_fact_import_report.csv"


def delete_existing(conn, source_run_id: str, period_start: date) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM fact_metric_observation
            WHERE source_system='yandex_metrica'
              AND source_run_id=%s
              AND period_granularity='month'
              AND period_start=%s
            """,
            (source_run_id, period_start),
        )


def build_row(metric_id: int, source_record_key: str, source_run_id: str, business_unit: str, period_start: date, period_end: date, value_numeric, value_raw: str, payload: dict, *, show_name: str | None = None, channel_name: str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "metric_id": metric_id,
        "rule_id": None,
        "source_system": "yandex_metrica",
        "source_record_key": source_record_key,
        "source_run_id": source_run_id,
        "source_cell_a1": None,
        "source_cell_url": None,
        "business_unit": business_unit,
        "show_name": show_name,
        "partner_name": None,
        "channel_name": channel_name,
        "period_granularity": "month",
        "period_start": period_start,
        "period_end": period_end,
        "value_numeric": value_numeric,
        "value_text": None,
        "value_raw": value_raw,
        "currency_code": None,
        "is_estimated": False,
        "observed_at": datetime.combine(period_end, time(23, 59, 59), tzinfo=MSK).astimezone(timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--month-start", required=True)
    parser.add_argument("--source-run-id", default="yandex_metrica_monthly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    period_start, period_end = month_bounds(date.fromisoformat(args.month_start))
    conn = psycopg2.connect(args.database_url)
    metric_id = fetch_metric_id(conn, "Website visits")
    if args.delete_existing:
        delete_existing(conn, args.source_run_id, period_start)
        conn.commit()

    report_rows: list[dict] = []
    insert_payload: list[dict] = []

    for business_unit, meta in COUNTERS.items():
        token = read_env_token(meta["env_path"], meta["token_key"])
        counter_id = meta["counter_id"]
        for item in channel_rows(token, counter_id, period_start, period_end):
            insert_payload.append(build_row(metric_id, f"{business_unit}|channel|{item['channel_name']}", args.source_run_id, business_unit, period_start, period_end, item["value_numeric"], item["value_raw"], item["payload"], channel_name=item["channel_name"]))
            report_rows.append({"business_unit": business_unit, "metric_name": "Website visits", "scope": f"channel:{item['channel_name']}", "status": "inserted", "value": str(item["value_numeric"]), "note": "ym:s:visits by normalized traffic channel"})
        for show_name, path in SHOW_PATHS.items():
            value, payload = show_pageviews(token, counter_id, path, period_start, period_end)
            insert_payload.append(build_row(metric_id, f"{business_unit}|show_page|{show_name}", args.source_run_id, business_unit, period_start, period_end, value, str(value), payload, show_name=show_name))
            report_rows.append({"business_unit": business_unit, "metric_name": "Website visits", "scope": f"show:{show_name}", "status": "inserted", "value": str(value), "note": "ym:pv:pageviews by canonical show page path"})

    main_token = read_env_token(COUNTERS["b2c_moscow"]["env_path"], COUNTERS["b2c_moscow"]["token_key"])
    main_counter_id = COUNTERS["b2c_moscow"]["counter_id"]
    b2b_filter = path_filter(B2B_PAGE_PATH)
    for item in channel_rows(main_token, main_counter_id, period_start, period_end, filters=b2b_filter, payload_extra={"path": B2B_PAGE_PATH}):
        insert_payload.append(build_row(metric_id, f"b2b|channel|{item['channel_name']}", args.source_run_id, "b2b", period_start, period_end, item["value_numeric"], item["value_raw"], item["payload"], channel_name=item["channel_name"]))
        report_rows.append({"business_unit": "b2b", "metric_name": "Website visits", "scope": f"channel:{item['channel_name']}", "status": "inserted", "value": str(item["value_numeric"]), "note": "ym:s:visits for /corporative by normalized traffic channel"})
    b2b_value, b2b_payload = path_visits(main_token, main_counter_id, B2B_PAGE_PATH, period_start, period_end)
    insert_payload.append(build_row(metric_id, "b2b|page|corporative", args.source_run_id, "b2b", period_start, period_end, b2b_value, str(b2b_value), b2b_payload))
    report_rows.append({"business_unit": "b2b", "metric_name": "Website visits", "scope": "page:/corporative", "status": "inserted", "value": str(b2b_value), "note": "ym:s:visits for /corporative"})

    insert_rows(conn, insert_payload)
    conn.commit()
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["business_unit", "metric_name", "scope", "status", "value", "note"])
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"inserted={len(insert_payload)}")
    print(f"report={report_path}")


if __name__ == "__main__":
    main()
