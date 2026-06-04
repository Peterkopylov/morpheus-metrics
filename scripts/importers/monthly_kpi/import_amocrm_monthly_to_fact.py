#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
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

from import_amocrm_weekly_to_fact import (
    DEFAULT_BASE_URL,
    ENV_PATH,
    FLOW_STATUS_NAME_TO_METRIC_LEGACY,
    FLOW_STATUS_NAME_TO_METRIC_V2,
    PIPELINE_CORPORATES_LEGACY,
    PIPELINE_CORPORATES_V2,
    PIPELINE_SWITCH_DATE,
    MSK,
    build_events_url,
    build_leads_url_for_pipeline,
    delete_existing,
    fetch_metric_id,
    fetch_page,
    fetch_pipeline_statuses,
    insert_rows,
    load_env_file,
)
from monthly_kpi_period_utils import month_bounds


REPORT_PATH = ROOT / "artifacts" / "run_reports" / "amocrm_monthly_to_fact_import_report.csv"


def to_ts(dt_date: date, end_of_day: bool) -> int:
    dt = datetime.combine(dt_date, dt_time(23, 59, 59) if end_of_day else dt_time(0, 0, 0), tzinfo=MSK)
    return int(dt.timestamp())


def fetch_all_leads_for_pipeline(base_url: str, token: str, pipeline_id: int, created_from: int, created_to: int) -> list[dict]:
    leads: list[dict] = []
    page = 1
    while True:
        payload = fetch_page(build_leads_url_for_pipeline(base_url, pipeline_id, created_from, created_to, page=page), token)
        chunk = payload.get("_embedded", {}).get("leads", []) or []
        leads.extend(chunk)
        if not chunk or len(chunk) < 250:
            break
        page += 1
    return leads


def fetch_status_events(base_url: str, token: str, from_ts: int, to_ts: int) -> list[dict]:
    events: list[dict] = []
    page = 1
    while True:
        payload = fetch_page(build_events_url(base_url, from_ts, to_ts, page=page), token)
        chunk = payload.get("_embedded", {}).get("events", []) or []
        events.extend(chunk)
        if not chunk or len(chunk) < 250:
            break
        page += 1
    return events


