#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_batch

ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
SERVING_DIR = ROOT / "scripts" / "serving"
if str(SERVING_DIR) not in sys.path:
    sys.path.append(str(SERVING_DIR))

from rebuild_monthly_pnl_history_views import build_view_sql

DEFAULT_STRUCTURE_PATH = ROOT / "catalog" / "pnl_structure_mapping_canonical.csv"
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "run_reports" / "monthly_pnl_calculated_rollups_to_fact_import_report.csv"

SOURCE_SYSTEM = "monthly_pnl_calculated_rollup"
SOURCE_RUN_ID = "monthly_pnl_calculated_rollup_v1"
SOURCE_VIEW = "monthly_pnl_leaf_only_rollup_history_with_total"
TARGET_NODE_ROLES = {"observed_rollup", "calculated_formula"}
EXCLUDED_TARGET_METRICS = {"Revenue"}


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
class RollupRow:
    metric_id: int
    metric_name: str
    value_kind: str
    business_unit: str
    show_name: str | None
    partner_name: str | None
    channel_name: str | None
    period_start: date
    period_end: date
    value_numeric: Decimal
    currency_code: str | None
    source_system: str
    payloads: list[dict]


def decimal_to_raw(value: Decimal) -> str:
    return format(value.normalize(), "f")


def month_end(period_start: date) -> date:
    return date(period_start.year, period_start.month, calendar.monthrange(period_start.year, period_start.month)[1])


def should_keep_period(period_start: date, month_start_value: date | None, month_end_value: date | None) -> bool:
    if month_start_value and period_start < month_start_value:
        return False
    if month_end_value and period_start > month_end_value:
        return False
    return True


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "status",
                "business_unit",
                "period_start",
                "canonical_metric",
                "show_name",
                "partner_name",
                "channel_name",
                "value_numeric",
                "reason",
                "rollup_source_system",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def load_target_metrics(path: Path) -> list[str]:
    target_metrics: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            metric_name = (row.get("canonical_metric") or "").strip()
            node_role = (row.get("node_role") or "").strip()
            mapping_action = (row.get("mapping_action") or "").strip()
            if not metric_name or metric_name in EXCLUDED_TARGET_METRICS:
                continue
            if node_role not in TARGET_NODE_ROLES:
                continue
            if mapping_action != "use_existing":
                continue
            target_metrics.add(metric_name)
    return sorted(target_metrics)


def load_rollup_rows(cur, target_metrics: list[str], month_start_value: date | None, month_end_value: date | None) -> list[RollupRow]:
    sql = f"""
        SELECT
            metric_id,
            metric_name,
            value_kind,
            COALESCE(business_unit, '') AS business_unit,
            NULLIF(show_name, ''),
            NULLIF(partner_name, ''),
            NULLIF(channel_name, ''),
            period_start,
            period_end,
            value_numeric,
            currency_code,
            source_system,
            payloads
        FROM {SOURCE_VIEW}
        WHERE metric_name = ANY(%s)
          AND source_system IN (
              'derived_leaf_only_rollup',
              'derived_total_from_leaf_only_rollup_business_units',
              'derived_leaf_only_formula'
          )
        ORDER BY metric_name, business_unit, period_start, show_name, partner_name, channel_name
    """
    cur.execute(sql, (target_metrics,))
    rows = [
        RollupRow(
            metric_id=metric_id,
            metric_name=metric_name,
            value_kind=value_kind,
            business_unit=business_unit,
            show_name=show_name,
            partner_name=partner_name,
            channel_name=channel_name,
            period_start=period_start,
            period_end=period_end,
            value_numeric=value_numeric,
            currency_code=currency_code,
            source_system=source_system,
            payloads=payloads or [],
        )
        for (
            metric_id,
            metric_name,
            value_kind,
            business_unit,
            show_name,
            partner_name,
            channel_name,
            period_start,
            period_end,
            value_numeric,
            currency_code,
            source_system,
            payloads,
        ) in cur.fetchall()
        if business_unit != "total" and should_keep_period(period_start, month_start_value, month_end_value)
    ]
    return rows


def build_channel_rollup_rows(rows: list[RollupRow]) -> list[RollupRow]:
    existing_unscoped = {
        (
            row.metric_id,
            row.business_unit,
            row.show_name or "",
            row.partner_name or "",
            row.period_start,
            row.period_end,
        )
        for row in rows
        if row.channel_name is None
    }

    grouped: dict[tuple, list[RollupRow]] = defaultdict(list)
    for row in rows:
        if row.channel_name is None:
            continue
        if row.show_name or row.partner_name:
            continue
        key = (
            row.metric_id,
            row.metric_name,
            row.value_kind,
            row.business_unit,
            row.period_start,
            row.period_end,
            row.currency_code,
            row.source_system,
        )
        grouped[key].append(row)

    synthesized: list[RollupRow] = []
    for key, members in grouped.items():
        metric_id, metric_name, value_kind, business_unit, period_start, period_end, currency_code, source_system = key
        aggregate_key = (metric_id, business_unit, "", "", period_start, period_end)
        if aggregate_key in existing_unscoped:
            continue
        value_numeric = sum((row.value_numeric for row in members), Decimal("0"))
        payloads = [
            {
                "aggregation_mode": "sum_channels_to_unscoped",
                "channel_name": row.channel_name,
                "value_numeric": decimal_to_raw(row.value_numeric),
            }
            for row in members
        ]
        synthesized.append(
            RollupRow(
                metric_id=metric_id,
                metric_name=metric_name,
                value_kind=value_kind,
                business_unit=business_unit,
                show_name=None,
                partner_name=None,
                channel_name=None,
                period_start=period_start,
                period_end=period_end,
                value_numeric=value_numeric,
                currency_code=currency_code,
                source_system=source_system,
                payloads=payloads,
            )
        )
    return synthesized


