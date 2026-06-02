#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

from import_erp_salary_variable_weekly_to_fact import (
    SHOW_CANON,
    UNITS,
    fetch_json,
    fetch_metric_id,
    fmt_ts,
    insert_rows,
)
from monthly_kpi_period_utils import month_bounds, start_end_datetimes


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "erp_salary_variable_monthly_to_fact_import_report.csv"


def delete_existing(conn, source_run_id: str, period_start: date) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM fact_metric_observation
            WHERE source_system='erp'
              AND source_run_id=%s
              AND period_granularity='month'
              AND period_start=%s
            """,
            (source_run_id, period_start),
        )


def base_row(metric_id: int, source_record_key: str, source_run_id: str, business_unit: str, period_start: date, period_end: date, show_name: str, value_numeric: Decimal, value_raw: str, payload: dict) -> dict:
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
        "period_granularity": "month",
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
    parser.add_argument("--month-start", required=True)
    parser.add_argument("--source-run-id", default="erp_salary_variable_monthly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    period_start, period_end = month_bounds(date.fromisoformat(args.month_start))
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
        for payload in salary_period.values():
            salary_total += Decimal(str(payload.get("shows_income") or 0))
            for seance in payload.get("seances") or []:
                canon = SHOW_CANON.get(seance.get("event_title"))
                amount = Decimal(str(seance.get("salary_payed") or 0))
                if not canon:
                    report_rows.append({"unit": unit, "metric_name": "Costs - Salary variable", "scope": seance.get("event_title") or "", "status": "skipped", "value": str(amount), "reason": "unknown_show_name_salary"})
                    continue
                show_salary[canon] += amount

        allocated_bonus = defaultdict(Decimal)
        unallocated_bonus_total = Decimal("0")
        for bonus in bonuses:
            amount = Decimal(str(bonus.get("amount") or 0))
            seance_id = bonus.get("seance_id")
            if seance_id is None:
                unallocated_bonus_total += amount
                continue
            show_row = shows_by_internal_id.get(int(seance_id))
            if not show_row:
                unallocated_bonus_total += amount
                continue
            canon = SHOW_CANON.get(show_row.get("event_title"))
            if not canon:
                unallocated_bonus_total += amount
                continue
            allocated_bonus[canon] += amount

        all_shows = sorted(set(show_salary) | set(allocated_bonus))
        for show_name in all_shows:
            salary_component = show_salary.get(show_name, Decimal("0"))
            bonus_component = allocated_bonus.get(show_name, Decimal("0"))
            total_value = salary_component + bonus_component
            rows_to_insert.append(
                base_row(
                    metric_id,
                    f"{unit}|{show_name}|{period_start.isoformat()}",
                    args.source_run_id,
                    unit,
                    period_start,
                    period_end,
                    show_name,
                    total_value,
                    str(total_value),
                    {
                        "source": "erp_salary_variable_monthly",
                        "salary_component": float(salary_component),
                        "bonus_component_allocated": float(bonus_component),
                        "unit_unallocated_bonus_total": float(unallocated_bonus_total),
                        "period_start": period_start.isoformat(),
                        "period_end": period_end.isoformat(),
                    },
                )
            )
            report_rows.append({"unit": unit, "metric_name": "Costs - Salary variable", "scope": f"show:{show_name}", "status": "inserted", "value": str(total_value), "reason": ""})

        total_with_bonus = salary_total + sum(allocated_bonus.values())
        rows_to_insert.append(
            base_row(
                metric_id,
                f"{unit}|general|{period_start.isoformat()}",
                args.source_run_id,
                unit,
                period_start,
                period_end,
                "general",
                total_with_bonus,
                str(total_with_bonus),
                {
                    "source": "erp_salary_variable_monthly",
                    "salary_total": float(salary_total),
                    "bonus_total_allocated": float(sum(allocated_bonus.values())),
                    "unit_unallocated_bonus_total": float(unallocated_bonus_total),
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                },
            )
        )
        report_rows.append({"unit": unit, "metric_name": "Costs - Salary variable", "scope": "show:general", "status": "inserted", "value": str(total_with_bonus), "reason": ""})

    insert_rows(conn, rows_to_insert)
    conn.commit()
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["unit", "metric_name", "scope", "status", "value", "reason"])
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"period={period_start}..{period_end} inserted={len(rows_to_insert)} report={report_path}")


if __name__ == "__main__":
    main()
