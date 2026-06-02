#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import csv
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import psycopg2
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
DEFAULT_MAPPING_PATH = ROOT / "generated/historical_sheet_canonical_metric_mapping.csv"
DEFAULT_REPORT_PATH = ROOT / "generated/historical_monthly_economics_sheet_to_fact_import_report.csv"
DEFAULT_GOOGLE_SERVICE_ACCOUNT_JSON = Path(
    os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "/Users/Peter/Downloads/appointments-1084-0dcc0dd99d1b.json",
    )
)

SPREADSHEET_ID = "19Ssy4Esp0vG_7yIHA8mNpfuzjvko12TdQEklEPFxfC0"
SHEET_GID = "582113259"
SHEET_NAME = "ЭКОНОМИКА (P&L) - для базы"
SOURCE_SYSTEM = "google_sheets_monthly_economics_historical"
SOURCE_RUN_ID = f"{SPREADSHEET_ID}:{SHEET_GID}"
MERGE_RULE_SUM = "sum"

# Addressed source quirks that should survive reimports.
# Keys are exact A1 cell references from the historical sheet.
CELL_NUMERIC_OVERRIDES: dict[str, Decimal] = {
    "AV221": Decimal("1000000"),
}

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
    %(show_name)s,
    %(partner_name)s,
    %(channel_name)s,
    'month',
    %(period_start)s,
    %(period_end)s,
    %(value_numeric)s,
    NULL,
    %(value_raw)s,
    %(currency_code)s,
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
    currency_code = EXCLUDED.currency_code,
    loaded_at = NOW()
"""

DELETE_SQL = """
DELETE FROM fact_metric_observation
WHERE source_system = %(source_system)s
  AND source_run_id = %(source_run_id)s
