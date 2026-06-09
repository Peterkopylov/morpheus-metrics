#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, time as dt_time, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
ROOT_SCRIPTS_DIR = ROOT / "scripts"
WEEKLY_IMPORTERS_DIR = ROOT_SCRIPTS_DIR / "importers" / "weekly"
for extra_path in (ROOT_SCRIPTS_DIR, WEEKLY_IMPORTERS_DIR):
    if str(extra_path) not in sys.path:
        sys.path.insert(0, str(extra_path))

from import_yandex_direct_weekly_to_fact import (
    ENV_MAIN,
    ENV_SPB,
    MSK,
    classify_campaign,
    direct_report,
    fetch_metric_id,
    insert_rows,
    parse_micros,
    read_env,
)
from monthly_kpi_period_utils import month_bounds


REPORT_PATH = ROOT / "artifacts" / "run_reports" / "yandex_direct_monthly_to_fact_import_report.csv"


def delete_existing(conn, source_run_id: str, period_start: date) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM fact_metric_observation
            WHERE source_system='yandex_direct'
              AND source_run_id=%s
              AND period_granularity='month'
              AND period_start=%s
            """,
            (source_run_id, period_start),
        )


def build_row(metric_id: int, metric_key: str, business_unit: str, value_numeric: Decimal, period_start: date, period_end: date, source_run_id: str, payload: dict) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "metric_id": metric_id,
        "rule_id": None,
        "source_system": "yandex_direct",
        "source_record_key": f"{business_unit}:perfomance:{metric_key}",
        "source_run_id": source_run_id,
        "source_cell_a1": None,
        "source_cell_url": None,
        "business_unit": business_unit,
        "show_name": None,
        "partner_name": None,
        "channel_name": "perfomance",
        "period_granularity": "month",
        "period_start": period_start,
        "period_end": period_end,
        "value_numeric": value_numeric,
        "value_text": None,
        "value_raw": str(value_numeric),
        "currency_code": "RUB",
        "is_estimated": False,
        "observed_at": datetime.combine(period_end, dt_time(23, 59, 59), tzinfo=MSK).astimezone(timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--month-start", required=True)
    parser.add_argument("--source-run-id", default="yandex_direct_monthly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    period_start, period_end = month_bounds(date.fromisoformat(args.month_start))
    main_env = read_env(ENV_MAIN)
    spb_env = read_env(ENV_SPB)
    cabinets = []
    if main_env.get("YANDEX_DIRECT_ACCESS_TOKEN"):
        cabinets.append(("main", main_env["YANDEX_DIRECT_ACCESS_TOKEN"]))
    if spb_env.get("YANDEX_DIRECT_SPB_ACCESS_TOKEN"):
        cabinets.append(("spb", spb_env["YANDEX_DIRECT_SPB_ACCESS_TOKEN"]))

    metric_name = "Marketing costs"
    report_rows: list[dict] = []
    aggregates = {"b2c_moscow": Decimal("0"), "b2c_spb": Decimal("0"), "b2b": Decimal("0")}
    campaign_payload: dict[str, list[dict]] = {"b2c_moscow": [], "b2c_spb": [], "b2b": []}

    for cabinet, token in cabinets:
        rows = direct_report(token, period_start.isoformat(), period_end.isoformat())
        for row in rows:
            cost = parse_micros(row.get("Cost"))
            campaign_name = row.get("CampaignName") or ""
            bucket = classify_campaign(campaign_name, cabinet)
            aggregates[bucket] += cost
            campaign_payload[bucket].append({"cabinet": cabinet, "campaign_id": row.get("CampaignId"), "campaign_name": campaign_name, "cost": str(cost), "clicks": row.get("Clicks"), "impressions": row.get("Impressions")})

    conn = psycopg2.connect(args.database_url)
    metric_id = fetch_metric_id(conn, metric_name)
    if args.delete_existing:
        with conn:
            delete_existing(conn, args.source_run_id, period_start)

    insert_buffer = []
    for business_unit in ("b2c_moscow", "b2c_spb", "b2b"):
        insert_buffer.append(build_row(metric_id, "marketing_costs", business_unit, aggregates[business_unit], period_start, period_end, args.source_run_id, {"loader": "import_yandex_direct_monthly_to_fact", "metric_name": metric_name, "campaigns": campaign_payload[business_unit]}))
        report_rows.append({"business_unit": business_unit, "metric_name": metric_name, "status": "inserted", "value_numeric": str(aggregates[business_unit]), "campaigns_count": str(len(campaign_payload[business_unit]))})

    with conn:
        insert_rows(conn, insert_buffer)
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["business_unit", "metric_name", "status", "value_numeric", "campaigns_count"])
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"inserted={len(insert_buffer)} report={report_path}")


if __name__ == "__main__":
    main()
