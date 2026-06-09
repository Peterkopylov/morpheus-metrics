#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import ssl
import sys
from collections import defaultdict
from datetime import date, datetime, time as dt_time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "amocrm_weekly_to_fact_import_report.csv"
ENV_PATH = ROOT / ".env.amocrm"
DEFAULT_BASE_URL = "https://morpheusshow.amocrm.ru"
PIPELINE_CORPORATES_LEGACY = 8783794
PIPELINE_CORPORATES_V2 = 10869194
PIPELINE_SWITCH_DATE = date(2025, 5, 1)
MSK = ZoneInfo("Europe/Moscow")
SSL_CONTEXT = ssl._create_unverified_context()

FLOW_STATUS_NAME_TO_METRIC_V2 = {
    "Контакт установлен": "Number of contacts established",
    "Квалифицирован": "Number of qualified leads",
    "Презентация проведена": "Number of concepts sent",
    "Назначена креативная встреча": "Number of creative meetings scheduled",
    "Креативная встреча проведена": "Number of creative meetings",
    "КП отправлено": "Number of proposals sent",
    "Договор отправлен": "Number of contracts sent",
    "Договор подписан": "Number of contracts approved",
    "Оплата получена": "Number of payments received",
    "Отзыв получен": "Number of orders",
    "Закрыто и не реализовано": "Number of lost leads",
}

FLOW_STATUS_NAME_TO_METRIC_LEGACY = {
    "Контакт установлен": "Number of contacts established",
    "Квалифицирован": "Number of qualified leads",
    "Концепт отправлен": "Number of concepts sent",
    "Назначена креативная встреча": "Number of creative meetings scheduled",
    "Проведена креативная встреча": "Number of creative meetings",
    "КП отправлено": "Number of proposals sent",
    "Договор отправлен": "Number of contracts sent",
    "Договор согласован": "Number of contracts approved",
    "Оплата получена": "Number of payments received",
    "Отзыв получен": "Number of orders",
    "Закрыто и не реализовано": "Number of lost leads",
}


def period_bounds(last_full_week_start: date | None = None) -> tuple[date, date]:
    if last_full_week_start:
        return last_full_week_start, last_full_week_start + timedelta(days=6)
    today = datetime.now(MSK).date()
    current_week_start = today - timedelta(days=today.weekday())
    last_week_start = current_week_start - timedelta(days=7)
    return last_week_start, last_week_start + timedelta(days=6)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def to_ts(dt_date: date, end_of_day: bool) -> int:
    dt = datetime.combine(dt_date, dt_time(23, 59, 59) if end_of_day else dt_time(0, 0, 0), tzinfo=MSK)
    return int(dt.timestamp())


def custom_field_value(lead: dict, field_name: str) -> str:
    for field in lead.get("custom_fields_values", []) or []:
        if field.get("field_name") == field_name:
            values = field.get("values") or []
            return ", ".join(str(v.get("value")) for v in values if v.get("value") is not None)
    return ""


def fetch_page(url: str, token: str) -> dict:
    request = Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urlopen(request, timeout=120, context=SSL_CONTEXT) as response:
        if getattr(response, "status", None) == 204:
            return {}
        body = response.read()
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))


def build_leads_url(base_url: str, created_from: int, created_to: int, page: int = 1, limit: int = 250) -> str:
    query = urlencode(
        [
            ("filter[pipeline_id][0]", str(PIPELINE_CORPORATES_V2)),
            ("filter[created_at][from]", str(created_from)),
            ("filter[created_at][to]", str(created_to)),
            ("limit", str(limit)),
            ("page", str(page)),
        ]
    )
    return f"{base_url.rstrip('/')}/api/v4/leads?{query}"


def fetch_all_leads(base_url: str, token: str, created_from: int, created_to: int) -> list[dict]:
    leads: list[dict] = []
    page = 1
    while True:
        payload = fetch_page(build_leads_url(base_url, created_from, created_to, page=page), token)
        chunk = payload.get("_embedded", {}).get("leads", []) or []
        leads.extend(chunk)
        if not chunk or len(chunk) < 250:
            break
        page += 1
    return leads


def pipeline_for_week(week_start: date) -> tuple[int, str]:
    if week_start < PIPELINE_SWITCH_DATE:
        return PIPELINE_CORPORATES_LEGACY, "Корпоративы"
    return PIPELINE_CORPORATES_V2, "Корпоративы 2.0"


def status_mapping_for_pipeline(pipeline_id: int) -> dict[str, str]:
    if pipeline_id == PIPELINE_CORPORATES_LEGACY:
        return FLOW_STATUS_NAME_TO_METRIC_LEGACY
    return FLOW_STATUS_NAME_TO_METRIC_V2


