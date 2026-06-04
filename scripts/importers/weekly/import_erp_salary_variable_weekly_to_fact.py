#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import ssl
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib import request

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "erp_salary_variable_weekly_to_fact_import_report.csv"
SSL_CONTEXT = ssl._create_unverified_context()
MSK = timezone(timedelta(hours=3))
ERP_BASE = "https://morpheus-server.ru:{port}{path}"

UNITS = {
    "b2c_moscow": {"port": 45010},
    "b2c_spb": {"port": 45011},
}

SHOW_CANON = {
    "Ответ Гиппократа": "Ответ Гиппократа",
    "До свадьбы доживёт": "До свадьбы доживёт",
    "22'07": "22'07",
    "ВДОХ": "ВДОХ",
    "Иное место": "Иное место",
    "Поезд, Чехов, два орла": "Поезд, Чехов, два орла",
    "Загадка амулета": "Загадка Амулета",
    "Загадка Амулета": "Загадка Амулета",
    "Судный день": "Судный день",
}


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S+03:00")


def fetch_json(port: int, path: str, body: dict) -> list | dict:
    payload = json.dumps(body).encode("utf-8")
    req = request.Request(
        ERP_BASE.format(port=port, path=path),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def period_bounds(last_full_week_start: date | None = None) -> tuple[date, date]:
    if last_full_week_start:
        return last_full_week_start, last_full_week_start + timedelta(days=6)
    today = datetime.now(MSK).date()
    current_week_start = today - timedelta(days=today.weekday())
    last_week_start = current_week_start - timedelta(days=7)
    return last_week_start, last_week_start + timedelta(days=6)


def start_end_datetimes(week_start: date, week_end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(week_start, time.min, tzinfo=MSK),
        datetime.combine(week_end, time(23, 59, 59), tzinfo=MSK),
    )


def fetch_metric_id(conn, metric_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute("select metric_id from metric_catalogue where metric_name=%s", (metric_name,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"Metric not found in metric_catalogue: {metric_name}")
        return row[0]


def insert_rows(conn, rows: list[dict]) -> None:
    if not rows:
        return
    sql = """
    INSERT INTO fact_metric_observation (
        metric_id,
        rule_id,
        source_system,
        source_record_key,
        source_run_id,
        source_cell_a1,
        source_cell_url,
        business_unit,
        show_name,
        partner_name,
        channel_name,
        period_granularity,
        period_start,
        period_end,
        value_numeric,
        value_text,
        value_raw,
        currency_code,
        is_estimated,
        observed_at,
        loaded_at,
        payload
    )
    VALUES (
        %(metric_id)s,
        %(rule_id)s,
        %(source_system)s,
        %(source_record_key)s,
        %(source_run_id)s,
        %(source_cell_a1)s,
        %(source_cell_url)s,
        %(business_unit)s,
        %(show_name)s,
        %(partner_name)s,
        %(channel_name)s,
        %(period_granularity)s,
        %(period_start)s,
        %(period_end)s,
        %(value_numeric)s,
        %(value_text)s,
        %(value_raw)s,
        %(currency_code)s,
        %(is_estimated)s,
        %(observed_at)s,
        %(loaded_at)s,
        %(payload)s
    )
    ON CONFLICT (
        metric_id,
        source_system,
        business_unit,
        show_name_norm,
        partner_name_norm,
        channel_name_norm,
        period_granularity,
        period_start,
        period_end,
        source_record_key_norm
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
        execute_batch(cur, sql, rows, page_size=200)


def delete_existing(conn, source_run_id: str, week_start: date) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM fact_metric_observation
            WHERE source_system='erp'
              AND source_run_id=%s
              AND period_granularity='week'
              AND period_start=%s
            """,
            (source_run_id, week_start),
        )


def base_row(
    metric_id: int,
    source_record_key: str,
    source_run_id: str,
    business_unit: str,
    period_start: date,
    period_end: date,
    show_name: str,
    value_numeric: Decimal,
    value_raw: str,
    payload: dict,
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "metric_id": metric_id,
        "rule_id": None,
        "source_system": "erp",
        "source_record_key": source_record_key,
        "source_run_id": source_run_id,
        "source_cell_a1": None,
        "source_cell_url": None,
        "business_unit": business_unit,
        "show_name": show_name,
        "partner_name": None,
        "channel_name": None,
        "period_granularity": "week",
        "period_start": period_start,
        "period_end": period_end,
        "value_numeric": value_numeric,
        "value_text": None,
        "value_raw": value_raw,
        "currency_code": "RUB",
        "is_estimated": False,
        "observed_at": datetime.combine(period_end, time.min, tzinfo=timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--week-start", help="YYYY-MM-DD for the Monday of the week to load")
    parser.add_argument("--source-run-id", default="erp_salary_variable_weekly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    week_start = date.fromisoformat(args.week_start) if args.week_start else None
    period_start, period_end = period_bounds(week_start)
    dt_from, dt_to = start_end_datetimes(period_start, period_end)

    conn = psycopg2.connect(args.database_url)
    metric_id = fetch_metric_id(conn, "Costs - Salary variable")

    if args.delete_existing:
        delete_existing(conn, args.source_run_id, period_start)
        conn.commit()

    rows_to_insert: list[dict] = []
    report_rows: list[dict] = []

    for unit, meta in UNITS.items():
        port = meta["port"]
        salary_period = fetch_json(port, "/salaries/period", {"from": fmt_ts(dt_from), "to": fmt_ts(dt_to)})
        shows = fetch_json(port, "/shows/get", {"from": fmt_ts(dt_from), "to": fmt_ts(dt_to)})
        bonuses = fetch_json(port, "/bonuses", {"from": fmt_ts(dt_from), "to": fmt_ts(dt_to)})

        shows_by_internal_id = {int(s["ID"]): s for s in shows if s.get("ID") is not None}

        show_salary = defaultdict(Decimal)
        salary_total = Decimal("0")
        for alias, payload in salary_period.items():
            salary_total += Decimal(str(payload.get("shows_income") or 0))
            for seance in payload.get("seances") or []:
                title = seance.get("event_title")
                canon = SHOW_CANON.get(title)
                amount = Decimal(str(seance.get("salary_payed") or 0))
                if not canon:
                    report_rows.append(
                        {"unit": unit, "metric_name": "Costs - Salary variable", "scope": title or "", "status": "skipped", "value": str(amount), "reason": "unknown_show_name_salary"}
                    )
                    continue
                show_salary[canon] += amount

        allocated_bonus = defaultdict(Decimal)
        bonus_total = Decimal("0")
        unallocated_bonus_total = Decimal("0")
        for bonus in bonuses:
            amount = Decimal(str(bonus.get("amount") or 0))
            bonus_total += amount
            seance_id = bonus.get("seance_id")
            if seance_id is None:
                unallocated_bonus_total += amount
                report_rows.append(
                    {"unit": unit, "metric_name": "Costs - Salary variable", "scope": "general", "status": "skipped", "value": str(amount), "reason": "bonus_without_seance_id"}
                )
                continue
            show_row = shows_by_internal_id.get(int(seance_id))
            if not show_row:
                unallocated_bonus_total += amount
                report_rows.append(
                    {"unit": unit, "metric_name": "Costs - Salary variable", "scope": str(seance_id), "status": "skipped", "value": str(amount), "reason": "bonus_seance_not_found_in_shows"}
                )
                continue
            canon = SHOW_CANON.get(show_row.get("event_title"))
            if not canon:
                unallocated_bonus_total += amount
                report_rows.append(
                    {"unit": unit, "metric_name": "Costs - Salary variable", "scope": show_row.get("event_title") or "", "status": "skipped", "value": str(amount), "reason": "unknown_show_name_bonus"}
                )
                continue
            allocated_bonus[canon] += amount

        all_shows = sorted(set(show_salary) | set(allocated_bonus))
        for show_name in all_shows:
            salary_component = show_salary.get(show_name, Decimal("0"))
            bonus_component = allocated_bonus.get(show_name, Decimal("0"))
            total_value = salary_component + bonus_component
            row = base_row(
                metric_id=metric_id,
                source_record_key=f"{unit}|{show_name}|{period_start.isoformat()}",
                source_run_id=args.source_run_id,
                business_unit=unit,
                period_start=period_start,
                period_end=period_end,
                show_name=show_name,
                value_numeric=total_value,
                value_raw=str(total_value),
                payload={
                    "source": "erp_salary_variable",
                    "salary_component": float(salary_component),
                    "bonus_component_allocated": float(bonus_component),
                    "unit_unallocated_bonus_total": float(unallocated_bonus_total),
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                },
            )
            rows_to_insert.append(row)
            report_rows.append(
                {
                    "unit": unit,
                    "metric_name": "Costs - Salary variable",
                    "scope": f"show:{show_name}",
                    "status": "inserted",
                    "value": str(total_value),
                    "reason": "",
                }
            )

        general_total = salary_total + bonus_total
        rows_to_insert.append(
            base_row(
                metric_id=metric_id,
                source_record_key=f"{unit}|general|{period_start.isoformat()}",
                source_run_id=args.source_run_id,
                business_unit=unit,
                period_start=period_start,
                period_end=period_end,
                show_name="general",
                value_numeric=general_total,
                value_raw=str(general_total),
                payload={
                    "source": "erp_salary_variable",
                    "salary_total": float(salary_total),
                    "bonus_total": float(bonus_total),
                    "bonus_allocated_to_shows": float(sum(allocated_bonus.values(), Decimal("0"))),
                    "bonus_unallocated_tail": float(unallocated_bonus_total),
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                },
            )
        )
        report_rows.append(
            {
                "unit": unit,
                "metric_name": "Costs - Salary variable",
                "scope": "show:general",
                "status": "inserted",
                "value": str(general_total),
                "reason": "",
            }
        )

        report_rows.append(
            {
                "unit": unit,
                "metric_name": "Costs - Salary variable",
                "scope": "general",
                "status": "skipped" if unallocated_bonus_total else "info",
                "value": str(unallocated_bonus_total),
                "reason": "unallocated_bonus_tail" if unallocated_bonus_total else "all_bonus_allocated",
            }
        )

    insert_rows(conn, rows_to_insert)
    conn.commit()
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["unit", "metric_name", "scope", "status", "value", "reason"])
        writer.writeheader()
        writer.writerows(report_rows)

    inserted = sum(1 for row in report_rows if row["status"] == "inserted")
    skipped = sum(1 for row in report_rows if row["status"] == "skipped")
    print(f"period={period_start}..{period_end} inserted={inserted} skipped={skipped} report={report_path}")


if __name__ == "__main__":
    main()
