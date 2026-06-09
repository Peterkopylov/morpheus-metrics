#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from typing import Optional

import psycopg2


ENV_PATH = "/opt/analytics/parser/.env"
PARSER_PATH = "/opt/analytics/parser/parse_sheet.py"
DASHBOARD_REFRESH_SCRIPT = "/opt/analytics/parser/run_weekly_dashboard_refresh.py"


SUMMARY_RE = re.compile(
    r"Loaded (?P<rows_loaded>\d+) fact rows .*?"
    r"metric_rows=(?P<metric_rows>\d+), unmapped_pairs=(?P<unmapped_pairs>\d+)",
    re.DOTALL,
)


@dataclass(frozen=True)
class SourceSpec:
    unit: str
    source_tab: str
    source_sheet_id: str
    source_gid: str
    aggregation_level: str = "week"


SOURCES = (
    SourceSpec(
        unit="b2c_moscow",
        source_tab="weekly_b2c_moscow",
        source_sheet_id="1gHuxPxZntVLAxhxY9yFuBRhvozm45r2LcnvId83CY-s",
        source_gid="1411303700",
    ),
    SourceSpec(
        unit="b2c_spb",
        source_tab="weekly_b2c_spb",
        source_sheet_id="1q71g1XD5fwTMo7xbEe1fGvXVTRyPfEswCPxyjVTEZi0",
        source_gid="1411303700",
    ),
)


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS weekly_import_runs (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL,
    job_name TEXT NOT NULL,
    unit TEXT NOT NULL,
    source_tab TEXT NOT NULL,
    source_sheet_id TEXT NOT NULL,
    source_gid TEXT NOT NULL,
    aggregation_level TEXT NOT NULL,
    triggered_by TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    exit_code INTEGER,
    rows_loaded INTEGER,
    metric_rows INTEGER,
    unmapped_pairs INTEGER,
    parser_stdout TEXT,
    parser_stderr TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_weekly_import_runs_batch_id
    ON weekly_import_runs(batch_id);

CREATE INDEX IF NOT EXISTS idx_weekly_import_runs_started_at
    ON weekly_import_runs(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_weekly_import_runs_unit_started_at
    ON weekly_import_runs(unit, started_at DESC);
"""


def load_env_file(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def ensure_log_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
    conn.commit()


def create_run_row(conn, batch_id: str, job_name: str, source: SourceSpec, triggered_by: str) -> int:
    sql = """
    INSERT INTO weekly_import_runs (
        batch_id,
        job_name,
        unit,
        source_tab,
        source_sheet_id,
        source_gid,
        aggregation_level,
        triggered_by,
        status
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'running')
    RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                batch_id,
                job_name,
                source.unit,
                source.source_tab,
                source.source_sheet_id,
                source.source_gid,
                source.aggregation_level,
                triggered_by,
            ),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def parse_summary(stdout: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    match = SUMMARY_RE.search(stdout or "")
    if not match:
        return None, None, None
    return (
        int(match.group("rows_loaded")),
        int(match.group("metric_rows")),
        int(match.group("unmapped_pairs")),
    )


def finalize_run_row(
    conn,
    run_id: int,
    *,
    status: str,
    exit_code: int,
    stdout: str,
    stderr: str,
) -> None:
    rows_loaded, metric_rows, unmapped_pairs = parse_summary(stdout)
    sql = """
    UPDATE weekly_import_runs
    SET
        status = %s,
        exit_code = %s,
        rows_loaded = %s,
        metric_rows = %s,
        unmapped_pairs = %s,
        parser_stdout = %s,
        parser_stderr = %s,
        finished_at = NOW()
    WHERE id = %s
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                status,
                exit_code,
                rows_loaded,
                metric_rows,
                unmapped_pairs,
                stdout,
                stderr,
                run_id,
            ),
        )
    conn.commit()


def run_source(source: SourceSpec, database_url: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        "python3",
        PARSER_PATH,
        "--sheet-id",
        source.source_sheet_id,
        "--gid",
        source.source_gid,
        "--unit",
        source.unit,
        "--aggregation-level",
        source.aggregation_level,
        "--source-tab",
        source.source_tab,
        "--database-url",
        database_url,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def run_dashboard_refresh(database_url: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        "python3",
        DASHBOARD_REFRESH_SCRIPT,
        "--triggered-by",
        "post-weekly-ingest",
        "--database-url",
        database_url,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def main() -> None:
    load_env_file(ENV_PATH)

    parser = argparse.ArgumentParser()
    parser.add_argument("--triggered-by", default="manual")
    parser.add_argument("--job-name", default="weekly_google_sheets_ingest")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()

    if not args.database_url:
        raise ValueError("DATABASE_URL is required")

    batch_id = str(uuid.uuid4())
    any_failed = False

    conn = psycopg2.connect(args.database_url)
    try:
        ensure_log_table(conn)
        for source in SOURCES:
            run_id = create_run_row(conn, batch_id, args.job_name, source, args.triggered_by)
            result = run_source(source, args.database_url)
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            status = "success" if result.returncode == 0 else "failed"
            finalize_run_row(
                conn,
                run_id,
                status=status,
                exit_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
            )

            print(f"[{source.unit}] status={status} exit_code={result.returncode}")
            if stdout:
                print(stdout)
            if stderr:
                print(stderr)

            if result.returncode != 0:
                any_failed = True
    finally:
        conn.close()

    if not any_failed:
        refresh_result = run_dashboard_refresh(args.database_url)
        print(f"[dashboard_refresh] status={'success' if refresh_result.returncode == 0 else 'failed'} exit_code={refresh_result.returncode}")
        if refresh_result.stdout.strip():
            print(refresh_result.stdout.strip())
        if refresh_result.stderr.strip():
            print(refresh_result.stderr.strip())
        if refresh_result.returncode != 0:
            raise SystemExit(1)

    if any_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
