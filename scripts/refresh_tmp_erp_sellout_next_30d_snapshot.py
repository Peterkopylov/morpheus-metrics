#!/usr/bin/env python3
import argparse
import json
import ssl
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple
from urllib import request

import psycopg2


MSK = timezone(timedelta(hours=3))
SHOWS_BASE = "https://morpheus-server.ru:{port}/shows/get"
TICKETS_BASE = "https://morpheus-server.ru:{port}/tickets/by-sell"
SSL_CONTEXT = ssl._create_unverified_context()
ENV_PATH = "/opt/analytics/parser/.env"
UNITS = {
    "b2c_moscow": {"label": "Москва", "port": 45010},
    "b2c_spb": {"label": "СПб", "port": 45011},
}

CREATE_SQL = """
DROP TABLE IF EXISTS tmp_erp_sellout_next_30d_snapshot;

CREATE TABLE tmp_erp_sellout_next_30d_snapshot (
    id BIGSERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    as_of_msk TIMESTAMPTZ NOT NULL,
    unit TEXT NOT NULL,
    unit_label TEXT NOT NULL,
    show_id BIGINT,
    event_id BIGINT,
    event_title TEXT NOT NULL,
    show_start TIMESTAMPTZ NOT NULL,
    show_end TIMESTAMPTZ,
    hall_title TEXT,
    venue_title TEXT,
    guests_capacity INTEGER,
    tickets_count INTEGER,
    tickets_remaining INTEGER,
    tickets_cert INTEGER,
    tickets_invite INTEGER,
    sold_tickets_orders INTEGER,
    occupancy_pct NUMERIC(7,2),
    is_cancelled BOOLEAN NOT NULL DEFAULT FALSE,
    is_temporary BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_tmp_erp_sellout_next_30d_unit_show_start
    ON tmp_erp_sellout_next_30d_snapshot(unit, show_start);

COMMENT ON TABLE tmp_erp_sellout_next_30d_snapshot IS
    'Temporary prototype table for next-30-days ERP sellout dashboard. Safe to replace or drop after proper warehouse layer is built.';
"""


def load_env_file(path: str) -> None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and value:
                    import os
                    os.environ.setdefault(key, value)
    except FileNotFoundError:
        return


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S+03:00")


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(MSK)
    except ValueError:
        return None


def fetch_json_rows(url: str, start: datetime, end: datetime) -> List[dict]:
    body = json.dumps({"from": fmt_ts(start), "to": fmt_ts(end)}).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_shows_rows(port: int, start: datetime, end: datetime) -> List[dict]:
    return fetch_json_rows(SHOWS_BASE.format(port=port), start, end)


def fetch_ticket_rows(port: int, start: datetime, end: datetime) -> List[dict]:
    return fetch_json_rows(TICKETS_BASE.format(port=port), start, end)


def as_int(value) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def as_optional_int(value) -> Optional[int]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def occupancy_pct(tickets_count: int, tickets_remaining: int) -> Optional[float]:
    total_slots = tickets_count + tickets_remaining
    if total_slots <= 0:
        return None
    return round((tickets_count / total_slots) * 100.0, 2)


def sold_tickets_by_show_id(ticket_rows: List[dict]) -> Dict[int, int]:
    sold: Dict[int, int] = {}
    for row in ticket_rows:
        seance_id = as_optional_int(row.get("seance_id"))
        if seance_id is None:
            continue
        if as_int(row.get("total")) <= 0:
            continue
        sold[seance_id] = sold.get(seance_id, 0) + 1
    return sold


def current_rows(as_of: datetime) -> List[Tuple]:
    future_start = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
    future_end = future_start + timedelta(days=30)
    sales_start = (as_of - timedelta(days=365)).replace(hour=0, minute=0, second=0, microsecond=0)
    sales_end = as_of
    rows_out: List[Tuple] = []

    for unit, cfg in UNITS.items():
        future_shows = fetch_shows_rows(cfg["port"], future_start, future_end)
        sold_by_show = sold_tickets_by_show_id(fetch_ticket_rows(cfg["port"], sales_start, sales_end))

        for row in future_shows:
            show_start = parse_dt(row.get("show_start"))
            if not show_start:
                continue

            cancelled = bool(row.get("cancelled"))
            if cancelled:
                continue

            guests_capacity = as_int(row.get("guests"))
            paid_tickets = as_int(row.get("tickets_count"))
            tickets_remaining = as_int(row.get("tickets"))
            tickets_cert = as_int(row.get("tickets_cert"))
            tickets_invite = as_int(row.get("tickets_invite"))
            show_id = as_optional_int(row.get("show_id"))
            sold_tickets_orders = sold_by_show.get(show_id or -1, 0)

            rows_out.append(
                (
                    as_of,
                    unit,
                    cfg["label"],
                    show_id,
                    as_optional_int(row.get("event_id")),
                    row.get("event_title") or "Без названия",
                    show_start,
                    parse_dt(row.get("show_end")),
                    row.get("hall_title"),
                    row.get("venue_title"),
                    guests_capacity,
                    paid_tickets,
                    tickets_remaining,
                    tickets_cert,
                    tickets_invite,
                    sold_tickets_orders,
                    occupancy_pct(paid_tickets, tickets_remaining),
                    cancelled,
                )
            )

    return rows_out


def replace_snapshot(conn, rows: Iterable[Tuple]) -> None:
    with conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_SQL)
            cur.executemany(
                """
                INSERT INTO tmp_erp_sellout_next_30d_snapshot (
                    as_of_msk,
                    unit,
                    unit_label,
                    show_id,
                    event_id,
                    event_title,
                    show_start,
                    show_end,
                    hall_title,
                    venue_title,
                    guests_capacity,
                    tickets_count,
                    tickets_remaining,
                    tickets_cert,
                    tickets_invite,
                    sold_tickets_orders,
                    occupancy_pct,
                    is_cancelled
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )


def main() -> None:
    load_env_file(ENV_PATH)

    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url")
    parser.add_argument("--as-of")
    args = parser.parse_args()

    import os
    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required")

    as_of = datetime.now(MSK)
    if args.as_of:
        as_of = datetime.fromisoformat(args.as_of).astimezone(MSK)

    conn = psycopg2.connect(database_url)
    try:
        rows = current_rows(as_of)
        replace_snapshot(conn, rows)
    finally:
        conn.close()

    print(
        json.dumps(
            {
                "snapshot_rows": len(rows),
                "as_of_msk": as_of.isoformat(),
                "units": sorted(UNITS.keys()),
                "table": "tmp_erp_sellout_next_30d_snapshot",
                "temporary_note": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
