#!/usr/bin/env python3
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import execute_batch, Json


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS legacy_monthly_pnl_reference (
    id BIGSERIAL PRIMARY KEY,
    source_file_name TEXT NOT NULL,
    source_file_path TEXT,
    source_row_number INTEGER NOT NULL,
    source_column_number INTEGER NOT NULL,
    business_unit_raw TEXT,
    business_unit_key TEXT,
    metric_name TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_label TEXT,
    value_raw TEXT NOT NULL,
    value_numeric NUMERIC(18,6),
    value_type TEXT NOT NULL,
    row_context JSONB,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT legacy_monthly_pnl_reference_value_type_chk
        CHECK (value_type IN ('number', 'percent', 'text')),
    CONSTRAINT legacy_monthly_pnl_reference_unique
        UNIQUE (source_file_name, source_row_number, source_column_number)
);

CREATE INDEX IF NOT EXISTS idx_legacy_monthly_pnl_reference_metric_period
    ON legacy_monthly_pnl_reference(metric_name, period_start);

CREATE INDEX IF NOT EXISTS idx_legacy_monthly_pnl_reference_unit_period
    ON legacy_monthly_pnl_reference(business_unit_key, period_start);
"""


INSERT_SQL = """
INSERT INTO legacy_monthly_pnl_reference (
    source_file_name,
    source_file_path,
    source_row_number,
    source_column_number,
    business_unit_raw,
    business_unit_key,
    metric_name,
    period_start,
    period_label,
    value_raw,
    value_numeric,
    value_type,
    row_context
)
VALUES (
    %(source_file_name)s,
    %(source_file_path)s,
    %(source_row_number)s,
    %(source_column_number)s,
    %(business_unit_raw)s,
    %(business_unit_key)s,
    %(metric_name)s,
    %(period_start)s,
    %(period_label)s,
    %(value_raw)s,
    %(value_numeric)s,
    %(value_type)s,
    %(row_context)s
)
ON CONFLICT (source_file_name, source_row_number, source_column_number)
DO UPDATE SET
    business_unit_raw = EXCLUDED.business_unit_raw,
    business_unit_key = EXCLUDED.business_unit_key,
    metric_name = EXCLUDED.metric_name,
    period_start = EXCLUDED.period_start,
    period_label = EXCLUDED.period_label,
    value_raw = EXCLUDED.value_raw,
    value_numeric = EXCLUDED.value_numeric,
    value_type = EXCLUDED.value_type,
    row_context = EXCLUDED.row_context,
    source_file_path = EXCLUDED.source_file_path,
    loaded_at = NOW();
"""


def normalize_unit(raw: str) -> Optional[str]:
    raw = (raw or "").strip()
    mapping = {
        "Москва": "b2c_moscow",
        "Спб": "b2c_spb",
        "СПб": "b2c_spb",
        "B2B": "b2b",
        "Франшиза": "franchise",
        "Общее": "general",
    }
    return mapping.get(raw)


def parse_period(cell: str):
    value = (cell or "").strip()
    if not value:
        return None
    parts = value.split(".")
    if len(parts) != 3:
        return None
    day, month, year = parts
    day = day.zfill(2)
    month = month.zfill(2)
    year = year.zfill(4)
    return datetime.strptime(f"{day}.{month}.{year}", "%d.%m.%Y").date()


def parse_value(raw: str):
    text = (raw or "").strip().replace("\xa0", "").replace(" ", "")
    if not text:
        return None, None
    if text.endswith("%"):
        num = text[:-1].replace(",", ".")
        try:
            return float(num), "percent"
        except ValueError:
            return None, "text"
    normalized = text.replace(",", ".")
    try:
        return float(normalized), "number"
    except ValueError:
        return None, "text"


def load_rows(csv_path: Path):
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    if len(rows) < 3:
        raise ValueError("CSV is too short to contain header rows")

    date_row = rows[1]
    label_row = rows[2]
    month_columns = []
    for idx in range(2, len(date_row)):
        period_start = parse_period(date_row[idx])
        if not period_start:
            continue
        period_label = label_row[idx].strip() if idx < len(label_row) else ""
        month_columns.append((idx, period_start, period_label))

    records = []
    for row_number, row in enumerate(rows[3:], start=4):
        if len(row) < 2:
            continue
        business_unit_raw = row[0].strip()
        metric_name = row[1].strip()
        if not business_unit_raw or business_unit_raw == "Бизнес Юнит" or not metric_name:
            continue

        business_unit_key = normalize_unit(business_unit_raw)
        row_snapshot = {
            "business_unit_raw": business_unit_raw,
            "metric_name": metric_name,
            "values": row[2:],
        }

        for col_idx, period_start, period_label in month_columns:
            if col_idx >= len(row):
                continue
            value_raw = row[col_idx].strip()
            if not value_raw:
                continue
            value_numeric, value_type = parse_value(value_raw)
            if value_type is None:
                continue
            records.append(
                {
                    "source_file_name": csv_path.name,
                    "source_file_path": str(csv_path),
                    "source_row_number": row_number,
                    "source_column_number": col_idx + 1,
                    "business_unit_raw": business_unit_raw,
                    "business_unit_key": business_unit_key,
                    "metric_name": metric_name,
                    "period_start": period_start,
                    "period_label": period_label,
                    "value_raw": value_raw,
                    "value_numeric": value_numeric,
                    "value_type": value_type,
                    "row_context": Json(row_snapshot, dumps=json.dumps),
                }
            )
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    records = load_rows(csv_path)

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_SQL)
                execute_batch(cur, INSERT_SQL, records, page_size=500)
        print(f"loaded_rows={len(records)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
