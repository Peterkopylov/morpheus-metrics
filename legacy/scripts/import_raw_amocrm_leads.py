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


def fetch_all_leads(base_url: str, token: str, pipeline_id: int, created_from: int, created_to: int) -> list[dict]:
    leads: list[dict] = []
    page = 1
    while True:
        query = urlencode(
            [
                ("filter[pipeline_id][0]", str(pipeline_id)),
                ("filter[created_at][from]", str(created_from)),
                ("filter[created_at][to]", str(created_to)),
                ("limit", "250"),
                ("page", str(page)),
            ]
        )
        payload = fetch_json(f"{base_url.rstrip('/')}/api/v4/leads?{query}", token)
        chunk = payload.get("_embedded", {}).get("leads", []) or []
        leads.extend(chunk)
        if not chunk or len(chunk) < 250:
            break
        page += 1
    return leads


def ts_to_dt(value: int | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromtimestamp(int(value), tz=ZoneInfo("UTC"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--pipeline-id", type=int, required=True)
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
    leads = fetch_all_leads(args.base_url, token, args.pipeline_id, created_from, created_to)

    rows = []
    synced_at = datetime.now(ZoneInfo("UTC"))
    for lead in leads:
        rows.append(
            {
                "lead_id": int(lead["id"]),
                "pipeline_id": int(lead["pipeline_id"]),
                "status_id": int(lead["status_id"]),
                "name": lead.get("name"),
                "price": lead.get("price"),
                "responsible_user_id": lead.get("responsible_user_id"),
                "created_at": ts_to_dt(lead.get("created_at")),
                "updated_at": ts_to_dt(lead.get("updated_at")),
                "closed_at": ts_to_dt(lead.get("closed_at")),
                "raw_json": Json(lead),
                "synced_at": synced_at,
            }
        )

    sql = """
    INSERT INTO raw_amocrm_leads (
        lead_id, pipeline_id, status_id, name, price, responsible_user_id,
        created_at, updated_at, closed_at, raw_json, synced_at
    )
    VALUES (
        %(lead_id)s, %(pipeline_id)s, %(status_id)s, %(name)s, %(price)s, %(responsible_user_id)s,
        %(created_at)s, %(updated_at)s, %(closed_at)s, %(raw_json)s, %(synced_at)s
    )
    ON CONFLICT (lead_id)
    DO UPDATE SET
        pipeline_id = EXCLUDED.pipeline_id,
        status_id = EXCLUDED.status_id,
        name = EXCLUDED.name,
        price = EXCLUDED.price,
        responsible_user_id = EXCLUDED.responsible_user_id,
        created_at = EXCLUDED.created_at,
        updated_at = EXCLUDED.updated_at,
        closed_at = EXCLUDED.closed_at,
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

    print(f"upserted_leads={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