def build_source_record_key(row: RollupRow) -> str:
    show_key = row.show_name or "-"
    partner_key = row.partner_name or "-"
    channel_key = row.channel_name or "-"
    return (
        f"{SOURCE_SYSTEM}:{row.metric_name}:{row.business_unit}:{show_key}:"
        f"{partner_key}:{channel_key}:{row.period_start.isoformat()}"
    )


def build_payload(row: RollupRow, source_run_id: str, structure_path: Path, materialization_kind: str) -> dict:
    return {
        "value_origin": "calculated_rollup",
        "calculation_kind": materialization_kind,
        "rollup_metric": row.metric_name,
        "source_rollup_view": SOURCE_VIEW,
        "rollup_source_system": row.source_system,
        "business_unit": row.business_unit,
        "show_name": row.show_name,
        "partner_name": row.partner_name,
        "channel_name": row.channel_name,
        "period_start": row.period_start.isoformat(),
        "rule_version": source_run_id,
        "pnl_structure_mapping_path": str(structure_path),
        "source_payloads": row.payloads,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--structure-path", default=str(DEFAULT_STRUCTURE_PATH))
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--source-run-id", default=SOURCE_RUN_ID)
    parser.add_argument("--month-start", help="Optional YYYY-MM-DD lower month bound")
    parser.add_argument("--month-end", help="Optional YYYY-MM-DD upper month bound")
    parser.add_argument("--delete-existing", action="store_true")
    args = parser.parse_args()

    structure_path = Path(args.structure_path)
    target_metrics = load_target_metrics(structure_path)
    source_run_id = args.source_run_id
    month_start_value = date.fromisoformat(args.month_start) if args.month_start else None
    month_end_value = date.fromisoformat(args.month_end) if args.month_end else None

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                if args.delete_existing:
                    delete_sql = DELETE_SQL
                    delete_params = {
                        "source_system": SOURCE_SYSTEM,
                        "source_run_id": source_run_id,
                    }
                    if month_start_value:
                        delete_sql += "\n  AND period_start >= %(month_start)s"
                        delete_params["month_start"] = month_start_value
                    if month_end_value:
                        delete_sql += "\n  AND period_start <= %(month_end)s"
                        delete_params["month_end"] = month_end_value
                    cur.execute(delete_sql, delete_params)

                # Keep the derived monthly P&L views fresh before we materialize them into fact.
                cur.execute(build_view_sql())

                rollup_rows = load_rollup_rows(cur, target_metrics, month_start_value, month_end_value)
                rollup_rows.extend(build_channel_rollup_rows(rollup_rows))

                inserts: list[dict] = []
                report_rows: list[dict[str, str]] = []
                for row in rollup_rows:
                    materialization_kind = "channel_rollup" if row.channel_name is None and any(
                        payload.get("aggregation_mode") == "sum_channels_to_unscoped" for payload in row.payloads
                    ) else "direct_from_rollup_view"
                    payload = build_payload(row, source_run_id, structure_path, materialization_kind)
                    inserts.append(
                        {
                            "metric_id": row.metric_id,
                            "source_system": SOURCE_SYSTEM,
                            "source_record_key": build_source_record_key(row),
                            "source_run_id": source_run_id,
                            "business_unit": row.business_unit,
                            "show_name": row.show_name,
                            "partner_name": row.partner_name,
                            "channel_name": row.channel_name,
                            "period_start": row.period_start,
                            "period_end": row.period_end or month_end(row.period_start),
                            "value_numeric": row.value_numeric,
                            "value_raw": decimal_to_raw(row.value_numeric),
                            "currency_code": row.currency_code if row.value_kind == "currency" else None,
                            "payload": Json(payload),
                        }
                    )
                    report_rows.append(
                        {
                            "status": "inserted",
                            "business_unit": row.business_unit,
                            "period_start": row.period_start.isoformat(),
                            "canonical_metric": row.metric_name,
                            "show_name": row.show_name or "",
                            "partner_name": row.partner_name or "",
                            "channel_name": row.channel_name or "",
                            "value_numeric": decimal_to_raw(row.value_numeric),
                            "reason": materialization_kind,
                            "rollup_source_system": row.source_system,
                        }
                    )

                execute_batch(cur, INSERT_SQL, inserts, page_size=200)
                write_report(Path(args.report_path), report_rows)
                print(
                    json.dumps(
                        {
                            "target_metrics": target_metrics,
                            "inserted_rows": len(inserts),
                            "report_path": str(args.report_path),
                            "source_run_id": source_run_id,
                        },
                        ensure_ascii=False,
                    )
                )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