def build_leads_url_for_pipeline(
    base_url: str,
    pipeline_id: int,
    created_from: int,
    created_to: int,
    page: int = 1,
    limit: int = 250,
) -> str:
    query = urlencode(
        [
            ("filter[pipeline_id][0]", str(pipeline_id)),
            ("filter[created_at][from]", str(created_from)),
            ("filter[created_at][to]", str(created_to)),
            ("limit", str(limit)),
            ("page", str(page)),
        ]
    )
    return f"{base_url.rstrip('/')}/api/v4/leads?{query}"


def fetch_all_leads_for_pipeline(
    base_url: str,
    token: str,
    pipeline_id: int,
    created_from: int,
    created_to: int,
) -> list[dict]:
    leads: list[dict] = []
    page = 1
    while True:
        payload = fetch_page(
            build_leads_url_for_pipeline(base_url, pipeline_id, created_from, created_to, page=page),
            token,
        )
        chunk = payload.get("_embedded", {}).get("leads", []) or []
        leads.extend(chunk)
        if not chunk or len(chunk) < 250:
            break
        page += 1
    return leads


def build_events_url(base_url: str, from_ts: int, to_ts: int, page: int = 1, limit: int = 250) -> str:
    query = urlencode(
        [
            ("filter[entity]", "lead"),
            ("filter[type][0]", "lead_status_changed"),
            ("filter[created_at][from]", str(from_ts)),
            ("filter[created_at][to]", str(to_ts)),
            ("limit", str(limit)),
            ("page", str(page)),
        ]
    )
    return f"{base_url.rstrip('/')}/api/v4/events?{query}"


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


def fetch_pipeline_statuses(base_url: str, token: str, pipeline_id: int) -> dict[int, str]:
    payload = fetch_page(f"{base_url.rstrip('/')}/api/v4/leads/pipelines/{pipeline_id}/statuses", token)
    result: dict[int, str] = {}
    for status in payload.get("_embedded", {}).get("statuses", []) or []:
        status_id = int(status.get("id") or 0)
        if status_id:
            result[status_id] = status.get("name") or ""
    return result


