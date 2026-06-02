#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg2


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
DEFAULT_OUTPUT_PATH = ROOT / "generated/monthly_pnl_profit_consistency_report.csv"
SOURCE_VIEW = "monthly_pnl_active_history_with_total"
METRICS = ("Revenue", "Variable costs", "Fixed costs", "Net profit")
ZERO = Decimal("0")


@dataclass(frozen=True)
class CheckKey:
    business_unit: str
    period_start: date


def attention_level(
    missing_metrics: list[str],
    abs_delta: Decimal,
    revenue: Decimal,
    variable_costs: Decimal,
    fixed_costs: Decimal,
    net_profit: Decimal,
) -> tuple[str, str]:
    coverage = sum(1 for value in (revenue, variable_costs, fixed_costs, net_profit) if value != ZERO)
    base = max(abs(revenue), abs(variable_costs), abs(fixed_costs), abs(net_profit), Decimal("1"))
    rel_delta = abs_delta / base

    if missing_metrics and coverage >= 2:
        return "high", "missing_required_metric"
    if abs_delta == ZERO:
        return "ok", "exact_match"
    if rel_delta <= Decimal("0.01"):
        return "low", "small_delta"
    if rel_delta <= Decimal("0.05"):
        return "medium", "moderate_delta"
    return "high", "large_delta"


def load_rows(conn) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                metric_name,
                COALESCE(business_unit, '') AS business_unit,
                period_start,
                value_numeric,
                source_system
            FROM {SOURCE_VIEW}
            WHERE metric_name IN %s
              AND COALESCE(show_name, '') = ''
              AND COALESCE(channel_name, '') = ''
              AND COALESCE(partner_name, '') = ''
            ORDER BY business_unit, period_start, metric_name
            """,
            (METRICS,),
        )
        return cur.fetchall()


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "business_unit",
        "period_start",
        "review_attention",
        "coverage_status",
        "present_metrics_count",
        "check_status",
        "missing_metrics",
        "source_systems",
        "Revenue",
        "Variable costs",
        "Fixed costs",
        "Net profit",
        "calculated_net_profit",
        "delta",
        "abs_delta",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    conn = psycopg2.connect(args.database_url)
    try:
        raw_rows = load_rows(conn)
    finally:
        conn.close()

    metric_values: dict[CheckKey, dict[str, Decimal]] = defaultdict(dict)
    source_systems: dict[CheckKey, dict[str, str]] = defaultdict(dict)
    for metric_name, business_unit, period_start, value_numeric, source_system in raw_rows:
        key = CheckKey(business_unit=business_unit, period_start=period_start)
        metric_values[key][metric_name] = value_numeric if value_numeric is not None else ZERO
        source_systems[key][metric_name] = source_system or ""

    output_rows: list[dict[str, str]] = []
    attention_counter: Counter[str] = Counter()
    for key in sorted(metric_values.keys(), key=lambda item: (item.business_unit, item.period_start)):
        values = metric_values[key]
        revenue = values.get("Revenue", ZERO)
        variable_costs = values.get("Variable costs", ZERO)
        fixed_costs = values.get("Fixed costs", ZERO)
        net_profit = values.get("Net profit", ZERO)
        calculated_net_profit = revenue - variable_costs - fixed_costs
        delta = net_profit - calculated_net_profit
        abs_delta = abs(delta)
        missing_metrics = [metric for metric in METRICS if metric not in values]
        review_attention, check_status = attention_level(
            missing_metrics=missing_metrics,
            abs_delta=abs_delta,
            revenue=revenue,
            variable_costs=variable_costs,
            fixed_costs=fixed_costs,
            net_profit=net_profit,
        )
        coverage_status = "complete" if not missing_metrics else "partial"
        attention_counter[review_attention] += 1
        output_rows.append(
            {
                "business_unit": key.business_unit,
                "period_start": key.period_start.isoformat(),
                "review_attention": review_attention,
                "coverage_status": coverage_status,
                "present_metrics_count": str(len(values)),
                "check_status": check_status,
                "missing_metrics": ", ".join(missing_metrics),
                "source_systems": "; ".join(
                    f"{metric}={source_systems[key].get(metric, '')}" for metric in METRICS if metric in values
                ),
                "Revenue": str(revenue),
                "Variable costs": str(variable_costs),
                "Fixed costs": str(fixed_costs),
                "Net profit": str(net_profit),
                "calculated_net_profit": str(calculated_net_profit),
                "delta": str(delta),
                "abs_delta": str(abs_delta),
            }
        )

    attention_order = {"high": 0, "medium": 1, "low": 2, "ok": 3}
    output_rows.sort(
        key=lambda row: (
            attention_order.get(row["review_attention"], 9),
            row["business_unit"],
            row["period_start"],
        )
    )
    write_csv(Path(args.output_path), output_rows)
    print(
        {
            "row_count": len(output_rows),
            "attention_breakdown": dict(attention_counter),
            "output_path": str(args.output_path),
            "source_view": SOURCE_VIEW,
        }
    )


if __name__ == "__main__":
    main()
