#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
ENV_PATH = ROOT / ".env.amocrm"
DEFAULT_BASE_URL = "https://morpheusshow.amocrm.ru"
SSL_CONTEXT = ssl._create_unverified_context()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def fetch_json(url: str, token: str) -> dict:
    request = Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urlopen(request, timeout=120, context=SSL_CONTEXT) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--env-file", default=str(ENV_PATH))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--pipeline-id", type=int, action="append")
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    token = os.environ.get("AMOCRM_LONG_LIVED_TOKEN", "")
    if not token:
        raise RuntimeError("AMOCRM_LONG_LIVED_TOKEN is missing")

    base_url = args.base_url.rstrip("/")
    pipelines: list[dict] = []
    if args.pipeline_id:
        for pipeline_id in args.pipeline_id:
            pipelines.append(fetch_json(f"{base_url}/api/v4/leads/pipelines/{pipeline_id}", token))
    else:
        payload = fetch_json(f"{base_url}/api/v4/leads/pipelines?{urlencode({'limit': 250})}", token)
        pipelines.extend(payload.get("_embedded", {}).get("pipelines", []) or [])

    now = datetime.now(timezone.utc)
    rows: list[dict] = []
    for pipeline in pipelines:
        pipeline_id = int(pipeline["id"])
        pipeline_name = pipeline.get("name") or ""
        statuses = pipeline.get("_embedded", {}).get("statuses", []) or []
        for status in statuses:
            rows.append(
                {
                    "pipeline_id": pipeline_id,
                    "pipeline_name": pipeline_name,
                    "status_id": int(status["id"]),
                    "status_name": status.get("name") or "",
                    "sort_order": status.get("sort"),
                    "status_type": status.get("type"),
                    "is_editable": status.get("is_editable"),
                    "color": status.get("color"),
                    "raw_json": Json(status),
                    "synced_at": now,
                }
            )

    sql = """
    INSERT INTO raw_amocrm_pipeline_statuses (
        pipeline_id, pipeline_name, status_id, status_name, sort_order, status_type,
        is_editable, color, raw_json, synced_at
    )
    VALUES (
        %(pipeline_id)s, %(pipeline_name)s, %(status_id)s, %(status_name)s, %(sort_order)s, %(status_type)s,
        %(is_editable)s, %(color)s, %(raw_json)s, %(synced_at)s
    )
    ON CONFLICT (pipeline_id, status_id)
    DO UPDATE SET
        pipeline_name = EXCLUDED.pipeline_name,
        status_name = EXCLUDED.status_name,
        sort_order = EXCLUDED.sort_order,
        status_type = EXCLUDED.status_type,
        is_editable = EXCLUDED.is_editable,
        color = EXCLUDED.color,
        raw_json = EXCLUDED.raw_json,
        synced_at = EXCLUDED.synced_at
    """

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                execute_batch(cur, sql, rows, page_size=200)
    finally:
        conn.close()

    print(f"upserted_statuses={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
