#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import ssl
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
from typing import Iterable
from urllib import request
from urllib import parse

import psycopg2


MSK = timezone(timedelta(hours=3))
SSL_CONTEXT = ssl._create_unverified_context()
ERP_BASE = "https://morpheus-server.ru:{port}{path}"
ENV_PATH = "/opt/analytics/parser/.env"
ROOT = Path(__file__).resolve().parent.parent
YANDEX_ENV_MAIN = ROOT / ".env.yandex_tickets"
YANDEX_ENV_SPB = ROOT / ".env.yandex_tickets_spb"

UNITS = {
    "b2c_moscow": {
        "label": "Москва",
        "port": 45010,
        "yandex_env_path": YANDEX_ENV_MAIN,
        "yandex_login_key": "YANDEX_TICKETS_LOGIN",
        "yandex_password_key": "YANDEX_TICKETS_PASSWORD",
        "yandex_city_key": "YANDEX_TICKETS_CITY_ID",
    },
    "b2c_spb": {
        "label": "СПб",
        "port": 45011,
        "yandex_env_path": YANDEX_ENV_SPB,
        "yandex_login_key": "YANDEX_TICKETS_SPB_LOGIN",
        "yandex_password_key": "YANDEX_TICKETS_SPB_PASSWORD",
        "yandex_city_key": "YANDEX_TICKETS_SPB_CITY_ID",
    },
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
    actual_tickets_count INTEGER NOT NULL,
    bought_orders_count INTEGER NOT NULL,
    bought_revenue_rub NUMERIC(18,2) NOT NULL,
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
    'Temporary snapshot of future seance-level buyout for a selected show using ERP shows/get + tickets/by-sell join.';
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


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


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


def yandex_credentials(cfg: dict) -> tuple[str, str, str] | None:
    env_file_values = read_env(cfg["yandex_env_path"])

    def pick(key: str) -> str:
        return env_file_values.get(key) or os.getenv(key, "")

    login = pick(cfg["yandex_login_key"])
    password = pick(cfg["yandex_password_key"])
    city_id = pick(cfg["yandex_city_key"])
    if not (login and password and city_id):
        return None
    return login, password, city_id


def yandex_auth(login: str, password: str) -> str:
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    md5 = hashlib.md5(password.encode("utf-8")).hexdigest()
    sha1 = hashlib.sha1((md5 + timestamp).encode("utf-8")).hexdigest()
    return f"{login}:{sha1}:{timestamp}"


def yandex_post(params: dict[str, str]) -> dict:
    url = "https://api.tickets.yandex.net/api/crm/?" + parse.urlencode(params)
    req = request.Request(url, method="POST")
    with request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_yandex_orders(login: str, password: str, city_id: str, dt_from: datetime, dt_to: datetime) -> list[dict]:
    payload = yandex_post(
        {
            "action": "crm.order.list",
            "auth": yandex_auth(login, password),
            "city_id": city_id,
            "start_date": dt_from.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S+0300"),
            "end_date": dt_to.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S+0300"),
        }
    )
    if payload.get("status") != "0":
        raise RuntimeError(f"Yandex Tickets order.list error: {payload}")
    orders: list[dict] = []
    for batch in payload.get("result") or []:
        if isinstance(batch, list):
            orders.extend(batch)
    return orders


def order_customer_key(order: dict) -> str | None:
    customer = order.get("customer") or {}
    customer_id = customer.get("id") or order.get("customer_id")
    if customer_id:
        return f"id:{customer_id}"
    email = (customer.get("email") or "").strip().lower()
    phone = "".join(ch for ch in str(customer.get("phone") or "") if ch.isdigit())
    name = (customer.get("name") or "").strip().lower()
    if email:
        return f"email:{email}"
    if phone:
        return f"phone:{phone}"
    if name:
        return f"name:{name}"
    return None


def sold_yandex_orders(orders: list[dict]) -> list[dict]:
    result: list[dict] = []
    for order in orders:
        if to_int(order.get("status")) == 0:
            continue
        if to_int(order.get("is_returned")) == 1:
            continue
        result.append(order)
    return result


def actual_ticket_counts_from_yandex(
    *,
    cfg: dict,
    show_ids: set[str],
    sales_from: datetime,
    as_of: datetime,
) -> Counter | None:
    creds = yandex_credentials(cfg)
    if not creds or not show_ids:
        return None

    login, password, city_id = creds
    raw_orders = fetch_yandex_orders(login, password, city_id, sales_from, as_of)
    orders = [
        order
        for order in sold_yandex_orders(raw_orders)
        if str(order.get("event_id") or "") in show_ids
    ]

    active_counts: Counter = Counter()
    positive_orders_by_customer: dict[tuple[str, int], list[dict]] = {}

    parsed_orders = []
    for order in orders:
        event_id = str(order.get("event_id") or "")
        tickets_count = to_int(order.get("tickets_count"))
        if not event_id or tickets_count <= 0:
            continue
        total = to_int(order.get("sum"))
        order_dt = datetime.strptime(order["order_date"], "%Y-%m-%d %H:%M:%S%z").astimezone(MSK)
        customer_key = order_customer_key(order)
        active_counts[event_id] += tickets_count
        parsed = {
            "event_id": event_id,
            "tickets_count": tickets_count,
            "total": total,
            "order_dt": order_dt,
            "customer_key": customer_key,
        }
        parsed_orders.append(parsed)
        if total > 0 and customer_key:
            positive_orders_by_customer.setdefault((customer_key, tickets_count), []).append(parsed)

    for items in positive_orders_by_customer.values():
        items.sort(key=lambda row: row["order_dt"])

    transferred_out: Counter = Counter()
    used_positive_ids: set[tuple[str, datetime, int]] = set()

    # A zero-sum active order for the same customer and ticket count is treated as a transfer target.
    for order in sorted(parsed_orders, key=lambda row: row["order_dt"]):
        if order["total"] != 0 or not order["customer_key"]:
            continue
        candidates = positive_orders_by_customer.get((order["customer_key"], order["tickets_count"]), [])
        for candidate in reversed(candidates):
            candidate_identity = (
                candidate["event_id"],
                candidate["order_dt"],
                candidate["tickets_count"],
            )
            if candidate_identity in used_positive_ids:
                continue
            if candidate["order_dt"] > order["order_dt"]:
                continue
            if candidate["event_id"] == order["event_id"]:
                continue
            used_positive_ids.add(candidate_identity)
            transferred_out[candidate["event_id"]] += candidate["tickets_count"]
            break

    actual_counts: Counter = Counter()
    for event_id, count in active_counts.items():
        actual_counts[event_id] = max(count - transferred_out[event_id], 0)
    return actual_counts


def fetch_snapshot_rows(show_name: str, horizon_days: int) -> list[tuple]:
    now_msk = datetime.now(MSK)
    show_end = now_msk + timedelta(days=horizon_days)
    sales_from = now_msk - timedelta(days=180)
    rows: list[tuple] = []

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
        actual_tickets_count = actual_ticket_counts_from_yandex(
            cfg=cfg,
            show_ids=show_ids,
            sales_from=sales_from,
            as_of=now_msk,
        )

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
                    (
                        actual_tickets_count[seance_id]
                        if actual_tickets_count is not None
                        else ticket_counts[seance_id]
                    ),
                    order_counts[seance_id],
                    round(revenue_rub[seance_id], 2),
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
                actual_tickets_count,
                bought_orders_count,
                bought_revenue_rub,
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
