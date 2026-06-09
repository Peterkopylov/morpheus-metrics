#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib import parse, request

import psycopg2


MSK = timezone(timedelta(hours=3))
SSL_CONTEXT = ssl._create_unverified_context()
ERP_BASE = "https://morpheus-server.ru:{port}{path}"
YANDEX_TICKETS_BASE = "https://api.tickets.yandex.net/api/crm/"
ENV_PATH = "/opt/analytics/parser/.env"

UNITS = {
    "b2c_moscow": {"label": "Москва", "port": 45010},
    "b2c_spb": {"label": "СПб", "port": 45011},
}

CREATE_SQL = """
DROP TABLE IF EXISTS tmp_erp_show_seance_buyout_snapshot;

CREATE TABLE tmp_erp_show_seance_buyout_snapshot (
    id BIGSERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    as_of_msk TIMESTAMPTZ NOT NULL,
    unit TEXT NOT NULL,
    unit_label TEXT NOT NULL,
    show_name TEXT NOT NULL,
    show_id TEXT NOT NULL,
    seance_start_msk TIMESTAMPTZ NOT NULL,
    seance_label TEXT NOT NULL,
    bought_tickets_count INTEGER NOT NULL,
    bought_orders_count INTEGER NOT NULL,
    bought_revenue_rub NUMERIC(18,2) NOT NULL,
    actual_tickets_count INTEGER,
    capacity_tickets INTEGER,
    tickets_cert INTEGER,
    tickets_invite INTEGER,
    is_cancelled BOOLEAN NOT NULL DEFAULT FALSE,
    horizon_days INTEGER NOT NULL,
    is_temporary BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_tmp_erp_show_seance_buyout_snapshot_lookup
    ON tmp_erp_show_seance_buyout_snapshot(unit, show_name, seance_start_msk);

COMMENT ON TABLE tmp_erp_show_seance_buyout_snapshot IS
    'Temporary snapshot of future seance-level buyout for a selected show using ERP shows/get + tickets/by-sell join and Yandex Tickets availability.';
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
                    os.environ.setdefault(key, value)
    except FileNotFoundError:
        return


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S+03:00")


def fetch_json(port: int, path: str, body: dict) -> list[dict]:
    payload = json.dumps(body).encode("utf-8")
    req = request.Request(
        ERP_BASE.format(port=port, path=path),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def to_int(value) -> int:
    try:
        return int(str(value))
    except Exception:
        return 0


def build_yandex_auth(login: str, password: str) -> str:
    timestamp = str(int(time.time()))
    md5 = hashlib.md5(password.encode("utf-8")).hexdigest()
    sha1 = hashlib.sha1((md5 + timestamp).encode("utf-8")).hexdigest()
    return f"{login}:{sha1}:{timestamp}"


def fetch_yandex_event_rows(login: str, password: str, city_id: str, event_id: str) -> list[dict]:
    params = {
        "action": "crm.report.event",
        "auth": build_yandex_auth(login, password),
        "city_id": city_id,
        "event_ids": event_id,
    }
    url = f"{YANDEX_TICKETS_BASE}?{parse.urlencode(params)}"
    req = request.Request(url, method="POST")
    with request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("result") or []


def occupied_tickets_from_yandex(event_rows: list[dict]) -> int:
    total_tickets = sum(to_int(row.get("tickets_count")) for row in event_rows)
    available_tickets = sum(to_int(row.get("tickets_available")) for row in event_rows)
    return max(total_tickets - available_tickets, 0)


def fetch_snapshot_rows(show_name: str, horizon_days: int) -> list[tuple]:
    now_msk = datetime.now(MSK)
    show_end = now_msk + timedelta(days=horizon_days)
    sales_from = now_msk - timedelta(days=180)
    rows: list[tuple] = []

    yt_login = os.getenv("YT_LOGIN", "")
    yt_password = os.getenv("YT_PASSWORD", "")
    yt_city_id = os.getenv("YT_CITY_ID", "")
    yandex_enabled = bool(yt_login and yt_password and yt_city_id)
    yandex_cache: dict[str, int | None] = {}

    for unit, cfg in UNITS.items():
        shows = fetch_json(
            cfg["port"],
            "/shows/get",
            {"from": fmt_ts(now_msk), "to": fmt_ts(show_end)},
        )
        matching_shows = [
            row
            for row in shows
            if (row.get("show_name") or row.get("event_title") or "").strip() == show_name
        ]
        show_ids = {str(row.get("show_id") or "") for row in matching_shows}

        sales = fetch_json(
            cfg["port"],
            "/tickets/by-sell",
            {"from": fmt_ts(sales_from), "to": fmt_ts(now_msk)},
        )

        ticket_counts = Counter()
        order_counts = Counter()
        revenue_rub = Counter()
        seen_orders: set[tuple[str, str]] = set()

        for sale in sales:
            seance_id = str(sale.get("seance_id") or "")
            if seance_id not in show_ids:
                continue
            total = to_int(sale.get("total"))
            if total <= 0:
                continue
            ticket_counts[seance_id] += 1
            revenue_rub[seance_id] += total / 100
            order_id = str(sale.get("order_id") or "")
            if order_id and (seance_id, order_id) not in seen_orders:
                seen_orders.add((seance_id, order_id))
                order_counts[seance_id] += 1

        for show_row in sorted(matching_shows, key=lambda r: r.get("show_start") or ""):
            seance_id = str(show_row.get("show_id") or "")
            start_raw = show_row.get("show_start")
            if not start_raw:
                continue
            start_dt = datetime.fromisoformat(start_raw).astimezone(MSK)

            actual_tickets_count = None
            if unit == "b2c_moscow" and yandex_enabled and seance_id:
                if seance_id not in yandex_cache:
                    event_rows = fetch_yandex_event_rows(yt_login, yt_password, yt_city_id, seance_id)
                    yandex_cache[seance_id] = occupied_tickets_from_yandex(event_rows)
                actual_tickets_count = yandex_cache[seance_id]

            rows.append(
                (
                    now_msk,
                    unit,
                    cfg["label"],
                    show_name,
                    seance_id,
                    start_dt,
                    start_dt.strftime("%d.%m.%Y %H:%M"),
                    ticket_counts[seance_id],
                    order_counts[seance_id],
                    round(revenue_rub[seance_id], 2),
                    actual_tickets_count,
                    to_int(show_row.get("tickets_count")) or None,
                    to_int(show_row.get("tickets_cert")) or None,
                    to_int(show_row.get("tickets_invite")) or None,
                    bool(show_row.get("cancelled")),
                    horizon_days,
                )
            )

    return rows


def replace_snapshot(conn, rows: Iterable[tuple]) -> None:
    with conn.cursor() as cur:
        cur.execute(CREATE_SQL)
        cur.executemany(
            """
            INSERT INTO tmp_erp_show_seance_buyout_snapshot (
                as_of_msk,
                unit,
                unit_label,
                show_name,
                show_id,
                seance_start_msk,
                seance_label,
                bought_tickets_count,
                bought_orders_count,
                bought_revenue_rub,
                actual_tickets_count,
                capacity_tickets,
                tickets_cert,
                tickets_invite,
                is_cancelled,
                horizon_days
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            list(rows),
        )
    conn.commit()


def main() -> None:
    load_env_file(ENV_PATH)

    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url")
    parser.add_argument("--show-name", default="Поезд, Чехов, два орла")
    parser.add_argument("--horizon-days", type=int, default=31)
    parser.add_argument("--as-of")
    args = parser.parse_args()

    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is required")

    if args.as_of:
        datetime.fromisoformat(args.as_of).astimezone(MSK)

    rows = fetch_snapshot_rows(args.show_name, args.horizon_days)
    conn = psycopg2.connect(database_url)
    try:
        replace_snapshot(conn, rows)
    finally:
        conn.close()

    print(
        json.dumps(
            {
                "table": "tmp_erp_show_seance_buyout_snapshot",
                "show_name": args.show_name,
                "horizon_days": args.horizon_days,
                "snapshot_rows": len(rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
