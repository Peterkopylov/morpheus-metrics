#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import psycopg2

ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REGISTRIES_DIR = ROOT / "scripts" / "registries"
if str(REGISTRIES_DIR) not in sys.path:
    sys.path.insert(0, str(REGISTRIES_DIR))

from monthly_kpi_fact_ingestion_registry import (
    MonthlyKpiIngestionStep,
    current_month_start,
    monthly_kpi_steps,
)
from monthly_kpi_period_utils import month_end
from run_weekly_fact_ingestion import CREATE_RUNS_SQL, CREATE_STEPS_SQL, clip

DEFAULT_REPORT_PATH = ROOT / "artifacts" / "run_reports" / "monthly_kpi_fact_ingestion_run_report.csv"


def ensure_logging_tables(conn) -> None:
    with conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_RUNS_SQL)
            cur.execute(CREATE_STEPS_SQL)


def insert_run(conn, run_id: str, month_start_value: date, trigger_mode: str, step_keys: list[str]) -> None:
    started_at = datetime.now(timezone.utc)
    payload = json.dumps({"step_keys": step_keys, "contour": "monthly_kpi"})
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fact_ingestion_runs (
                    run_id, cadence, period_start, period_end, status, started_at, trigger_mode, payload
                )
                VALUES (%s, 'month', %s, %s, 'running', %s, %s, %s::jsonb)
                """,
                (run_id, month_start_value, month_end(month_start_value), started_at, trigger_mode, payload),
            )


def update_run_status(conn, run_id: str, status: str) -> None:
    finished_at = datetime.now(timezone.utc)
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE fact_ingestion_runs SET status=%s, finished_at=%s WHERE run_id=%s",
                (status, finished_at, run_id),
            )


def upsert_step_log(
    conn,
    run_id: str,
    step: MonthlyKpiIngestionStep,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    exit_code: int | None,
    stdout_excerpt: str,
    stderr_excerpt: str,
    notes: str,
) -> None:
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fact_ingestion_run_steps (
                    run_id, step_key, source_system, script_path, source_run_id, report_path,
                    status, started_at, finished_at, exit_code, stdout_excerpt, stderr_excerpt, notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, step_key)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    finished_at = EXCLUDED.finished_at,
                    exit_code = EXCLUDED.exit_code,
                    stdout_excerpt = EXCLUDED.stdout_excerpt,
                    stderr_excerpt = EXCLUDED.stderr_excerpt,
                    notes = EXCLUDED.notes
                """,
                (
                    run_id,
                    step.key,
                    step.source_system,
                    str(step.script_path) if step.script_path else None,
                    step.source_run_id,
                    str(step.report_path),
                    status,
                    started_at,
                    finished_at,
                    exit_code,
                    stdout_excerpt,
                    stderr_excerpt,
                    notes,
                ),
            )


def build_command(step: MonthlyKpiIngestionStep, database_url: str, month_start_value: date, delete_existing: bool) -> list[str]:
    if not step.script_path:
        raise RuntimeError(f"step {step.key} has no script_path")
    cmd = [
        sys.executable,
        str(step.script_path),
        "--database-url",
        database_url,
        "--month-start",
        month_start_value.isoformat(),
        "--source-run-id",
        step.source_run_id,
        "--report-path",
        str(step.report_path),
    ]
    if delete_existing:
        cmd.append("--delete-existing")
    cmd.extend(step.extra_args)
    return cmd


def select_steps(all_steps: Iterable[MonthlyKpiIngestionStep], requested: set[str] | None) -> list[MonthlyKpiIngestionStep]:
    steps = list(all_steps)
    if not requested:
        return steps
    return [step for step in steps if step.key in requested]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the monthly KPI fact-layer ingestion pipeline.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--month-start", help="YYYY-MM-DD for the first day of the month to load")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--steps", help="Comma-separated subset of step keys to run")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--skip-pending", action="store_true")
    args = parser.parse_args()

    month_start_value = date.fromisoformat(args.month_start) if args.month_start else current_month_start()
    if month_start_value.day != 1:
        raise SystemExit("--month-start must be the first day of a month")

    requested = {part.strip() for part in args.steps.split(",")} if args.steps else None
    steps = select_steps(monthly_kpi_steps(), requested)
    if args.skip_pending:
        steps = [step for step in steps if step.implemented]

    run_id = f"monthly_kpi_fact_ingestion_{month_start_value.isoformat()}_{uuid.uuid4().hex[:8]}"
    conn = psycopg2.connect(args.database_url)
    ensure_logging_tables(conn)
    insert_run(conn, run_id, month_start_value, "manual_cli", [step.key for step in steps])

    report_rows: list[dict[str, str]] = []
    overall_status = "success"

    for step in steps:
        started_at = datetime.now(timezone.utc)
        if not step.implemented:
            finished_at = datetime.now(timezone.utc)
            note = "Step is part of the monthly KPI contour, but importer is not implemented yet."
            upsert_step_log(conn, run_id, step, "pending", started_at, finished_at, None, "", "", note)
            report_rows.append(
                {
                    "run_id": run_id,
                    "month_start": month_start_value.isoformat(),
                    "step_key": step.key,
                    "label": step.label,
                    "source_system": step.source_system,
                    "status": "pending",
                    "exit_code": "",
                    "source_run_id": step.source_run_id,
                    "report_path": str(step.report_path),
                    "notes": note,
                }
            )
            overall_status = "partial"
            continue

        proc = subprocess.run(
            build_command(step, args.database_url, month_start_value, args.delete_existing),
            capture_output=True,
            text=True,
        )
        finished_at = datetime.now(timezone.utc)
        status = "success" if proc.returncode == 0 else "pending" if proc.returncode == 20 else "failed"
        if status == "failed":
            overall_status = "failed"
        elif status == "pending" and overall_status == "success":
            overall_status = "partial"
        upsert_step_log(
            conn,
            run_id,
            step,
            status,
            started_at,
            finished_at,
            proc.returncode,
            clip(proc.stdout.strip()),
            clip(proc.stderr.strip()),
            step.description,
        )
        report_rows.append(
            {
                "run_id": run_id,
                "month_start": month_start_value.isoformat(),
                "step_key": step.key,
                "label": step.label,
                "source_system": step.source_system,
                "status": status,
                "exit_code": str(proc.returncode),
                "source_run_id": step.source_run_id,
                "report_path": str(step.report_path),
                "notes": step.description,
            }
        )
        if proc.returncode not in {0, 20} and not args.continue_on_error:
            break

    if overall_status == "success" and any(row["status"] == "pending" for row in report_rows):
        overall_status = "partial"
    update_run_status(conn, run_id, overall_status)
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "run_id",
                "month_start",
                "step_key",
                "label",
                "source_system",
                "status",
                "exit_code",
                "source_run_id",
                "report_path",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(report_rows)

    print(
        json.dumps(
            {
                "run_id": run_id,
                "month_start": month_start_value.isoformat(),
                "overall_status": overall_status,
                "steps_total": len(report_rows),
                "steps_success": sum(1 for row in report_rows if row["status"] == "success"),
                "steps_pending": sum(1 for row in report_rows if row["status"] == "pending"),
                "steps_failed": sum(1 for row in report_rows if row["status"] == "failed"),
                "report_path": str(report_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if overall_status in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