"""


@dataclass(frozen=True)
class MappingRow:
    row_number: int
    source_business_unit: str
    source_label: str
    formula_or_input: str
    filled_cell_count: int
    layer: str
    canonical_metric: str
    business_unit: str
    show: str
    channel: str
    agent: str
    merge_rule: str
    mapping_status: str
    mapping_note: str


def col_to_a1(col_number_1_based: int) -> str:
    result = ""
    num = col_number_1_based
    while num > 0:
        num, rem = divmod(num - 1, 26)
        result = chr(65 + rem) + result
    return result


def sheet_cell_a1(row_number_1_based: int, col_number_1_based: int) -> str:
    return f"{col_to_a1(col_number_1_based)}{row_number_1_based}"


def sheet_cell_url(row_number_1_based: int, col_number_1_based: int) -> str:
    a1 = sheet_cell_a1(row_number_1_based, col_number_1_based)
    return (
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
        f"?gid={SHEET_GID}#gid={SHEET_GID}&range={SHEET_NAME}!{a1}"
    )


def month_end(period_start: date) -> date:
    return date(period_start.year, period_start.month, calendar.monthrange(period_start.year, period_start.month)[1])


def build_google_session(service_account_json: Path) -> AuthorizedSession:
    creds = Credentials.from_service_account_file(
        str(service_account_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return AuthorizedSession(creds)


def fetch_range(session: AuthorizedSession, render_option: str, max_row: int, max_col: int) -> list[list[str]]:
    end_col = col_to_a1(max_col)
    data_range = f"{SHEET_NAME}!A1:{end_col}{max_row}"
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{data_range}"
    response = session.get(
        url,
        params={
            "majorDimension": "ROWS",
            "valueRenderOption": render_option,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json().get("values", [])


def sheet_value(grid: list[list[str]], row_1_based: int, col_1_based: int) -> str:
    row_idx = row_1_based - 1
    col_idx = col_1_based - 1
    if row_idx < 0 or row_idx >= len(grid):
        return ""
    row = grid[row_idx]
    if col_idx < 0 or col_idx >= len(row):
        return ""
    value = row[col_idx]
    return "" if value is None else str(value)


def parse_month_columns(formatted_grid: list[list[str]], max_col: int) -> list[tuple[int, date, str]]:
    result: list[tuple[int, date, str]] = []
    for col in range(3, max_col + 1):
        raw_date = sheet_value(formatted_grid, 2, col).strip()
        raw_label = sheet_value(formatted_grid, 3, col).strip()
        if not raw_date:
            continue
        try:
            period_start = datetime.strptime(raw_date, "%d.%m.%Y").date()
        except ValueError:
            continue
        result.append((col, period_start, raw_label or raw_date))
    return result


def should_keep_period(period_start: date, month_start: date | None, month_end_value: date | None) -> bool:
    if month_start and period_start < month_start:
        return False
    if month_end_value and period_start > month_end_value:
        return False
    return True


def normalize_dimension(value: str, kind: str) -> Optional[str]:
    normalized = (value or "").strip()
    if not normalized or normalized.lower() == "general":
        return None
    if kind == "show":
        mapping = {
            "certificate": "Certificate",
            "sd": "SD",
            "online": "Online",
        }
        return mapping.get(normalized.lower(), normalized)
    return normalized


def parse_numeric(value: str) -> Optional[Decimal]:
    raw = (value or "").replace("\xa0", "").replace(" ", "").strip()
    if raw in {"", "-", "—"}:
        return None
    raw = raw.replace("₽", "")
    if raw.lower().startswith("р."):
        raw = raw[2:]
    elif raw.lower().startswith("р"):
        raw = raw[1:]
    raw = raw.strip()
    if raw.endswith("%"):
        raw = raw[:-1].replace(",", ".")
        try:
            return Decimal(raw) / Decimal("100")
        except InvalidOperation:
            return None
    raw = raw.replace(",", ".")
    if raw.startswith("(") and raw.endswith(")"):
        raw = f"-{raw[1:-1]}"
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def decimal_to_raw(value: Decimal) -> str:
    return format(value.normalize(), "f")


def load_mapping(path: Path) -> list[MappingRow]:
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            rows.append(
                MappingRow(
                    row_number=int(row["row_number"]),
                    source_business_unit=(row.get("source_business_unit") or "").strip(),
                    source_label=(row.get("source_label") or "").strip(),
                    formula_or_input=(row.get("formula_or_input") or "").strip(),
                    filled_cell_count=int(row.get("filled_cell_count") or 0),
                    layer=(row.get("layer") or "").strip().lower(),
                    canonical_metric=(row.get("canonical_metric") or "").strip(),
                    business_unit=(row.get("business_unit") or "").strip(),
                    show=(row.get("show") or "").strip(),
                    channel=(row.get("channel") or "").strip(),
                    agent=(row.get("agent") or "").strip(),
                    merge_rule=(row.get("merge_rule") or "").strip().lower(),
                    mapping_status=(row.get("mapping_status") or "").strip().lower(),
                    mapping_note=(row.get("mapping_note") or "").strip(),
                )
            )
        return rows


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "status",
                "period_start",
                "source_row_number",
                "source_business_unit",
                "source_label",
                "canonical_metric",
                "business_unit",
                "show",
                "channel",
                "agent",
                "cell_a1",
                "value_raw",
                "value_numeric",
                "reason",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--mapping-path", default=str(DEFAULT_MAPPING_PATH))
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--service-account-json", default=str(DEFAULT_GOOGLE_SERVICE_ACCOUNT_JSON))
    parser.add_argument("--source-system", default=SOURCE_SYSTEM)
    parser.add_argument("--source-run-id", default=SOURCE_RUN_ID)
    parser.add_argument("--month-start", help="Optional YYYY-MM-DD lower month bound")
    parser.add_argument("--month-end", help="Optional YYYY-MM-DD upper month bound")
    parser.add_argument("--delete-existing", action="store_true")
    args = parser.parse_args()

    mapping_path = Path(args.mapping_path)
    service_account_json = Path(args.service_account_json)
    report_path = Path(args.report_path)
    source_system = args.source_system
    source_run_id = args.source_run_id
    month_start = date.fromisoformat(args.month_start) if args.month_start else None
    month_end_value = date.fromisoformat(args.month_end) if args.month_end else None

    rows = load_mapping(mapping_path)
    fact_rows = [
        row
        for row in rows
        if row.layer == "fact"
        and row.canonical_metric
        and row.mapping_status.startswith("mapped")
        and row.merge_rule == MERGE_RULE_SUM
    ]
    max_row = max(row.row_number for row in rows)
    max_col = 65

    session = build_google_session(service_account_json)
    formatted_grid = fetch_range(session, "FORMATTED_VALUE", max_row, max_col)
    formula_grid = fetch_range(session, "FORMULA", max_row, max_col)
    month_columns = parse_month_columns(formatted_grid, max_col)

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT metric_id, metric_name, value_kind FROM metric_catalogue")
                metric_meta = {
                    metric_name: {"metric_id": metric_id, "value_kind": value_kind}
                    for metric_id, metric_name, value_kind in cur.fetchall()
                }

                missing_metrics = sorted({row.canonical_metric for row in fact_rows if row.canonical_metric not in metric_meta})
                if missing_metrics:
                    raise RuntimeError(f"Missing metrics in metric_catalogue: {missing_metrics}")

                if args.delete_existing:
                    delete_sql = DELETE_SQL
                    delete_params = {
                        "source_system": source_system,
                        "source_run_id": source_run_id,
                    }
                    if month_start:
                        delete_sql += "\n  AND period_start >= %(month_start)s"
                        delete_params["month_start"] = month_start
                    if month_end_value:
                        delete_sql += "\n  AND period_start <= %(month_end)s"
                        delete_params["month_end"] = month_end_value
                    cur.execute(delete_sql, delete_params)

                aggregates: dict[tuple, dict] = {}
                report_rows: list[dict[str, str]] = []

                for row in fact_rows:
                    metric_info = metric_meta[row.canonical_metric]
                    for col_1_based, period_start, month_label in month_columns:
                        if not should_keep_period(period_start, month_start, month_end_value):
                            continue
                        formatted_value = sheet_value(formatted_grid, row.row_number, col_1_based)
                        formula_value = sheet_value(formula_grid, row.row_number, col_1_based)
                        numeric_value = parse_numeric(formatted_value)
                        cell_mode = "formula" if formula_value.startswith("=") else "input"
                        cell_a1 = sheet_cell_a1(row.row_number, col_1_based)

                        if cell_a1 in CELL_NUMERIC_OVERRIDES:
                            numeric_value = CELL_NUMERIC_OVERRIDES[cell_a1]

                        if numeric_value is None:
                            report_rows.append(
                                {
                                    "status": "skipped",
                                    "period_start": period_start.isoformat(),
                                    "source_row_number": str(row.row_number),
                                    "source_business_unit": row.source_business_unit,
                                    "source_label": row.source_label,
                                    "canonical_metric": row.canonical_metric,
                                    "business_unit": row.business_unit,
                                    "show": row.show,
                                    "channel": row.channel,
                                    "agent": row.agent,
                                    "cell_a1": cell_a1,
                                    "value_raw": formatted_value,
                                    "value_numeric": "",
                                    "reason": "blank_or_non_numeric",
                                }
                            )
                            continue

                        show_name = normalize_dimension(row.show, "show")
                        channel_name = normalize_dimension(row.channel, "channel")
                        partner_name = normalize_dimension(row.agent, "agent")
                        business_unit = (row.business_unit or "").strip() or None
                        period_end = month_end(period_start)

                        aggregate_key = (
                            row.canonical_metric,
                            business_unit,
                            show_name,
                            channel_name,
                            partner_name,
                            period_start,
                            period_end,
                        )
                        aggregate = aggregates.setdefault(
                            aggregate_key,
                            {
                                "metric_id": metric_info["metric_id"],
                                "metric_name": row.canonical_metric,
                                "value_kind": metric_info["value_kind"],
                                "business_unit": business_unit,
                                "show_name": show_name,
                                "channel_name": channel_name,
                                "partner_name": partner_name,
                                "period_start": period_start,
                                "period_end": period_end,
                                "total": Decimal("0"),
                                "source_rows": [],
                                "source_modes": set(),
                                "source_cells": [],
                                "source_cell_urls": [],
                                "source_labels": [],
                                "source_business_units": [],
                                "month_labels": set(),
                                "source_value_details": [],
                            },
                        )
                        aggregate["total"] += numeric_value
                        aggregate["source_rows"].append(row.row_number)
                        aggregate["source_modes"].add(cell_mode)
                        aggregate["source_cells"].append(cell_a1)
                        aggregate["source_cell_urls"].append(sheet_cell_url(row.row_number, col_1_based))
                        aggregate["source_labels"].append(row.source_label)
                        aggregate["source_business_units"].append(row.source_business_unit)
                        aggregate["month_labels"].add(month_label)
                        aggregate["source_value_details"].append(
                            {
                                "row_number": row.row_number,
                                "cell_a1": cell_a1,
                                "cell_url": sheet_cell_url(row.row_number, col_1_based),
                                "raw_value": formatted_value,
                                "numeric_value": decimal_to_raw(numeric_value),
                                "numeric_override_applied": cell_a1 in CELL_NUMERIC_OVERRIDES,
                                "formula_or_input": cell_mode,
                                "source_label": row.source_label,
                                "source_business_unit": row.source_business_unit,
                                "month_label": month_label,
                                "period_start": period_start.isoformat(),
                            }
                        )

                        report_rows.append(
                            {
                                "status": "aggregated",
                                "period_start": period_start.isoformat(),
                                "source_row_number": str(row.row_number),
                                "source_business_unit": row.source_business_unit,
                                "source_label": row.source_label,
                                "canonical_metric": row.canonical_metric,
                                "business_unit": row.business_unit,
                                "show": row.show,
                                "channel": row.channel,
                                "agent": row.agent,
                                "cell_a1": cell_a1,
                                "value_raw": formatted_value,
                                "value_numeric": decimal_to_raw(numeric_value),
                                "reason": "",
                            }
                        )

                inserts = []
                def aggregate_sort_key(item):
                    metric_name, business_unit, show_name, channel_name, partner_name, period_start, period_end = item[0]
                    return (
                        metric_name or "",
                        business_unit or "",
                        show_name or "",
                        channel_name or "",
                        partner_name or "",
                        period_start.isoformat(),
                        period_end.isoformat(),
                    )

                for (
                    metric_name,
                    business_unit,
                    show_name,
                    channel_name,
                    partner_name,
                    period_start,
                    period_end,
                ), aggregate in sorted(aggregates.items(), key=aggregate_sort_key):
                    source_record_key = (
                        f"historical_monthly_economics:"
                        f"{metric_name}:"
                        f"{business_unit or 'none'}:"
                        f"{show_name or 'none'}:"
                        f"{channel_name or 'none'}:"
                        f"{partner_name or 'none'}:"
                        f"{period_start.isoformat()}"
                    )
                    total = aggregate["total"]
                    value_raw = decimal_to_raw(total)
                    currency_code = "RUB" if aggregate["value_kind"] == "currency" else None
                    payload = {
                        "sheet_role": "historical_monthly_economics",
                        "sheet_id": SPREADSHEET_ID,
                        "sheet_gid": SHEET_GID,
                        "sheet_name": SHEET_NAME,
                        "sheet_url": f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit?gid={SHEET_GID}#gid={SHEET_GID}",
                        "source_rows": sorted(set(aggregate["source_rows"])),
                        "source_labels": sorted(set(aggregate["source_labels"])),
                        "source_business_units": sorted(set(aggregate["source_business_units"])),
                        "source_cells": sorted(set(aggregate["source_cells"])),
                        "source_cell_urls": sorted(set(aggregate["source_cell_urls"])),
                        "source_modes": sorted(aggregate["source_modes"]),
                        "source_month_labels": sorted(aggregate["month_labels"]),
                        "source_value_details": aggregate["source_value_details"],
                        "merge_rule": MERGE_RULE_SUM,
                        "mapping_file": str(mapping_path),
                    }
                    inserts.append(
                        {
                            "metric_id": aggregate["metric_id"],
                            "source_system": source_system,
                            "source_record_key": source_record_key,
                            "source_run_id": source_run_id,
                            "business_unit": business_unit,
                            "show_name": show_name,
                            "partner_name": partner_name,
                            "channel_name": channel_name,
                            "period_start": period_start,
                            "period_end": period_end,
                            "value_numeric": total,
                            "value_raw": value_raw,
                            "currency_code": currency_code,
                            "payload": Json(payload),
                        }
                    )

                execute_batch(cur, INSERT_SQL, inserts, page_size=200)

                for insert in inserts:
                    report_rows.append(
                        {
                            "status": "inserted",
                            "period_start": insert["period_start"].isoformat(),
                            "source_row_number": "",
                            "source_business_unit": insert["business_unit"] or "",
                            "source_label": "",
                            "canonical_metric": next(
                                metric_name
                                for metric_name, meta in metric_meta.items()
                                if meta["metric_id"] == insert["metric_id"]
                            ),
                            "business_unit": insert["business_unit"] or "",
                            "show": insert["show_name"] or "",
                            "channel": insert["channel_name"] or "",
                            "agent": insert["partner_name"] or "",
                            "cell_a1": "",
                            "value_raw": insert["value_raw"],
                            "value_numeric": insert["value_raw"],
                            "reason": "",
                        }
                    )

                write_report(report_path, report_rows)
                print(
                    json.dumps(
                        {
                            "inserted_rows": len(inserts),
                            "aggregated_source_rows": len([row for row in report_rows if row["status"] == "aggregated"]),
                            "report_path": str(report_path),
                            "source_run_id": source_run_id,
                        },
                        ensure_ascii=False,
                    )
                )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
