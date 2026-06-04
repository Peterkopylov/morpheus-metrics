#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
DEFAULT_STRUCTURE_PATH = ROOT / "generated/pnl_structure_mapping_canonical.csv"
DEFAULT_REPORT_PATH = ROOT / "generated/historical_leaf_rollup_backfill_import_report.csv"

SOURCE_SYSTEM = "historical_leaf_rollup_backfill"
SOURCE_RUN_ID = "historical_leaf_rollup_backfill:v1"
HISTORICAL_SOURCE_SYSTEM = "google_sheets_monthly_economics_historical"
TARGET_ROLLUPS = ("Variable costs", "Fixed costs")
EXCLUDED_FROM_VARIABLE = {
    "Investment costs",
    "Relocation costs",
    "Marketing costs",
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
    NULL,
    NULL,
    NULL,
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
class StructureRow:
    pnl_node_path: str
    parent_pnl_node_path: str
    canonical_metric: str
    node_role: str
    mapping_action: str


@dataclass(frozen=True)
class FactRow:
    metric_name: str
    business_unit: str
    period_start: date
    period_end: date
    show_name: str | None
    partner_name: str | None
    channel_name: str | None
    value_numeric: Decimal
    source_system: str


def month_end(period_start: date) -> date:
    return date(period_start.year, period_start.month, calendar.monthrange(period_start.year, period_start.month)[1])


def decimal_to_raw(value: Decimal) -> str:
    return format(value.normalize(), "f")


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
                "value_numeric",
                "reason",
                "source_metrics",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def load_structure(path: Path) -> list[StructureRow]:
    rows: list[StructureRow] = []
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            canonical_metric = (row.get("canonical_metric") or "").strip()
            pnl_node_path = (row.get("pnl_node_path") or "").strip()
            if not canonical_metric or not pnl_node_path:
                continue
            rows.append(
                StructureRow(
                    pnl_node_path=pnl_node_path,
                    parent_pnl_node_path=(row.get("parent_pnl_node_path") or "").strip(),
                    canonical_metric=canonical_metric,
                    node_role=(row.get("node_role") or "").strip(),
                    mapping_action=(row.get("mapping_action") or "").strip(),
                )
            )
    return rows


def build_metric_graph(rows: list[StructureRow]) -> dict[str, set[str]]:
    path_to_metric = {row.pnl_node_path: row.canonical_metric for row in rows}
    children_by_metric: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if not row.parent_pnl_node_path:
            continue
        parent_metric = path_to_metric.get(row.parent_pnl_node_path)
        child_metric = row.canonical_metric
        if not parent_metric or not child_metric or parent_metric == child_metric:
            continue
        children_by_metric[parent_metric].add(child_metric)
    return children_by_metric


def choose_observed_value(rows: list[FactRow]) -> tuple[Decimal | None, list[FactRow]]:
    if not rows:
        return None, []
    total_channel_rows = [
        row
        for row in rows
        if (row.channel_name or "") == "total" and not row.show_name and not row.partner_name
    ]
    if total_channel_rows:
        return sum((row.value_numeric for row in total_channel_rows), Decimal("0")), total_channel_rows
    unscoped_rows = [
        row
        for row in rows
        if not row.show_name and not row.partner_name and not row.channel_name
    ]
    if unscoped_rows:
        return sum((row.value_numeric for row in unscoped_rows), Decimal("0")), unscoped_rows
    return sum((row.value_numeric for row in rows), Decimal("0")), rows


def descendants_for_targets(children_by_metric: dict[str, set[str]]) -> dict[str, set[str]]:
    def collect(metric: str, seen: set[str]) -> set[str]:
        result: set[str] = set()
        for child in children_by_metric.get(metric, set()):
            if child in seen:
                continue
            seen.add(child)
            result.add(child)
            result.update(collect(child, seen))
        return result

    descendants = {target: collect(target, {target}) for target in TARGET_ROLLUPS}
    descendants["Variable costs"] = {
        metric for metric in descendants["Variable costs"] if metric not in EXCLUDED_FROM_VARIABLE
    }
    return descendants


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

    structure_rows = load_structure(Path(args.structure_path))
    children_by_metric = build_metric_graph(structure_rows)
    descendants = descendants_for_targets(children_by_metric)
    source_run_id = args.source_run_id
    month_start_value = date.fromisoformat(args.month_start) if args.month_start else None
    month_end_value = date.fromisoformat(args.month_end) if args.month_end else None

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT metric_id, metric_name, value_kind FROM metric_catalogue")
                metric_meta = {
                    metric_name: {"metric_id": metric_id, "value_kind": value_kind}
                    for metric_id, metric_name, value_kind in cur.fetchall()
                }

                missing_catalogue = [metric for metric in TARGET_ROLLUPS if metric not in metric_meta]
                if missing_catalogue:
                    raise RuntimeError(f"Missing target rollup metrics in metric_catalogue: {missing_catalogue}")

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

                cur.execute(
                    """
                    SELECT
                        mc.metric_name,
                        COALESCE(o.business_unit, ''),
                        o.period_start::date,
                        o.period_end::date,
                        NULLIF(o.show_name, ''),
                        NULLIF(o.partner_name, ''),
                        NULLIF(o.channel_name, ''),
                        o.value_numeric,
                        o.source_system
                    FROM fact_metric_observation o
                    JOIN metric_catalogue mc
                      ON mc.metric_id = o.metric_id
                    WHERE o.period_granularity = 'month'
                      AND o.source_system = %s
                    """,
                    (HISTORICAL_SOURCE_SYSTEM,),
                )
                raw_rows = [
                    FactRow(
                        metric_name=metric_name,
                        business_unit=business_unit,
                        period_start=period_start,
                        period_end=period_end,
                        show_name=show_name,
                        partner_name=partner_name,
                        channel_name=channel_name,
                        value_numeric=value_numeric,
                        source_system=source_system,
                    )
                    for (
                        metric_name,
                        business_unit,
                        period_start,
                        period_end,
                        show_name,
                        partner_name,
                        channel_name,
                        value_numeric,
                        source_system,
                    ) in cur.fetchall()
                ]

                rows_by_metric_bu_month: dict[tuple[str, str, date], list[FactRow]] = defaultdict(list)
                existing_rollups: set[tuple[str, str, date]] = set()
                business_units: set[str] = set()
                periods: set[date] = set()
                for row in raw_rows:
                    if not row.business_unit or row.business_unit == "total":
                        continue
                    business_units.add(row.business_unit)
                    periods.add(row.period_start)
                    rows_by_metric_bu_month[(row.metric_name, row.business_unit, row.period_start)].append(row)
                    if row.metric_name in TARGET_ROLLUPS:
                        existing_rollups.add((row.metric_name, row.business_unit, row.period_start))

                report_rows: list[dict[str, str]] = []
                inserts: list[dict] = []

                def node_value(metric_name: str, business_unit: str, period_start: date, visiting: set[str]) -> tuple[Decimal | None, list[str], list[dict]]:
                    if metric_name in visiting:
                        return None, [], []
                    visiting = set(visiting)
                    visiting.add(metric_name)

                    observed_rows = rows_by_metric_bu_month.get((metric_name, business_unit, period_start), [])
                    observed_value, used_rows = choose_observed_value(observed_rows)
                    if observed_value is not None:
                        return observed_value, [metric_name], [
                            {
                                "metric_name": metric_name,
                                "value_numeric": decimal_to_raw(observed_value),
                                "mode": "observed",
                                "channels": sorted({row.channel_name or "" for row in used_rows}),
                            }
                        ]

                    child_values = []
                    source_metrics: list[str] = []
                    source_details: list[dict] = []
                    for child in sorted(children_by_metric.get(metric_name, set())):
                        if metric_name == "Variable costs" and child in EXCLUDED_FROM_VARIABLE:
                            continue
                        child_value, child_metrics, child_details = node_value(child, business_unit, period_start, visiting)
                        if child_value is None:
                            continue
                        child_values.append(child_value)
                        source_metrics.extend(child_metrics)
                        source_details.extend(child_details)
                    if child_values:
                        return sum(child_values, Decimal("0")), sorted(set(source_metrics)), source_details
                    return None, [], []

                for target_metric in TARGET_ROLLUPS:
                    metric_info = metric_meta[target_metric]
                    for business_unit in sorted(business_units):
                        for period_start in sorted(periods):
                            if not should_keep_period(period_start, month_start_value, month_end_value):
                                continue
                            if (target_metric, business_unit, period_start) in existing_rollups:
                                report_rows.append(
                                    {
                                        "status": "skipped",
                                        "business_unit": business_unit,
                                        "period_start": period_start.isoformat(),
                                        "canonical_metric": target_metric,
                                        "value_numeric": "",
                                        "reason": "observed_rollup_exists",
                                        "source_metrics": "",
                                    }
                                )
                                continue

                            value_numeric, source_metrics, source_details = node_value(target_metric, business_unit, period_start, set())
                            if value_numeric is None:
                                report_rows.append(
                                    {
                                        "status": "skipped",
                                        "business_unit": business_unit,
                                        "period_start": period_start.isoformat(),
                                        "canonical_metric": target_metric,
                                        "value_numeric": "",
                                        "reason": "no_descendant_values",
                                        "source_metrics": "",
                                    }
                                )
                                continue

                            period_end = month_end(period_start)
                            source_record_key = (
                                f"{SOURCE_SYSTEM}:{target_metric}:{business_unit}:{period_start.isoformat()}"
                            )
                            payload = {
                                "backfill_role": "historical_leaf_rollup_backfill",
                                "rollup_metric": target_metric,
                                "business_unit": business_unit,
                                "period_start": period_start.isoformat(),
                                "source_system_base": HISTORICAL_SOURCE_SYSTEM,
                                "source_metrics": source_metrics,
                                "source_metric_details": source_details,
                                "rule_version": source_run_id,
                                "pnl_structure_mapping_path": str(args.structure_path),
                                "excludes_for_variable_costs": sorted(EXCLUDED_FROM_VARIABLE) if target_metric == "Variable costs" else [],
                            }
                            inserts.append(
                                {
                                    "metric_id": metric_info["metric_id"],
                                    "source_system": SOURCE_SYSTEM,
                                    "source_record_key": source_record_key,
                                    "source_run_id": source_run_id,
                                    "business_unit": business_unit,
                                    "period_start": period_start,
                                    "period_end": period_end,
                                    "value_numeric": value_numeric,
                                    "value_raw": decimal_to_raw(value_numeric),
                                    "currency_code": "RUB" if metric_info["value_kind"] == "currency" else None,
                                    "payload": Json(payload),
                                }
                            )
                            report_rows.append(
                                {
                                    "status": "inserted",
                                    "business_unit": business_unit,
                                    "period_start": period_start.isoformat(),
                                    "canonical_metric": target_metric,
                                    "value_numeric": decimal_to_raw(value_numeric),
                                    "reason": "backfilled_from_descendants",
                                    "source_metrics": "; ".join(source_metrics),
                                }
                            )

                execute_batch(cur, INSERT_SQL, inserts, page_size=200)
                write_report(Path(args.report_path), report_rows)
                print(
                    json.dumps(
                        {
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
