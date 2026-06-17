#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import uuid
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import psycopg2

ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REGISTRIES_DIR = ROOT / "scripts" / "registries"
if str(REGISTRIES_DIR) not in sys.path:
    sys.path.insert(0, str(REGISTRIES_DIR))

from weekly_fact_ingestion_registry import WeeklyIngestionStep, last_full_week_start, weekly_steps


DEFAULT_REPORT_PATH = ROOT / "artifacts" / "run_reports" / "weekly_fact_ingestion_run_report.csv"


CREATE_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS fact_ingestion_runs (
    run_id TEXT PRIMARY KEY,
    cadence TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    trigger_mode TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
)
"""

CREATE_STEPS_SQL = """
CREATE TABLE IF NOT EXISTS fact_ingestion_run_steps (
    run_id TEXT NOT NULL REFERENCES fact_ingestion_runs(run_id) ON DELETE CASCADE,
    step_key TEXT NOT NULL,
    source_system TEXT NOT NULL,
    script_path TEXT,
    source_run_id TEXT NOT NULL,
    report_path TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    exit_code INTEGER,
    stdout_excerpt TEXT,
    stderr_excerpt TEXT,
    notes TEXT,
    PRIMARY KEY (run_id, step_key)
)
"""


def clip(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def period_end(week_start: date) -> date:
    from datetime import timedelta

    return week_start + timedelta(days=6)


def ensure_logging_tables(conn) -> None:
    with conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_RUNS_SQL)
            cur.execute(CREATE_STEPS_SQL)


def insert_run(conn, run_id: str, week_start: date, trigger_mode: str, step_keys: list[str]) -> None:
    started_at = datetime.now(timezone.utc)
    payload = json.dumps({"step_keys": step_keys})
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fact_ingestion_runs (
                    run_id, cadence, period_start, period_end, status, started_at, trigger_mode, payload
                )
                VALUES (%s, 'week', %s, %s, 'running', %s, %s, %s::jsonb)
                """,
                (run_id, week_start, period_end(week_start), started_at, trigger_mode, payload),
            )


def update_run_status(conn, run_id: str, status: str) -> None:
    finished_at = datetime.now(timezone.utc)
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE fact_ingestion_runs
                SET status=%s, finished_at=%s
                WHERE run_id=%s
                """,
                (status, finished_at, run_id),
            )


def upsert_step_log(
    conn,
    run_id: str,
    step: WeeklyIngestionStep,
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


def build_command(step: WeeklyIngestionStep, database_url: str, week_start: date, delete_existing: bool) -> list[str]:
    if not step.script_path:
        raise RuntimeError(f"step {step.key} has no script_path")
    cmd = [
        sys.executable,
        str(step.script_path),
        "--database-url",
        database_url,
        "--week-start",
        week_start.isoformat(),
        "--source-run-id",
        step.source_run_id,
        "--report-path",
        str(step.report_path),
    ]
    if delete_existing:
        cmd.append("--delete-existing")
    cmd.extend(step.extra_args)
    return cmd


def select_steps(all_steps: Iterable[WeeklyIngestionStep], requested: set[str] | None) -> list[WeeklyIngestionStep]:
    steps = list(all_steps)
    if not requested:
        return steps
    return [step for step in steps if step.key in requested]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the weekly fact-layer ingestion pipeline.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--week-start", help="YYYY-MM-DD for the Monday of the week to load")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--trigger-mode", default="manual_cli")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--steps", help="Comma-separated subset of step keys to run")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--skip-pending", action="store_true", help="Hide pending/unimplemented steps from the run")
    args = parser.parse_args()

    week_start = date.fromisoformat(args.week_start) if args.week_start else last_full_week_start()
    requested = {part.strip() for part in args.steps.split(",")} if args.steps else None
    steps = select_steps(weekly_steps(), requested)
    if args.skip_pending:
        steps = [step for step in steps if step.implemented]

    run_id = f"weekly_fact_ingestion_{week_start.isoformat()}_{uuid.uuid4().hex[:8]}"
    conn = psycopg2.connect(args.database_url)
    ensure_logging_tables(conn)
    insert_run(conn, run_id, week_start, trigger_mode=args.trigger_mode, step_keys=[step.key for step in steps])

    report_rows: list[dict[str, str]] = []
    overall_status = "success"

    for step in steps:
        started_at = datetime.now(timezone.utc)
        if not step.implemented:
            finished_at = datetime.now(timezone.utc)
            note = "Step is part of the weekly source-of-truth contour, but importer is not implemented yet."
            upsert_step_log(
                conn,
                run_id,
                step,
                status="pending",
                started_at=started_at,
                finished_at=finished_at,
                exit_code=None,
                stdout_excerpt="",
                stderr_excerpt="",
                notes=note,
            )
            report_rows.append(
                {
                    "run_id": run_id,
                    "week_start": week_start.isoformat(),
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

        cmd = build_command(step, args.database_url, week_start, args.delete_existing)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        finished_at = datetime.now(timezone.utc)
        if proc.returncode == 0:
            status = "success"
        elif proc.returncode == 20:
            status = "pending"
        else:
            status = "failed"
        if status == "failed":
            overall_status = "failed"
        elif status == "pending" and overall_status == "success":
            overall_status = "partial"
        stdout_excerpt = clip(proc.stdout.strip())
        stderr_excerpt = clip(proc.stderr.strip())
        upsert_step_log(
            conn,
            run_id,
            step,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=proc.returncode,
            stdout_excerpt=stdout_excerpt,
            stderr_excerpt=stderr_excerpt,
            notes=step.description,
        )
        report_rows.append(
            {
                "run_id": run_id,
                "week_start": week_start.isoformat(),
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
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "run_id",
                "week_start",
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
                "week_start": week_start.isoformat(),
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
