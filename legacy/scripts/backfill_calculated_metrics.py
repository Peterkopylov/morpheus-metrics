#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
DEFAULT_REPORT_PATH = ROOT / "generated" / "calculated_metrics_backfill_report.csv"
RUNNER_PATH = ROOT / "scripts" / "run_calculated_metrics.py"


@dataclass
class BackfillPeriodResult:
    period_start: date
    status: str
    run_id: str
    report_path: str
    notes: str
    exit_code: int


def assert_period_start(value: date, granularity: str, label: str) -> None:
    if granularity == "week" and value.weekday() != 0:
        raise SystemExit(f"{label} must be a Monday, got {value.isoformat()}")
    if granularity == "month" and value.day != 1:
        raise SystemExit(f"{label} must be the first day of a month, got {value.isoformat()}")


def period_starts_between(granularity: str, start_period: date, end_period: date) -> list[date]:
    periods: list[date] = []
    current = start_period
    while current <= end_period:
        periods.append(current)
        if granularity == "week":
            current += timedelta(days=7)
        else:
            current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return periods


def build_run_command(
    database_url: str,
    period_granularity: str,
    period_start: date,
    include_pending: bool,
) -> list[str]:
    cmd = [
        sys.executable,
        str(RUNNER_PATH),
        "--database-url",
        database_url,
        "--period-granularity",
        period_granularity,
        "--period-start",
        period_start.isoformat(),
    ]
    if include_pending:
        cmd.append("--include-pending")
    return cmd


def run_period(
    database_url: str,
    period_granularity: str,
    period_start: date,
    include_pending: bool,
) -> BackfillPeriodResult:
    cmd = build_run_command(database_url, period_granularity, period_start, include_pending)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    if proc.returncode != 0:
        return BackfillPeriodResult(
            period_start=period_start,
            status="failed",
            run_id="",
            report_path="",
            notes=stderr or stdout or "calculated runner failed",
            exit_code=proc.returncode,
        )

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return BackfillPeriodResult(
            period_start=period_start,
            status="failed",
            run_id="",
            report_path="",
            notes=f"runner returned non-JSON stdout: {stdout[:500]}",
            exit_code=proc.returncode,
        )

    return BackfillPeriodResult(
        period_start=period_start,
        status=payload.get("overall_status", "unknown"),
        run_id=payload.get("run_id", ""),
        report_path=payload.get("report_path", ""),
        notes="",
        exit_code=proc.returncode,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill calculated metrics one period at a time.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--period-granularity", required=True, choices=["week", "month"])
    parser.add_argument("--start-period", required=True)
    parser.add_argument("--end-period", required=True)
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--include-pending", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    start_period = date.fromisoformat(args.start_period)
    end_period = date.fromisoformat(args.end_period)
    assert_period_start(start_period, args.period_granularity, "start-period")
    assert_period_start(end_period, args.period_granularity, "end-period")
    if start_period > end_period:
        raise SystemExit("start-period must be <= end-period")

    results: list[BackfillPeriodResult] = []
    for period_start in period_starts_between(args.period_granularity, start_period, end_period):
        result = run_period(args.database_url, args.period_granularity, period_start, args.include_pending)
        results.append(result)
        if result.status == "failed" and not args.continue_on_error:
            break

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["period_start", "status", "run_id", "report_path", "notes", "exit_code"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "period_start": result.period_start.isoformat(),
                    "status": result.status,
                    "run_id": result.run_id,
                    "report_path": result.report_path,
                    "notes": result.notes,
                    "exit_code": result.exit_code,
                }
            )

    summary = {
        "periods_total": len(results),
        "periods_success": sum(result.status == "success" for result in results),
        "periods_partial": sum(result.status == "partial" for result in results),
        "periods_failed": sum(result.status == "failed" for result in results),
        "report_path": str(report_path),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["periods_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
