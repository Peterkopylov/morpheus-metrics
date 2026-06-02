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

import psycopg2


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
DEFAULT_REPORT_PATH = ROOT / "generated" / "weekly_fact_ingestion_backfill_report.csv"
RUNNER_PATH = ROOT / "scripts" / "run_weekly_fact_ingestion.py"


@dataclass
class BackfillWeekResult:
    week_start: date
    status: str
    run_id: str
    report_path: str
    action: str
    notes: str
    exit_code: int


def mondays_between(start_week: date, end_week: date) -> list[date]:
    weeks: list[date] = []
    current = start_week
    while current <= end_week:
        weeks.append(current)
        current += timedelta(days=7)
    return weeks


def assert_monday(value: date, label: str) -> None:
    if value.weekday() != 0:
        raise SystemExit(f"{label} must be a Monday, got {value.isoformat()}")


def already_successful(conn, week_start: date) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            select 1
            from fact_ingestion_runs
            where cadence='week'
              and period_start=%s
              and status='success'
            limit 1
            """,
            (week_start,),
        )
        return cur.fetchone() is not None


def build_run_command(
    database_url: str,
    week_start: date,
    delete_existing: bool,
    steps: str | None,
    skip_pending: bool,
) -> list[str]:
    cmd = [
        sys.executable,
        str(RUNNER_PATH),
        "--database-url",
        database_url,
        "--week-start",
        week_start.isoformat(),
    ]
    if delete_existing:
        cmd.append("--delete-existing")
    if steps:
        cmd.extend(["--steps", steps])
    if skip_pending:
        cmd.append("--skip-pending")
    return cmd


def run_week(
    database_url: str,
    week_start: date,
    delete_existing: bool,
    steps: str | None,
    skip_pending: bool,
) -> BackfillWeekResult:
    cmd = build_run_command(database_url, week_start, delete_existing, steps, skip_pending)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    if proc.returncode != 0:
        notes = stderr or stdout or "weekly runner failed"
        return BackfillWeekResult(
            week_start=week_start,
            status="failed",
            run_id="",
            report_path="",
            action="executed",
            notes=notes,
            exit_code=proc.returncode,
        )

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return BackfillWeekResult(
            week_start=week_start,
            status="failed",
            run_id="",
            report_path="",
            action="executed",
            notes=f"runner returned non-JSON stdout: {stdout[:500]}",
            exit_code=proc.returncode,
        )

    return BackfillWeekResult(
        week_start=week_start,
        status=payload.get("overall_status", "unknown"),
        run_id=payload.get("run_id", ""),
        report_path=payload.get("report_path", ""),
        action="executed",
        notes="",
        exit_code=proc.returncode,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill weekly fact ingestion one Monday at a time.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--start-week", required=True, help="Monday in YYYY-MM-DD")
    parser.add_argument("--end-week", required=True, help="Monday in YYYY-MM-DD")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--steps", help="Comma-separated subset of step keys to run")
    parser.add_argument("--skip-pending", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--force", action="store_true", help="Run even if this week already has a successful run")
    args = parser.parse_args()

    start_week = date.fromisoformat(args.start_week)
    end_week = date.fromisoformat(args.end_week)
    assert_monday(start_week, "start-week")
    assert_monday(end_week, "end-week")
    if start_week > end_week:
        raise SystemExit("start-week must be <= end-week")

    weeks = mondays_between(start_week, end_week)
    conn = psycopg2.connect(args.database_url)

    results: list[BackfillWeekResult] = []
    try:
        for week_start in weeks:
            if not args.force and already_successful(conn, week_start):
                results.append(
                    BackfillWeekResult(
                        week_start=week_start,
                        status="skipped",
                        run_id="",
                        report_path="",
                        action="already_successful",
                        notes="Successful weekly run already exists in fact_ingestion_runs",
                        exit_code=0,
                    )
                )
                continue

            result = run_week(
                database_url=args.database_url,
                week_start=week_start,
                delete_existing=args.delete_existing,
                steps=args.steps,
                skip_pending=args.skip_pending,
            )
            results.append(result)
            if result.status != "success" and not args.continue_on_error:
                break
    finally:
        conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "week_start",
                "status",
                "run_id",
                "report_path",
                "action",
                "notes",
                "exit_code",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "week_start": result.week_start.isoformat(),
                    "status": result.status,
                    "run_id": result.run_id,
                    "report_path": result.report_path,
                    "action": result.action,
                    "notes": result.notes,
                    "exit_code": result.exit_code,
                }
            )

    summary = {
        "weeks_total": len(results),
        "weeks_success": sum(result.status == "success" for result in results),
        "weeks_skipped": sum(result.status == "skipped" for result in results),
        "weeks_failed": sum(result.status == "failed" for result in results),
        "report_path": str(report_path),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["weeks_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
