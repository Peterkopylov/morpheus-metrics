#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import psycopg2


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
DEFAULT_OUTPUT_PATH = ROOT / "generated/monthly_pnl_attention_matrix.csv"
DEFAULT_ANOMALY_PATH = ROOT / "generated/monthly_pnl_anomaly_report.csv"
DEFAULT_SOURCE_VIEW = "monthly_pnl_active_history"


@dataclass(frozen=True)
class SeriesKey:
    metric_name: str
    business_unit: str
    show_name: str
    channel_name: str
    partner_name: str

    @property
    def label(self) -> str:
        parts = [self.metric_name]
        if self.business_unit:
            parts.append(f"bu={self.business_unit}")
        if self.show_name:
            parts.append(f"show={self.show_name}")
        if self.channel_name:
            parts.append(f"channel={self.channel_name}")
        if self.partner_name:
            parts.append(f"partner={self.partner_name}")
        return " | ".join(parts)


def load_active_history(conn, source_view: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                metric_name,
                COALESCE(business_unit, '') AS business_unit,
                COALESCE(show_name, '') AS show_name,
                COALESCE(channel_name, '') AS channel_name,
                COALESCE(partner_name, '') AS partner_name,
                period_start,
                value_numeric::double precision
            FROM {source_view}
            ORDER BY metric_name, business_unit, show_name, channel_name, partner_name, period_start
            """
        )
        return [
            {
                "metric_name": row[0],
                "business_unit": row[1],
                "show_name": row[2],
                "channel_name": row[3],
                "partner_name": row[4],
                "period_start": row[5],
                "value_numeric": row[6],
            }
            for row in cur.fetchall()
        ]


def attention_level(anomaly_count: int, severe_count: int, types: set[str]) -> str:
    if severe_count >= 2 or anomaly_count >= 6 or {"sign_flip", "zero_gap", "drop_down"} <= types:
        return "high"
    if severe_count >= 1 or anomaly_count >= 3 or "sign_flip" in types:
        return "medium"
    if anomaly_count >= 1:
        return "low"
    return "ok"


def load_anomalies(path: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    if not path.exists():
        return result
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["series_label"]].append(row)

    for label, series_rows in grouped.items():
        scores = [float(row["severity_score"]) for row in series_rows]
        types = {row["anomaly_type"] for row in series_rows}
        type_counts = Counter(row["anomaly_type"] for row in series_rows)
        severe_count = sum(1 for score in scores if score >= 1_000_000)
        result[label] = {
            "review_attention": attention_level(len(series_rows), severe_count, types),
            "anomaly_count": len(series_rows),
            "anomaly_types": ", ".join(f"{k}:{v}" for k, v in sorted(type_counts.items())),
            "max_severity_score": f"{max(scores):.2f}",
        }
    return result


def month_slug(period_start: date) -> str:
    return period_start.isoformat()[:7]


def write_matrix(path: Path, rows: list[dict], months: list[str]) -> None:
    fieldnames = [
        "series_label",
        "metric_name",
        "business_unit",
        "show_name",
        "channel_name",
        "partner_name",
        "review_attention",
        "anomaly_count",
        "anomaly_types",
        "max_severity_score",
    ] + months
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--anomaly-report-path", default=str(DEFAULT_ANOMALY_PATH))
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--source-view", default=DEFAULT_SOURCE_VIEW)
    args = parser.parse_args()

    conn = psycopg2.connect(args.database_url)
    try:
        points = load_active_history(conn, args.source_view)
    finally:
        conn.close()

    anomalies = load_anomalies(Path(args.anomaly_report_path))

    months = sorted({month_slug(point["period_start"]) for point in points})
    by_series: dict[SeriesKey, dict[str, float]] = defaultdict(dict)

    for point in points:
        key = SeriesKey(
            metric_name=point["metric_name"],
            business_unit=point["business_unit"],
            show_name=point["show_name"],
            channel_name=point["channel_name"],
            partner_name=point["partner_name"],
        )
        by_series[key][month_slug(point["period_start"])] = point["value_numeric"]

    output_rows: list[dict] = []
    attention_order = {"high": 0, "medium": 1, "low": 2, "ok": 3}
    for key, month_map in by_series.items():
        anomaly_meta = anomalies.get(
            key.label,
            {
                "review_attention": "ok",
                "anomaly_count": 0,
                "anomaly_types": "",
                "max_severity_score": "",
            },
        )
        row = {
            "series_label": key.label,
            "metric_name": key.metric_name,
            "business_unit": key.business_unit,
            "show_name": key.show_name,
            "channel_name": key.channel_name,
            "partner_name": key.partner_name,
            "review_attention": anomaly_meta["review_attention"],
            "anomaly_count": anomaly_meta["anomaly_count"],
            "anomaly_types": anomaly_meta["anomaly_types"],
            "max_severity_score": anomaly_meta["max_severity_score"],
        }
        for month in months:
            value = month_map.get(month)
            row[month] = "" if value is None else f"{value:.6f}"
        output_rows.append(row)

    output_rows.sort(
        key=lambda row: (
            attention_order.get(row["review_attention"], 9),
            row["metric_name"],
            row["business_unit"],
            row["show_name"],
            row["channel_name"],
            row["partner_name"],
        )
    )
    write_matrix(Path(args.output_path), output_rows, months)
    print(
        {
            "series_count": len(output_rows),
            "month_count": len(months),
            "source_view": args.source_view,
            "output_path": str(args.output_path),
        }
    )


if __name__ == "__main__":
    main()
