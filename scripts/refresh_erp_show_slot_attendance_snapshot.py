#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import ssl
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable
from urllib import request

import psycopg2
from psycopg2.extras import execute_values


MSK = timezone(timedelta(hours=3))
SSL_CONTEXT = ssl._create_unverified_context()
ERP_BASE = "https://morpheus-server.ru:{port}{path}"

UNITS = {
    "b2c_moscow": {
        "label": "Москва",
        "port": 45010,
    },
    "b2c_spb": {
        "label": "СПб",
        "port": 45011,
    },
}

CREATE_SQL = """
DROP TABLE IF EXISTS erp_show_slot_attendance_snapshot;

CREATE TABLE erp_show_slot_attendance_snapshot (
    id BIGSERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    business_unit TEXT NOT NULL,
    city_label TEXT NOT NULL,
    show_id TEXT NOT NULL,
    show_name TEXT NOT NULL,
    seance_start_msk TIMESTAMPTZ NOT NULL,
    seance_date DATE NOT NULL,
    slot_time TIME NOT NULL,
    iso_weekday SMALLINT NOT NULL,
    weekday_label TEXT NOT NULL,
    venue_title TEXT,
    venue_city TEXT,
    hall_title TEXT,
    guests_count INTEGER NOT NULL,
    capacity_tickets INTEGER,
    tickets_cert INTEGER,
    tickets_invite INTEGER,
    is_cancelled BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_erp_show_slot_attendance_snapshot_lookup
    ON erp_show_slot_attendance_snapshot(business_unit, seance_date, show_name, slot_time);

COMMENT ON TABLE erp_show_slot_attendance_snapshot IS
    'ERP seance-level attendance snapshot for slot dashboards, sourced from POST /shows/get.';
"""


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


def weekday_label(iso_weekday: int) -> str:
    return {
        1: "Пн",
        2: "Вт",
        3: "Ср",
        4: "Чт",
        5: "Пт",
        6: "Сб",
        7: "Вс",
    }[iso_weekday]


def iter_windows(date_from: date, date_to: date, window_days: int) -> Iterable[tuple[date, date]]:
    cursor = date_from
    while cursor <= date_to:
        window_end = min(cursor + timedelta(days=window_days - 1), date_to)
        yield cursor, window_end
        cursor = window_end + timedelta(days=1)


def fetch_snapshot_rows(date_from: date, date_to: date) -> list[tuple]:
    rows: list[tuple] = []

    for unit, meta in UNITS.items():
        for window_from, window_to in iter_windows(date_from, date_to, window_days=31):
            dt_from = datetime.combine(window_from, time.min, tzinfo=MSK)
            dt_to = datetime.combine(window_to, time.max, tzinfo=MSK)
            shows = fetch_json(
                meta["port"],
                "/shows/get",
                {"from": fmt_ts(dt_from), "to": fmt_ts(dt_to)},
            )
            print(
                json.dumps(
                    {
                        "unit": unit,
                        "window_from": window_from.isoformat(),
                        "window_to": window_to.isoformat(),
                        "rows_fetched": len(shows),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            for row in shows:
                show_id = str(row.get("show_id") or "").strip()
                show_name = (row.get("event_title") or row.get("show_name") or "").strip()
                show_start = row.get("show_start")
                if not show_id or not show_name or not show_start:
                    continue

                start_dt = datetime.fromisoformat(show_start).astimezone(MSK)
                capacity_tickets = to_int(row.get("tickets_count")) or None
                guests_count = to_int(row.get("guests"))
                iso_dow = start_dt.isoweekday()

                rows.append(
                    (
                        unit,
                        meta["label"],
                        show_id,
                        show_name,
                        start_dt,
                        start_dt.date(),
                        start_dt.time().replace(second=0, microsecond=0, tzinfo=None),
                        iso_dow,
                        weekday_label(iso_dow),
                        (row.get("venue_title") or "").strip() or None,
                        (row.get("venue_city") or "").strip() or None,
                        (row.get("hall_title") or "").strip() or None,
                        guests_count,
                        capacity_tickets,
                        to_int(row.get("tickets_cert")) or None,
                        to_int(row.get("tickets_invite")) or None,
                        bool(row.get("cancelled")),
                    )
                )

    rows.sort(key=lambda item: (item[0], item[5], item[6], item[4], item[3], item[2]))
    return rows


def replace_snapshot(conn, rows: Iterable[tuple]) -> None:
    with conn.cursor() as cur:
        cur.execute(CREATE_SQL)
        execute_values(
            cur,
            """
            INSERT INTO erp_show_slot_attendance_snapshot (
                business_unit,
                city_label,
                show_id,
                show_name,
                seance_start_msk,
                seance_date,
                slot_time,
                iso_weekday,
                weekday_label,
                venue_title,
                venue_city,
                hall_title,
                guests_count,
                capacity_tickets,
                tickets_cert,
                tickets_invite,
                is_cancelled
            ) VALUES %s
            """,
            list(rows),
            template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            page_size=1000,
        )
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--date-from", default="2026-01-01")
    parser.add_argument("--date-to", default=datetime.now(MSK).date().isoformat())
    args = parser.parse_args()

    date_from = date.fromisoformat(args.date_from)
    date_to = date.fromisoformat(args.date_to)
    if date_from > date_to:
        raise ValueError("--date-from must be <= --date-to")

    rows = fetch_snapshot_rows(date_from, date_to)
    conn = psycopg2.connect(args.database_url)
    try:
        replace_snapshot(conn, rows)
    finally:
        conn.close()

    print(
        json.dumps(
            {
                "table": "erp_show_slot_attendance_snapshot",
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "snapshot_rows": len(rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
