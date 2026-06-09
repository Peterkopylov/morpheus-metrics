#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import ssl
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
ENV_PATH = ROOT / ".env.amocrm"
DEFAULT_BASE_URL = "https://morpheusshow.amocrm.ru"
DEFAULT_TIMEZONE = "Europe/Moscow"
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


def parse_date(value: str, tz_name: str, end_of_day: bool) -> int:
    tz = ZoneInfo(tz_name)
    dt = datetime.strptime(value, "%Y-%m-%d")
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59, tzinfo=tz)
    else:
        dt = dt.replace(hour=0, minute=0, second=0, tzinfo=tz)
    return int(dt.timestamp())


def fetch_json(url: str, token: str) -> dict:
    request = Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urlopen(request, timeout=120, context=SSL_CONTEXT) as response:
        return json.load(response)


def fetch_status_events(base_url: str, token: str, created_from: int, created_to: int) -> list[dict]:
    events: list[dict] = []
    page = 1
    while True:
        query = urlencode(
            [
                ("filter[entity]", "lead"),
                ("filter[type][0]", "lead_status_changed"),
                ("filter[created_at][from]", str(created_from)),
                ("filter[created_at][to]", str(created_to)),
                ("limit", "250"),
                ("page", str(page)),
            ]
        )
        payload = fetch_json(f"{base_url.rstrip('/')}/api/v4/events?{query}", token)
        chunk = payload.get("_embedded", {}).get("events", []) or []
        events.extend(chunk)
        if not chunk or len(chunk) < 250:
            break
        page += 1
    return events


def extract_status(side: list | None) -> tuple[int | None, int | None]:
    if not side:
        return None, None
    raw = (side[0] or {}).get("lead_status") or {}
    status_id = raw.get("id")
    pipeline_id = raw.get("pipeline_id")
    return (int(pipeline_id) if pipeline_id is not None else None, int(status_id) if status_id is not None else None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--pipeline-id", type=int)
    parser.add_argument("--env-file", default=str(ENV_PATH))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    token = os.environ.get("AMOCRM_LONG_LIVED_TOKEN", "")
    if not token:
        raise RuntimeError("AMOCRM_LONG_LIVED_TOKEN is missing")

    created_from = parse_date(args.date_from, args.timezone, end_of_day=False)
    created_to = parse_date(args.date_to, args.timezone, end_of_day=True)
    events = fetch_status_events(args.base_url, token, created_from, created_to)

    synced_at = datetime.now(ZoneInfo("UTC"))
    rows = []
    for event in events:
        pipeline_before_id, status_before_id = extract_status(event.get("value_before"))
        pipeline_after_id, status_after_id = extract_status(event.get("value_after"))
        if args.pipeline_id and args.pipeline_id not in {pipeline_before_id, pipeline_after_id}:
            continue
        rows.append(
            {
                "event_id": event["id"],
                "lead_id": int(event["entity_id"]),
                "event_type": event["type"],
                "created_at": datetime.fromtimestamp(int(event["created_at"]), tz=ZoneInfo("UTC")),
                "created_by": event.get("created_by"),
                "account_id": event.get("account_id"),
                "pipeline_before_id": pipeline_before_id,
                "status_before_id": status_before_id,
                "pipeline_after_id": pipeline_after_id,
                "status_after_id": status_after_id,
                "value_before_json": Json(event.get("value_before") or []),
                "value_after_json": Json(event.get("value_after") or []),
                "raw_json": Json(event),
                "synced_at": synced_at,
            }
        )

    sql = """
    INSERT INTO raw_amocrm_lead_status_events (
        event_id, lead_id, event_type, created_at, created_by, account_id,
        pipeline_before_id, status_before_id, pipeline_after_id, status_after_id,
        value_before_json, value_after_json, raw_json, synced_at
    )
    VALUES (
        %(event_id)s, %(lead_id)s, %(event_type)s, %(created_at)s, %(created_by)s, %(account_id)s,
        %(pipeline_before_id)s, %(status_before_id)s, %(pipeline_after_id)s, %(status_after_id)s,
        %(value_before_json)s, %(value_after_json)s, %(raw_json)s, %(synced_at)s
    )
    ON CONFLICT (event_id)
    DO UPDATE SET
        lead_id = EXCLUDED.lead_id,
        event_type = EXCLUDED.event_type,
        created_at = EXCLUDED.created_at,
        created_by = EXCLUDED.created_by,
        account_id = EXCLUDED.account_id,
        pipeline_before_id = EXCLUDED.pipeline_before_id,
        status_before_id = EXCLUDED.status_before_id,
        pipeline_after_id = EXCLUDED.pipeline_after_id,
        status_after_id = EXCLUDED.status_after_id,
        value_before_json = EXCLUDED.value_before_json,
        value_after_json = EXCLUDED.value_after_json,
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

    print(f"upserted_status_events={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
