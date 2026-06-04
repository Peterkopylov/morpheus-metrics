#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import date
from pathlib import Path


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
WEEKLY_FACT_RUNNER = ROOT / "scripts" / "run_weekly_fact_ingestion.py"
MONTHLY_KPI_FACT_RUNNER = ROOT / "scripts" / "run_monthly_kpi_fact_ingestion.py"
MONTHLY_FACT_RUNNER = ROOT / "scripts" / "run_monthly_pnl_fact_ingestion.py"
MONTHLY_HISTORY_REBUILD_RUNNER = ROOT / "scripts" / "serving" / "rebuild_monthly_pnl_history_views.py"
CALCULATION_RUNNER = ROOT / "scripts" / "run_calculated_metrics.py"


def build_weekly_fact_command(database_url: str, period_start: date, delete_existing: bool, steps: str | None) -> list[str]:
    cmd = [
        sys.executable,
        str(WEEKLY_FACT_RUNNER),
        "--database-url",
        database_url,
        "--week-start",
        period_start.isoformat(),
    ]
    if delete_existing:
        cmd.append("--delete-existing")
    if steps:
        cmd.extend(["--steps", steps])
    return cmd


def build_calculation_command(database_url: str, period_granularity: str, period_start: date) -> list[str]:
    return [
        sys.executable,
        str(CALCULATION_RUNNER),
        "--database-url",
        database_url,
        "--period-granularity",
        period_granularity,
        "--period-start",
        period_start.isoformat(),
        "--trigger-mode",
        "fact_refresh_wrapper",
    ]


def build_monthly_fact_command(database_url: str, period_start: date, delete_existing: bool, steps: str | None) -> list[str]:
    cmd = [
        sys.executable,
        str(MONTHLY_FACT_RUNNER),
        "--database-url",
        database_url,
        "--month-start",
        period_start.isoformat(),
    ]
    if delete_existing:
        cmd.append("--delete-existing")
    if steps:
        cmd.extend(["--steps", steps])
    return cmd


def build_monthly_kpi_fact_command(database_url: str, period_start: date, delete_existing: bool, steps: str | None) -> list[str]:
    cmd = [
        sys.executable,
        str(MONTHLY_KPI_FACT_RUNNER),
        "--database-url",
        database_url,
        "--month-start",
        period_start.isoformat(),
    ]
    if delete_existing:
        cmd.append("--delete-existing")
    if steps:
        cmd.extend(["--steps", steps])
    return cmd


def refresh_mode_to_period_granularity(refresh_mode: str) -> str:
    if refresh_mode == "weekly_kpi":
        return "week"
    return "month"


def default_fact_command(
    refresh_mode: str,
    database_url: str,
    period_start: date,
    delete_existing: bool,
    steps: str | None,
) -> list[str]:
    if refresh_mode == "weekly_kpi":
        return build_weekly_fact_command(database_url, period_start, delete_existing, steps)
    if refresh_mode == "monthly_kpi":
        return build_monthly_kpi_fact_command(database_url, period_start, delete_existing, steps)
    if refresh_mode == "monthly_pnl":
        return build_monthly_fact_command(database_url, period_start, delete_existing, steps)
    return []


def should_rebuild_monthly_pnl_views(refresh_mode: str) -> bool:
    return refresh_mode == "monthly_pnl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fact refresh and then recalculate the matching calculated metrics.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--refresh-mode", choices=["weekly_kpi", "monthly_kpi", "monthly_pnl"])
    parser.add_argument("--period-granularity", choices=["week", "month"])
    parser.add_argument("--period-start", required=True, help="YYYY-MM-DD start of week or month")
    parser.add_argument("--skip-fact", action="store_true", help="Skip fact refresh and run only calculated metrics")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--fact-steps", help="Comma-separated subset of fact steps for the selected granularity")
    parser.add_argument("--fact-command", help="Optional explicit fact refresh command")
    args = parser.parse_args()

    refresh_mode = args.refresh_mode
    if refresh_mode is None:
        if args.period_granularity == "week":
            refresh_mode = "weekly_kpi"
        elif args.period_granularity == "month":
            refresh_mode = "monthly_pnl"
        else:
            raise SystemExit("Either --refresh-mode or --period-granularity is required")

    period_granularity = args.period_granularity or refresh_mode_to_period_granularity(refresh_mode)
    period_start = date.fromisoformat(args.period_start)
    summary: dict[str, object] = {
        "refresh_mode": refresh_mode,
        "period_granularity": period_granularity,
        "period_start": period_start.isoformat(),
        "fact_command_executed": False,
        "fact_returncode": None,
        "calculation_returncode": None,
    }

    if not args.skip_fact:
        if args.fact_command:
            fact_cmd = shlex.split(args.fact_command)
        else:
            fact_cmd = default_fact_command(refresh_mode, args.database_url, period_start, args.delete_existing, args.fact_steps)

        if fact_cmd:
            fact_proc = subprocess.run(fact_cmd, capture_output=True, text=True)
            summary["fact_command_executed"] = True
            summary["fact_returncode"] = fact_proc.returncode
            summary["fact_stdout"] = fact_proc.stdout.strip()
            summary["fact_stderr"] = fact_proc.stderr.strip()
            if fact_proc.returncode != 0:
                print(json.dumps(summary, ensure_ascii=False))
                return fact_proc.returncode
            if should_rebuild_monthly_pnl_views(refresh_mode):
                rebuild_cmd = [
                    sys.executable,
                    str(MONTHLY_HISTORY_REBUILD_RUNNER),
                    "--database-url",
                    args.database_url,
                ]
                rebuild_proc = subprocess.run(rebuild_cmd, capture_output=True, text=True)
                summary["monthly_history_rebuild_returncode"] = rebuild_proc.returncode
                summary["monthly_history_rebuild_stdout"] = rebuild_proc.stdout.strip()
                summary["monthly_history_rebuild_stderr"] = rebuild_proc.stderr.strip()
                if rebuild_proc.returncode != 0:
                    print(json.dumps(summary, ensure_ascii=False))
                    return rebuild_proc.returncode
        else:
            summary["fact_stdout"] = "No default fact runner configured for this granularity; assuming fact layer is already updated."
            summary["fact_stderr"] = ""

    calc_cmd = build_calculation_command(args.database_url, period_granularity, period_start)
    calc_proc = subprocess.run(calc_cmd, capture_output=True, text=True)
    summary["calculation_returncode"] = calc_proc.returncode
    summary["calculation_stdout"] = calc_proc.stdout.strip()
    summary["calculation_stderr"] = calc_proc.stderr.strip()

    print(json.dumps(summary, ensure_ascii=False))
    return calc_proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