def fetch_metric_id(conn, metric_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute("select metric_id from metric_catalogue where metric_name=%s", (metric_name,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"metric not found: {metric_name}")
        return int(row[0])


def insert_rows(conn, rows: list[dict]) -> None:
    if not rows:
        return
    sql = """
    INSERT INTO fact_metric_observation (
        metric_id, rule_id, source_system, source_record_key, source_run_id,
        source_cell_a1, source_cell_url, business_unit, show_name, partner_name, channel_name,
        period_granularity, period_start, period_end, value_numeric, value_text, value_raw,
        currency_code, is_estimated, observed_at, loaded_at, payload
    )
    VALUES (
        %(metric_id)s, %(rule_id)s, %(source_system)s, %(source_record_key)s, %(source_run_id)s,
        %(source_cell_a1)s, %(source_cell_url)s, %(business_unit)s, %(show_name)s, %(partner_name)s, %(channel_name)s,
        %(period_granularity)s, %(period_start)s, %(period_end)s, %(value_numeric)s, %(value_text)s, %(value_raw)s,
        %(currency_code)s, %(is_estimated)s, %(observed_at)s, %(loaded_at)s, %(payload)s
    )
    ON CONFLICT (
        metric_id, source_system, business_unit, show_name_norm, partner_name_norm, channel_name_norm,
        period_granularity, period_start, period_end, source_record_key_norm
    )
    DO UPDATE SET
        source_run_id = EXCLUDED.source_run_id,
        value_numeric = EXCLUDED.value_numeric,
        value_text = EXCLUDED.value_text,
        value_raw = EXCLUDED.value_raw,
        currency_code = EXCLUDED.currency_code,
        is_estimated = EXCLUDED.is_estimated,
        observed_at = EXCLUDED.observed_at,
        loaded_at = EXCLUDED.loaded_at,
        payload = EXCLUDED.payload
    """
    with conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=100)


def delete_existing(conn, source_run_id: str, week_start: date) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM fact_metric_observation
            WHERE source_system='amocrm'
              AND source_run_id=%s
              AND period_granularity='week'
              AND period_start=%s
            """,
            (source_run_id, week_start),
        )


def build_row(
    metric_id: int,
    source_record_key: str,
    source_run_id: str,
    business_unit: str,
    week_start: date,
    week_end: date,
    value_numeric: Decimal,
    payload: dict,
) -> dict:
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
        "period_granularity": "week",
        "period_start": week_start,
        "period_end": week_end,
        "value_numeric": value_numeric,
        "value_text": None,
        "value_raw": str(value_numeric),
        "currency_code": None,
        "is_estimated": False,
        "observed_at": datetime.combine(week_end, dt_time(23, 59, 59), tzinfo=MSK).astimezone(timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--week-start", help="YYYY-MM-DD for the Monday of the week to load")
    parser.add_argument("--source-run-id", default="amocrm_weekly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    parser.add_argument("--env-file", default=str(ENV_PATH))
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    token = os.environ.get("AMOCRM_LONG_LIVED_TOKEN", "")
    base_url = os.environ.get("AMOCRM_BASE_URL", DEFAULT_BASE_URL)
    if not token or token == "replace_me":
        Path(args.report_path).parent.mkdir(parents=True, exist_ok=True)
        with Path(args.report_path).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["status", "reason"])
            writer.writeheader()
            writer.writerow({"status": "pending", "reason": "missing_amocrm_token"})
        print("pending: missing amoCRM token", file=sys.stderr)
        return 20

    week_start, week_end = period_bounds(date.fromisoformat(args.week_start) if args.week_start else None)
    created_from = to_ts(week_start, end_of_day=False)
    created_to = to_ts(week_end, end_of_day=True)
    pipeline_id, pipeline_name = pipeline_for_week(week_start)
    flow_status_name_to_metric = status_mapping_for_pipeline(pipeline_id)
    leads = fetch_all_leads_for_pipeline(base_url, token, pipeline_id, created_from, created_to)
    status_events = fetch_status_events(base_url, token, created_from, created_to)

    conn = psycopg2.connect(args.database_url)
    if args.delete_existing:
        with conn:
            delete_existing(conn, args.source_run_id, week_start)

    metric_ids = {"Number of leads": fetch_metric_id(conn, "Number of leads")}
    for metric_name in flow_status_name_to_metric.values():
        metric_ids[metric_name] = fetch_metric_id(conn, metric_name)

    pipeline_status_names = fetch_pipeline_statuses(base_url, token, pipeline_id)

    rows = []
    rows.append(
        build_row(
            metric_ids["Number of leads"],
            "b2b:Number of leads:general",
            args.source_run_id,
            "b2b",
            week_start,
            week_end,
            Decimal(len(leads)),
            {
                "loader": "import_amocrm_weekly_to_fact",
                "metric_name": "Number of leads",
                "pipeline_id": pipeline_id,
                "pipeline_name": pipeline_name,
                "count_logic": "lead created_at during week in the selected corporates pipeline for this period",
                "lead_ids": [int(lead["id"]) for lead in leads],
            },
        )
    )

    lead_ids_by_metric: dict[str, set[int]] = defaultdict(set)
    for event in status_events:
        value_after = event.get("value_after") or []
        if not value_after:
            continue
        lead_status = (value_after[0] or {}).get("lead_status") or {}
        if int(lead_status.get("pipeline_id") or 0) != pipeline_id:
            continue
        status_id = int(lead_status.get("id") or 0)
        status_name = pipeline_status_names.get(status_id, "")
        metric_name = flow_status_name_to_metric.get(status_name)
        if not metric_name:
            continue
        lead_ids_by_metric[metric_name].add(int(event["entity_id"]))

    report_rows: list[dict[str, str]] = []
    for status_name, metric_name in flow_status_name_to_metric.items():
        lead_ids = sorted(lead_ids_by_metric.get(metric_name, set()))
        rows.append(
            build_row(
                metric_ids[metric_name],
                f"b2b:{metric_name}:general",
                args.source_run_id,
                "b2b",
                week_start,
                week_end,
                Decimal(len(lead_ids)),
                {
                    "loader": "import_amocrm_weekly_to_fact",
                    "metric_name": metric_name,
                    "pipeline_id": pipeline_id,
                    "pipeline_name": pipeline_name,
                    "status_name": status_name,
                    "status_mapping_version": "legacy" if pipeline_id == PIPELINE_CORPORATES_LEGACY else "v2",
                    "count_logic": "distinct leads with lead_status_changed into target status during week",
                    "lead_ids": lead_ids,
                },
            )
        )
        report_rows.append(
            {
                "metric_name": metric_name,
                "status_name": status_name,
                "value": str(len(lead_ids)),
            }
        )

    with conn:
        insert_rows(conn, rows)
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric_name", "status_name", "value", "pipeline_id", "pipeline_name"])
        writer.writeheader()
        writer.writerow(
            {
                "metric_name": "Number of leads",
                "status_name": "",
                "value": str(len(leads)),
                "pipeline_id": str(pipeline_id),
                "pipeline_name": pipeline_name,
            }
        )
        for row in report_rows:
            row["pipeline_id"] = str(pipeline_id)
            row["pipeline_name"] = pipeline_name
        writer.writerows(report_rows)
    print(f"inserted={len(rows)} report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