def build_row(metric_id: int, source_record_key: str, source_run_id: str, business_unit: str, period_start: date, period_end: date, value_numeric: Decimal, payload: dict) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "metric_id": metric_id,
        "rule_id": None,
        "source_system": "amocrm",
        "source_record_key": source_record_key,
        "source_run_id": source_run_id,
        "source_cell_a1": None,
        "source_cell_url": None,
        "business_unit": business_unit,
        "show_name": None,
        "partner_name": None,
        "channel_name": None,
        "period_granularity": "month",
        "period_start": period_start,
        "period_end": period_end,
        "value_numeric": value_numeric,
        "value_text": None,
        "value_raw": str(value_numeric),
        "currency_code": None,
        "is_estimated": False,
        "observed_at": datetime.combine(period_end, dt_time(23, 59, 59), tzinfo=MSK).astimezone(timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


def delete_existing_month(conn, source_run_id: str, period_start: date) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM fact_metric_observation
            WHERE source_system='amocrm'
              AND source_run_id=%s
              AND period_granularity='month'
              AND period_start=%s
            """,
            (source_run_id, period_start),
        )


def pipelines_for_period(period_start: date, period_end: date) -> list[tuple[int, str, dict[str, str]]]:
    if period_end < PIPELINE_SWITCH_DATE:
        return [(PIPELINE_CORPORATES_LEGACY, "Корпоративы", FLOW_STATUS_NAME_TO_METRIC_LEGACY)]
    if period_start >= PIPELINE_SWITCH_DATE:
        return [(PIPELINE_CORPORATES_V2, "Корпоративы 2.0", FLOW_STATUS_NAME_TO_METRIC_V2)]
    return [
        (PIPELINE_CORPORATES_LEGACY, "Корпоративы", FLOW_STATUS_NAME_TO_METRIC_LEGACY),
        (PIPELINE_CORPORATES_V2, "Корпоративы 2.0", FLOW_STATUS_NAME_TO_METRIC_V2),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--month-start", required=True)
    parser.add_argument("--source-run-id", default="amocrm_monthly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    parser.add_argument("--env-file", default=str(ENV_PATH))
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    token = os.environ.get("AMOCRM_LONG_LIVED_TOKEN", "")
    base_url = os.environ.get("AMOCRM_BASE_URL", DEFAULT_BASE_URL)
    if not token or token == "replace_me":
        Path(args.report_path).parent.mkdir(parents=True, exist_ok=True)
        with Path(args.report_path).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["status", "reason"])
            writer.writeheader()
            writer.writerow({"status": "pending", "reason": "missing_amocrm_token"})
        print("pending: missing amoCRM token", file=sys.stderr)
        return 20

    period_start, period_end = month_bounds(date.fromisoformat(args.month_start))
    created_from = to_ts(period_start, end_of_day=False)
    created_to = to_ts(period_end, end_of_day=True)

    conn = psycopg2.connect(args.database_url)
    if args.delete_existing:
        with conn:
            delete_existing_month(conn, args.source_run_id, period_start)

    metric_ids = {"Number of leads": fetch_metric_id(conn, "Number of leads")}
    for metric_name in set(FLOW_STATUS_NAME_TO_METRIC_LEGACY.values()) | set(FLOW_STATUS_NAME_TO_METRIC_V2.values()):
        metric_ids[metric_name] = fetch_metric_id(conn, metric_name)

    rows = []
    report_rows: list[dict[str, str]] = []
    all_lead_ids: set[int] = set()
    pipeline_payload: list[dict] = []
    lead_ids_by_metric: dict[str, set[int]] = defaultdict(set)

    for pipeline_id, pipeline_name, flow_map in pipelines_for_period(period_start, period_end):
        leads = fetch_all_leads_for_pipeline(base_url, token, pipeline_id, created_from, created_to)
        status_events = fetch_status_events(base_url, token, created_from, created_to)
        pipeline_status_names = fetch_pipeline_statuses(base_url, token, pipeline_id)
        all_lead_ids.update(int(lead["id"]) for lead in leads)
        pipeline_payload.append({"pipeline_id": pipeline_id, "pipeline_name": pipeline_name, "lead_count": len(leads)})

        for event in status_events:
            value_after = event.get("value_after") or []
            if not value_after:
                continue
            lead_status = (value_after[0] or {}).get("lead_status") or {}
            if int(lead_status.get("pipeline_id") or 0) != pipeline_id:
                continue
            status_id = int(lead_status.get("id") or 0)
            status_name = pipeline_status_names.get(status_id, "")
            metric_name = flow_map.get(status_name)
            if not metric_name:
                continue
            lead_ids_by_metric[metric_name].add(int(event["entity_id"]))

    rows.append(
        build_row(
            metric_ids["Number of leads"],
            "b2b:Number of leads:general",
            args.source_run_id,
            "b2b",
            period_start,
            period_end,
            Decimal(len(all_lead_ids)),
            {"loader": "import_amocrm_monthly_to_fact", "metric_name": "Number of leads", "pipelines": pipeline_payload, "lead_ids": sorted(all_lead_ids)},
        )
    )
    report_rows.append({"metric_name": "Number of leads", "status_name": "", "value": str(len(all_lead_ids))})

    for metric_name in sorted(set(FLOW_STATUS_NAME_TO_METRIC_LEGACY.values()) | set(FLOW_STATUS_NAME_TO_METRIC_V2.values())):
        lead_ids = sorted(lead_ids_by_metric.get(metric_name, set()))
        rows.append(
            build_row(
                metric_ids[metric_name],
                f"b2b:{metric_name}:general",
                args.source_run_id,
                "b2b",
                period_start,
                period_end,
                Decimal(len(lead_ids)),
                {"loader": "import_amocrm_monthly_to_fact", "metric_name": metric_name, "count_logic": "distinct leads with lead_status_changed into target status during month", "lead_ids": lead_ids, "pipelines": pipeline_payload},
            )
        )
        report_rows.append({"metric_name": metric_name, "status_name": "", "value": str(len(lead_ids))})

    with conn:
        insert_rows(conn, rows)
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric_name", "status_name", "value"])
        writer.writeheader()
        writer.writerows(report_rows)
    print(f"inserted={len(rows)} report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
