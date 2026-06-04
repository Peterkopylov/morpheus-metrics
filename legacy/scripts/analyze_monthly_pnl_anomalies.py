#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import psycopg2


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
DEFAULT_REPORT_PATH = ROOT / "generated/monthly_pnl_anomaly_report.csv"
DEFAULT_SOURCE_VIEW = "monthly_pnl_active_history"


@dataclass
class Point:
    metric_name: str
    metric_family: str
    value_kind: str
    business_unit: str
    show_name: str
    channel_name: str
    partner_name: str
    period_start: date
    value: float
    source_system: str


def load_points(conn, source_view: str) -> list[Point]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                metric_name,
                metric_family,
                value_kind,
                COALESCE(business_unit, '') AS business_unit,
                COALESCE(show_name, '') AS show_name,
                COALESCE(channel_name, '') AS channel_name,
                COALESCE(partner_name, '') AS partner_name,
                period_start,
                value_numeric::double precision,
                source_system
            FROM {source_view}
            ORDER BY metric_name, business_unit, show_name, channel_name, partner_name, period_start
            """
        )
        return [Point(*row) for row in cur.fetchall()]


def series_key(point: Point) -> tuple[str, str, str, str, str]:
    return (
        point.metric_name,
        point.business_unit,
        point.show_name,
        point.channel_name,
        point.partner_name,
    )


def local_neighbors(points: list[Point], idx: int, radius: int = 3) -> list[float]:
    values: list[float] = []
    for offset in range(1, radius + 1):
        if idx - offset >= 0:
            values.append(points[idx - offset].value)
        if idx + offset < len(points):
            values.append(points[idx + offset].value)
    return values


def positive_neighbors(points: list[Point], idx: int, radius: int = 3) -> list[float]:
    return [v for v in local_neighbors(points, idx, radius) if v > 0]


def threshold_for_kind(value_kind: str) -> float:
    return {
        "currency": 10000.0,
        "count": 5.0,
        "ratio": 0.05,
        "percent": 0.05,
    }.get(value_kind, 1.0)


def describe_series(key: tuple[str, str, str, str, str]) -> str:
    metric_name, business_unit, show_name, channel_name, partner_name = key
    parts = [metric_name]
    if business_unit:
        parts.append(f"bu={business_unit}")
    if show_name:
        parts.append(f"show={show_name}")
    if channel_name:
        parts.append(f"channel={channel_name}")
    if partner_name:
        parts.append(f"partner={partner_name}")
    return " | ".join(parts)


def analyze_series(points: list[Point]) -> list[dict[str, str]]:
    anomalies: list[dict[str, str]] = []
    if len(points) < 4:
        return anomalies

    point_values = [p.value for p in points]
    series_nonzero = [v for v in point_values if v != 0]
    if not series_nonzero:
        return anomalies

    global_median = statistics.median(series_nonzero)
    min_abs = threshold_for_kind(points[0].value_kind)

    for idx, point in enumerate(points):
        neighbor_values = local_neighbors(points, idx)
        neighbor_nonzero = [v for v in neighbor_values if v != 0]
        if len(neighbor_nonzero) < 2:
            continue

        local_median = statistics.median(neighbor_nonzero)
        if local_median == 0:
            continue

        ratio = abs(point.value) / abs(local_median) if local_median else math.inf
        diff = point.value - local_median
        abs_diff = abs(diff)

        prev_value = points[idx - 1].value if idx > 0 else None
        next_value = points[idx + 1].value if idx + 1 < len(points) else None

        anomaly_type: Optional[str] = None
        reason = ""

        if point.value == 0 and len(neighbor_nonzero) >= 2 and local_median >= min_abs:
            anomaly_type = "zero_gap"
            reason = f"zero against local median {local_median:.2f}"
        elif point.value > 0 and ratio >= 3 and abs_diff >= min_abs:
            anomaly_type = "spike_up"
            reason = f"value {point.value:.2f} is {ratio:.1f}x local median {local_median:.2f}"
        elif point.value > 0 and point.value / local_median <= 0.33 and abs_diff >= min_abs:
            anomaly_type = "drop_down"
            reason = f"value {point.value:.2f} is only {point.value / local_median:.2f}x local median {local_median:.2f}"
        elif point.value < 0 and global_median > 0 and abs_diff >= min_abs:
            anomaly_type = "sign_flip"
            reason = f"negative value {point.value:.2f} against positive history median {global_median:.2f}"

        if not anomaly_type:
            continue

        severity = abs_diff * max(ratio, 1 / max(point.value / local_median, 1e-9)) if point.value and local_median else abs_diff
        anomalies.append(
            {
                "anomaly_type": anomaly_type,
                "severity_score": f"{severity:.2f}",
                "metric_name": point.metric_name,
                "metric_family": point.metric_family,
                "value_kind": point.value_kind,
                "business_unit": point.business_unit,
                "show_name": point.show_name,
                "channel_name": point.channel_name,
                "partner_name": point.partner_name,
                "period_start": point.period_start.isoformat(),
                "value_numeric": f"{point.value:.6f}",
                "local_median": f"{local_median:.6f}",
                "previous_value": "" if prev_value is None else f"{prev_value:.6f}",
                "next_value": "" if next_value is None else f"{next_value:.6f}",
                "source_system": point.source_system,
                "reason": reason,
                "series_label": describe_series(series_key(point)),
            }
        )

    return anomalies


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "anomaly_type",
        "severity_score",
        "metric_name",
        "metric_family",
        "value_kind",
        "business_unit",
        "show_name",
        "channel_name",
        "partner_name",
        "period_start",
        "value_numeric",
        "local_median",
        "previous_value",
        "next_value",
        "source_system",
        "reason",
        "series_label",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--source-view", default=DEFAULT_SOURCE_VIEW)
    args = parser.parse_args()

    conn = psycopg2.connect(args.database_url)
    try:
        points = load_points(conn, args.source_view)
    finally:
        conn.close()

    grouped: dict[tuple[str, str, str, str, str], list[Point]] = {}
    for point in points:
        grouped.setdefault(series_key(point), []).append(point)

    anomalies: list[dict[str, str]] = []
    for series_points in grouped.values():
        anomalies.extend(analyze_series(series_points))

    anomalies.sort(key=lambda row: float(row["severity_score"]), reverse=True)
    write_report(Path(args.report_path), anomalies)

    counts = Counter(row["anomaly_type"] for row in anomalies)
    print(
        {
            "series_count": len(grouped),
            "anomaly_count": len(anomalies),
            "anomaly_breakdown": dict(counts),
            "source_view": args.source_view,
            "report_path": str(args.report_path),
        }
    )


if __name__ == "__main__":
    main()
