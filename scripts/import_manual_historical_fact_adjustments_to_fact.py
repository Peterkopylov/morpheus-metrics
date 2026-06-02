#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
DEFAULT_INPUT_CSV = ROOT / "generated/manual_historical_fact_adjustments.csv"
DEFAULT_REPORT_CSV = ROOT / "generated/manual_historical_fact_adjustments_import_report.csv"
SOURCE_SYSTEM = "google_sheets_monthly_economics_historical"
SOURCE_RUN_ID = f"manual_historical_fact_adjustments_{date.today().isoformat()}"
RECORD_KEY_PREFIX = "manual_historical_adjustment:"
REFERENCE_DOC = "/Users/Peter/Documents/Morpheus Metrics/docs/manual_historical_fact_adjustments.md"

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
    %(business_unit)s,
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
  AND source_record_key LIKE %(record_key_like)s
"""


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def load_rows(path: Path) -> list[dict[str, str]]:
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
                "metric_name",
                "business_unit",
                "value_numeric",
                "note",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT_CSV))
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_CSV))
    parser.add_argument("--delete-existing", action="store_true")
    args = parser.parse_args()

    input_csv = Path(args.input_csv)
    report_path = Path(args.report_path)
    rows = load_rows(input_csv)

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT metric_id, metric_name FROM metric_catalogue")
                metric_ids = {metric_name: metric_id for metric_id, metric_name in cur.fetchall()}

                if args.delete_existing:
                    cur.execute(
                        DELETE_SQL,
                        {
                            "source_system": SOURCE_SYSTEM,
                            "record_key_like": f"{RECORD_KEY_PREFIX}%",
                        },
                    )

                inserts = []
                report_rows: list[dict[str, str]] = []
                for row in rows:
                    metric_name = row["metric_name"]
                    metric_id = metric_ids.get(metric_name)
                    if metric_id is None:
                        raise RuntimeError(f"Metric '{metric_name}' is missing from metric_catalogue.")

                    period_start = date.fromisoformat(row["period_start"])
                    business_unit = row["business_unit"]
                    value_numeric = Decimal(row["value_numeric"])
                    note = row["note"]
                    source_record_key = (
                        f"{RECORD_KEY_PREFIX}{period_start.isoformat()}:{metric_name}:{business_unit}"
                    )
                    payload = {
                        "reference_doc": REFERENCE_DOC,
                        "source_csv": str(input_csv),
                        "manual_adjustment": True,
                        "note": note,
                    }
                    inserts.append(
                        {
                            "metric_id": metric_id,
                            "source_system": SOURCE_SYSTEM,
                            "source_record_key": source_record_key,
                            "source_run_id": SOURCE_RUN_ID,
                            "business_unit": business_unit,
                            "period_start": period_start,
                            "period_end": month_end(period_start),
                            "value_numeric": value_numeric,
                            "value_raw": format(value_numeric, "f"),
                            "payload": Json(payload),
                        }
                    )
                    report_rows.append(
                        {
                            "status": "inserted",
                            "period_start": period_start.isoformat(),
                            "metric_name": metric_name,
                            "business_unit": business_unit,
                            "value_numeric": format(value_numeric, "f"),
                            "note": note,
                        }
                    )

                execute_batch(cur, INSERT_SQL, inserts, page_size=100)
                write_report(report_path, report_rows)
                print({"inserted_rows": len(inserts), "report_path": str(report_path)})
    finally:
        conn.close()


if __name__ == "__main__":
    main()
