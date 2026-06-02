#!/usr/bin/env python3
import argparse
import os
import subprocess
import uuid

import psycopg2


ENV_PATH = "/opt/analytics/parser/.env"
YOY_SCRIPT = "/opt/analytics/parser/rebuild_weekly_metrics_yoy_views.py"
TRACE_SCRIPT = "/opt/analytics/parser/rebuild_weekly_metrics_trace_view.py"


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS dashboard_refresh_runs (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL,
    job_name TEXT NOT NULL,
    dashboard_scope TEXT NOT NULL,
    triggered_by TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    exit_code INTEGER,
    yoy_refresh_ok BOOLEAN,
    trace_refresh_ok BOOLEAN,
    stdout TEXT,
    stderr TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_dashboard_refresh_runs_started_at
    ON dashboard_refresh_runs(started_at DESC);
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


def create_run_row(conn, batch_id: str, job_name: str, dashboard_scope: str, triggered_by: str) -> int:
    sql = """
    INSERT INTO dashboard_refresh_runs (
        batch_id,
        job_name,
        dashboard_scope,
        triggered_by,
        status
    ) VALUES (%s, %s, %s, %s, 'running')
    RETURNING id
    """
    with conn.cursor() as cur:
        cur.execute(sql, (batch_id, job_name, dashboard_scope, triggered_by))
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finalize_run_row(
    conn,
    run_id: int,
    *,
    status: str,
    exit_code: int,
    yoy_refresh_ok: bool,
    trace_refresh_ok: bool,
    stdout: str,
    stderr: str,
) -> None:
    sql = """
    UPDATE dashboard_refresh_runs
    SET
        status = %s,
        exit_code = %s,
        yoy_refresh_ok = %s,
        trace_refresh_ok = %s,
        stdout = %s,
        stderr = %s,
        finished_at = NOW()
    WHERE id = %s
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (status, exit_code, yoy_refresh_ok, trace_refresh_ok, stdout, stderr, run_id),
        )
    conn.commit()


def run_step(script_path: str, database_url: str) -> subprocess.CompletedProcess[str]:
    cmd = ["python3", script_path, "--database-url", database_url]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def main() -> None:
    load_env_file(ENV_PATH)

    parser = argparse.ArgumentParser()
    parser.add_argument("--triggered-by", default="manual")
    parser.add_argument("--job-name", default="weekly_dashboard_refresh")
    parser.add_argument("--dashboard-scope", default="b2c_moscow,b2c_spb")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()

    if not args.database_url:
        raise ValueError("DATABASE_URL is required")

    batch_id = str(uuid.uuid4())
    conn = psycopg2.connect(args.database_url)
    try:
        ensure_log_table(conn)
        run_id = create_run_row(conn, batch_id, args.job_name, args.dashboard_scope, args.triggered_by)

        parts = []
        errors = []

        yoy_result = run_step(YOY_SCRIPT, args.database_url)
        parts.append(f"[yoy] exit_code={yoy_result.returncode}")
        if yoy_result.stdout.strip():
            parts.append(yoy_result.stdout.strip())
        if yoy_result.stderr.strip():
            errors.append(f"[yoy]\n{yoy_result.stderr.strip()}")

        trace_result = run_step(TRACE_SCRIPT, args.database_url)
        parts.append(f"[trace] exit_code={trace_result.returncode}")
        if trace_result.stdout.strip():
            parts.append(trace_result.stdout.strip())
        if trace_result.stderr.strip():
            errors.append(f"[trace]\n{trace_result.stderr.strip()}")

        yoy_ok = yoy_result.returncode == 0
        trace_ok = trace_result.returncode == 0
        exit_code = 0 if (yoy_ok and trace_ok) else 1
        status = "success" if exit_code == 0 else "failed"

        finalize_run_row(
            conn,
            run_id,
            status=status,
            exit_code=exit_code,
            yoy_refresh_ok=yoy_ok,
            trace_refresh_ok=trace_ok,
            stdout="\n".join(parts).strip(),
            stderr="\n\n".join(errors).strip(),
        )

        print("\n".join(parts))
        if errors:
            print("\n\n".join(errors))
    finally:
        conn.close()

    if not (yoy_ok and trace_ok):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
