#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import csv
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
DEFAULT_INPUT_CSV = ROOT / "artifacts" / "snapshots" / "manual_dividends_total_history.csv"
DEFAULT_REPORT_CSV = ROOT / "artifacts" / "run_reports" / "manual_dividends_total_history_import_report.csv"
SOURCE_SYSTEM = "manual_dividends_total_history"
SOURCE_RUN_ID = f"manual_dividends_total_history_{date.today().isoformat()}"
REFERENCE_DOC = "/Users/Peter/Documents/Morpheus Metrics/legacy/docs/manual_dividends_total_history.md"

INSERT_SQL = """
INSERT INTO fact_metric_observation (
    metric_id,
    rule_id,
    source_system,
    source_record_key,
    source_run_id,
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
    payload
)
VALUES (
    %(metric_id)s,
    NULL,
    %(source_system)s,
    %(source_record_key)s,
    %(source_run_id)s,
    'total',
    NULL,
    NULL,
    NULL,
    'month',
    %(period_start)s,
    %(period_end)s,
    %(value_numeric)s,
    NULL,
    %(value_raw)s,
    'RUB',
    FALSE,
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
    value_numeric = EXCLUDED.value_numeric,
    value_raw = EXCLUDED.value_raw,
    payload = EXCLUDED.payload,
    loaded_at = NOW()
"""

DELETE_SQL = """
DELETE FROM fact_metric_observation
WHERE source_system = %(source_system)s
  AND business_unit = 'total'
"""


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def should_keep_period(period_start: date, month_start_value: date | None, month_end_value: date | None) -> bool:
    if month_start_value and period_start < month_start_value:
        return False
    if month_end_value and period_start > month_end_value:
        return False
    return True


def load_entries(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "status",
                "period_start",
                "entry_date",
                "amount_rub",
                "source_group",
                "entry_note",
                "reason",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT_CSV))
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_CSV))
    parser.add_argument("--source-run-id", default=SOURCE_RUN_ID)
    parser.add_argument("--month-start", help="Optional YYYY-MM-DD lower month bound")
    parser.add_argument("--month-end", help="Optional YYYY-MM-DD upper month bound")
    parser.add_argument("--delete-existing", action="store_true")
    args = parser.parse_args()

    input_csv = Path(args.input_csv)
    report_path = Path(args.report_path)
    source_run_id = args.source_run_id
    month_start_value = date.fromisoformat(args.month_start) if args.month_start else None
    month_end_value = date.fromisoformat(args.month_end) if args.month_end else None
    entries = load_entries(input_csv)

    monthly_entries: dict[date, list[dict[str, str]]] = defaultdict(list)
    for entry in entries:
        entry_date = datetime.strptime(entry["entry_date"], "%Y-%m-%d").date()
        monthly_entries[month_start(entry_date)].append(entry)

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT metric_id FROM metric_catalogue WHERE metric_name = 'Dividends'")
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("Metric 'Dividends' is missing from metric_catalogue.")
                metric_id = int(row[0])

                if args.delete_existing:
                    delete_sql = DELETE_SQL
                    delete_params = {"source_system": SOURCE_SYSTEM}
                    if month_start_value:
                        delete_sql += "\n  AND period_start >= %(month_start)s"
                        delete_params["month_start"] = month_start_value
                    if month_end_value:
                        delete_sql += "\n  AND period_start <= %(month_end)s"
                        delete_params["month_end"] = month_end_value
                    cur.execute(delete_sql, delete_params)

                cur.execute(
                    """
                    SELECT period_start
                    FROM monthly_pnl_total_history
                    WHERE metric_name = 'Dividends'
                      AND business_unit = 'total'
                    """
                )
                existing_months = {r[0] for r in cur.fetchall()}

                inserts = []
                report_rows: list[dict[str, str]] = []
                for period_start in sorted(monthly_entries):
                    if not should_keep_period(period_start, month_start_value, month_end_value):
                        continue
                    group = monthly_entries[period_start]
                    if period_start in existing_months:
                        for entry in group:
                            report_rows.append(
                                {
                                    "status": "skipped",
                                    "period_start": period_start.isoformat(),
                                    "entry_date": entry["entry_date"],
                                    "amount_rub": entry["amount_rub"],
                                    "source_group": entry["source_group"],
                                    "entry_note": entry["entry_note"],
                                    "reason": "month_already_present_in_total_history",
                                }
                            )
                        continue

                    total = sum(Decimal(entry["amount_rub"]) for entry in group)
                    record_key = f"manual_dividends_total_history:{period_start.isoformat()}"
                    payload = {
                        "reference_doc": REFERENCE_DOC,
                        "source_csv": str(input_csv),
                        "fill_policy": "insert_only_when_total_month_missing",
                        "entry_count": len(group),
                        "entries": group,
                    }
                    inserts.append(
                        {
                            "metric_id": metric_id,
                            "source_system": SOURCE_SYSTEM,
                            "source_record_key": record_key,
                            "source_run_id": source_run_id,
                            "period_start": period_start,
                            "period_end": month_end(period_start),
                            "value_numeric": total,
                            "value_raw": format(total, "f"),
                            "payload": Json(payload),
                        }
                    )
                    for entry in group:
                        report_rows.append(
                            {
                                "status": "inserted",
                                "period_start": period_start.isoformat(),
                                "entry_date": entry["entry_date"],
                                "amount_rub": entry["amount_rub"],
                                "source_group": entry["source_group"],
                                "entry_note": entry["entry_note"],
                                "reason": "",
                            }
                        )

                execute_batch(cur, INSERT_SQL, inserts, page_size=100)
                write_report(report_path, report_rows)
                print(
                    {
                        "inserted_months": len(inserts),
                        "report_path": str(report_path),
                        "source_run_id": source_run_id,
                    }
                )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
