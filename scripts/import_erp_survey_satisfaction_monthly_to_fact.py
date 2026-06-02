#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

from import_erp_survey_satisfaction_weekly_to_fact import (
    UNITS,
    fetch_json,
    fetch_metric_ids,
    fmt_ts,
    insert_rows,
    normalize_q2,
    normalize_show,
)
from monthly_kpi_period_utils import month_bounds, start_end_datetimes


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "erp_survey_satisfaction_monthly_to_fact_import_report.csv"


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
    value_text: str | None = None,
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
        "period_granularity": "month",
        "period_start": period_start,
        "period_end": period_end,
        "value_numeric": value_numeric,
        "value_text": value_text,
        "value_raw": value_raw,
        "currency_code": None,
        "is_estimated": False,
        "observed_at": datetime.combine(period_end, time.min, tzinfo=timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--month-start", required=True)
    parser.add_argument("--source-run-id", default="erp_survey_satisfaction_monthly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    period_start, period_end = month_bounds(date.fromisoformat(args.month_start))
    dt_from, dt_to = start_end_datetimes(period_start, period_end)

    conn = psycopg2.connect(args.database_url)
    metric_ids = fetch_metric_ids(conn)
    if args.delete_existing:
        delete_existing(conn, args.source_run_id, period_start)
        conn.commit()

    report_rows: list[dict] = []
    insert_payload: list[dict] = []

    for unit, meta in UNITS.items():
        rows = fetch_json(meta["port"], "/survey/satisfaction", {"from": fmt_ts(dt_from), "to": fmt_ts(dt_to)})

        total_responses_general = 0
        total_responses_by_show = Counter()
        q1_count = Counter()
        q1_sum = defaultdict(Decimal)
        q2_counts_general = Counter()
        q2_counts_by_show = Counter()
        q3_counts_by_show = Counter()
        q4_counts_by_show = Counter()

        for row in rows:
            show_name = normalize_show(row.get("seance_name"))
            if not show_name:
                report_rows.append({"unit": unit, "metric_name": "survey/satisfaction", "scope": "", "status": "skipped", "value": "", "reason": "missing_show_name"})
                continue
            answers = row.get("answers") or {}
            q1 = str(answers.get("1") or "").strip()
            q2 = str(answers.get("2") or "").strip()
            q3 = str(answers.get("3") or "").strip()
            q4 = str(answers.get("4") or "").strip()
            if any([q1, q2, q3, q4]):
                total_responses_general += 1
                total_responses_by_show[show_name] += 1
            if q1 and q1.isdigit():
                q1_count[show_name] += 1
                q1_sum[show_name] += Decimal(q1)
            if q2:
                cat = normalize_q2(q2)
                q2_counts_general[cat] += 1
                q2_counts_by_show[(show_name, cat)] += 1
            if q3:
                q3_counts_by_show[(show_name, q3)] += 1
            if q4:
                q4_counts_by_show[(show_name, q4)] += 1

        def add(metric_name: str, key: str, show_name: str, value: Decimal, raw: str, payload: dict, value_text: str | None = None) -> None:
            insert_payload.append(
                base_row(
                    metric_ids[metric_name],
                    key,
                    args.source_run_id,
                    unit,
                    period_start,
                    period_end,
                    show_name,
                    value,
                    raw,
                    payload,
                    value_text=value_text,
                )
            )

        add("Number of post-show survey responses", f"{unit}|general|survey_responses|{period_start.isoformat()}", "general", Decimal(total_responses_general), str(total_responses_general), {"source": "erp_survey_satisfaction_monthly", "question": "any_nonempty", "unit": unit})
        report_rows.append({"unit": unit, "metric_name": "Number of post-show survey responses", "scope": "show:general", "status": "inserted", "value": str(total_responses_general), "reason": ""})
        for show_name, count in sorted(total_responses_by_show.items()):
            add("Number of post-show survey responses", f"{unit}|{show_name}|survey_responses|{period_start.isoformat()}", show_name, Decimal(count), str(count), {"source": "erp_survey_satisfaction_monthly", "question": "any_nonempty", "unit": unit})
            report_rows.append({"unit": unit, "metric_name": "Number of post-show survey responses", "scope": f"show:{show_name}", "status": "inserted", "value": str(count), "reason": ""})
        for show_name, count in sorted(q1_count.items()):
            add("Number of show rating responses", f"{unit}|{show_name}|q1_count|{period_start.isoformat()}", show_name, Decimal(count), str(count), {"source": "erp_survey_satisfaction_monthly", "question": 1, "measure": "count"})
            report_rows.append({"unit": unit, "metric_name": "Number of show rating responses", "scope": f"show:{show_name}", "status": "inserted", "value": str(count), "reason": ""})
        for show_name, total in sorted(q1_sum.items()):
            add("Sum of post-show ratings", f"{unit}|{show_name}|q1_sum|{period_start.isoformat()}", show_name, total, str(total), {"source": "erp_survey_satisfaction_monthly", "question": 1, "measure": "sum"})
            report_rows.append({"unit": unit, "metric_name": "Sum of post-show ratings", "scope": f"show:{show_name}", "status": "inserted", "value": str(total), "reason": ""})

        for category, count in sorted(q2_counts_general.items()):
            add("Number of source-attribution responses", f"{unit}|general|q2|{category}|{period_start.isoformat()}", "general", Decimal(count), str(count), {"source": "erp_survey_satisfaction_monthly", "question": 2, "response_category": category, "scope": "general"}, value_text=category)
            report_rows.append({"unit": unit, "metric_name": "Number of source-attribution responses", "scope": f"show:general q2:{category}", "status": "inserted", "value": str(count), "reason": ""})
        for (show_name, category), count in sorted(q2_counts_by_show.items()):
            add("Number of source-attribution responses", f"{unit}|{show_name}|q2|{category}|{period_start.isoformat()}", show_name, Decimal(count), str(count), {"source": "erp_survey_satisfaction_monthly", "question": 2, "response_category": category, "scope": "show"}, value_text=category)
            report_rows.append({"unit": unit, "metric_name": "Number of source-attribution responses", "scope": f"show:{show_name} q2:{category}", "status": "inserted", "value": str(count), "reason": ""})
        for (show_name, category), count in sorted(q3_counts_by_show.items()):
            add("Number of question 3 responses", f"{unit}|{show_name}|q3|{category}|{period_start.isoformat()}", show_name, Decimal(count), str(count), {"source": "erp_survey_satisfaction_monthly", "question": 3, "response_category": category}, value_text=category)
            report_rows.append({"unit": unit, "metric_name": "Number of question 3 responses", "scope": f"show:{show_name} q3:{category}", "status": "inserted", "value": str(count), "reason": ""})
        for (show_name, category), count in sorted(q4_counts_by_show.items()):
            add("Number of question 4 responses", f"{unit}|{show_name}|q4|{category}|{period_start.isoformat()}", show_name, Decimal(count), str(count), {"source": "erp_survey_satisfaction_monthly", "question": 4, "response_category": category}, value_text=category)
            report_rows.append({"unit": unit, "metric_name": "Number of question 4 responses", "scope": f"show:{show_name} q4:{category}", "status": "inserted", "value": str(count), "reason": ""})

    insert_rows(conn, insert_payload)
    conn.commit()
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["unit", "metric_name", "scope", "status", "value", "reason"])
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"period={period_start}..{period_end} inserted={len(insert_payload)} report={report_path}")


if __name__ == "__main__":
    main()
