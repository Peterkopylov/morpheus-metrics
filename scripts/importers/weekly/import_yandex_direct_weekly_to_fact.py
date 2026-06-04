#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import ssl
import urllib.request
from datetime import date, datetime, time as dt_time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "yandex_direct_weekly_to_fact_import_report.csv"
ENV_MAIN = ROOT / ".env.yandex_direct"
ENV_SPB = ROOT / ".env.yandex_direct_spb"
SSL_CONTEXT = ssl._create_unverified_context()
MSK = timezone(timedelta(hours=3))

REPORT_URL = "https://api.direct.yandex.com/json/v5/reports"


def period_bounds(last_full_week_start: date | None = None) -> tuple[date, date]:
    if last_full_week_start:
        return last_full_week_start, last_full_week_start + timedelta(days=6)
    today = datetime.now(MSK).date()
    current_week_start = today - timedelta(days=today.weekday())
    last_week_start = current_week_start - timedelta(days=7)
    return last_week_start, last_week_start + timedelta(days=6)


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip()
    return values


def direct_report(access_token: str, date_from: str, date_to: str) -> list[dict[str, str]]:
    body = {
        "params": {
            "SelectionCriteria": {"DateFrom": date_from, "DateTo": date_to},
            "FieldNames": ["CampaignId", "CampaignName", "Cost", "Clicks", "Impressions"],
            "ReportName": "Weekly fact-layer direct costs",
            "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
            "DateRangeType": "CUSTOM_DATE",
            "Format": "TSV",
            "IncludeVAT": "YES",
            "IncludeDiscount": "NO",
        }
    }
    req = urllib.request.Request(
        REPORT_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept-Language": "ru",
            "Content-Type": "application/json; charset=utf-8",
            "processingMode": "auto",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
        text = resp.read().decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    if lines and lines[0].startswith('"'):
        lines = lines[1:]
    if lines and lines[-1].startswith("Total rows:"):
        lines = lines[:-1]
    reader = csv.DictReader(lines, delimiter="\t")
    return list(reader)


def classify_campaign(name: str, cabinet: str) -> str:
    lower = name.strip().lower()
    if lower.startswith("b2b"):
        return "b2b"
    if cabinet == "spb" and "b2b спб" in lower:
        return "b2b"
    return "b2c_spb" if cabinet == "spb" else "b2c_moscow"


def fetch_metric_id(conn, metric_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute("select metric_id from metric_catalogue where metric_name=%s", (metric_name,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"Metric not found: {metric_name}")
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
            WHERE source_system='yandex_direct'
              AND source_run_id=%s
              AND period_granularity='week'
              AND period_start=%s
            """,
            (source_run_id, week_start),
        )


def parse_micros(value: str | None) -> Decimal:
    if value in {None, "", "--"}:
        return Decimal("0")
    return (Decimal(str(value)) / Decimal("1000000")).quantize(Decimal("0.01"))


def build_row(
    metric_id: int,
    metric_key: str,
    business_unit: str,
    value_numeric: Decimal,
    week_start: date,
    week_end: date,
    source_run_id: str,
    payload: dict,
) -> dict:
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
        "period_granularity": "week",
        "period_start": week_start,
        "period_end": week_end,
        "value_numeric": value_numeric,
        "value_text": None,
        "value_raw": str(value_numeric),
        "currency_code": "RUB",
        "is_estimated": False,
        "observed_at": datetime.combine(week_end, dt_time(23, 59, 59), tzinfo=MSK).astimezone(timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--week-start", help="YYYY-MM-DD for the Monday of the week to load")
    parser.add_argument("--source-run-id", default="yandex_direct_weekly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    week_start, week_end = period_bounds(date.fromisoformat(args.week_start) if args.week_start else None)
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
        rows = direct_report(token, week_start.isoformat(), week_end.isoformat())
        for row in rows:
            cost = parse_micros(row.get("Cost"))
            campaign_name = row.get("CampaignName") or ""
            bucket = classify_campaign(campaign_name, cabinet)
            aggregates[bucket] += cost
            campaign_payload[bucket].append(
                {
                    "cabinet": cabinet,
                    "campaign_id": row.get("CampaignId"),
                    "campaign_name": campaign_name,
                    "cost": str(cost),
                    "clicks": row.get("Clicks"),
                    "impressions": row.get("Impressions"),
                }
            )

    conn = psycopg2.connect(args.database_url)
    metric_id = fetch_metric_id(conn, metric_name)
    if args.delete_existing:
        with conn:
            delete_existing(conn, args.source_run_id, week_start)

    insert_buffer = []
    for business_unit in ("b2c_moscow", "b2c_spb", "b2b"):
        insert_buffer.append(
            build_row(
                metric_id,
                "marketing_costs",
                business_unit,
                aggregates[business_unit],
                week_start,
                week_end,
                args.source_run_id,
                {
                    "loader": "import_yandex_direct_weekly_to_fact",
                    "metric_name": metric_name,
                    "campaigns": campaign_payload[business_unit],
                },
            )
        )
        report_rows.append(
            {
                "business_unit": business_unit,
                "metric_name": metric_name,
                "status": "inserted",
                "value_numeric": str(aggregates[business_unit]),
                "campaigns_count": str(len(campaign_payload[business_unit])),
            }
        )

    with conn:
        insert_rows(conn, insert_buffer)
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["business_unit", "metric_name", "status", "value_numeric", "campaigns_count"])
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"inserted={len(insert_buffer)} report={report_path}")


if __name__ == "__main__":
    main()
