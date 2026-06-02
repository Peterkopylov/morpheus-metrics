#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import socket
import ssl
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error

from import_erp_weekly_to_fact import fetch_json, fmt_ts


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
DEFAULT_OUTPUT = ROOT / "generated" / "erp_avg_ticket_price_by_slot.csv"
MSK = timezone(timedelta(hours=3))
WEEKDAY = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}
UNITS = {
    "b2c_moscow": 45010,
    "b2c_spb": 45011,
}


def month_ranges(start: datetime, end: datetime):
    current = datetime(start.year, start.month, 1, tzinfo=start.tzinfo)
    while current <= end:
        if current.month == 12:
            nxt = datetime(current.year + 1, 1, 1, tzinfo=current.tzinfo)
        else:
            nxt = datetime(current.year, current.month + 1, 1, tzinfo=current.tzinfo)
        chunk_start = max(start, current)
        chunk_end = min(end, nxt - timedelta(seconds=1))
        yield chunk_start, chunk_end
        current = nxt


def fetch_json_with_retries(port: int, path: str, body: dict, retries: int = 4) -> list[dict]:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fetch_json(port, path, body)
        except (TimeoutError, socket.timeout, error.URLError, ssl.SSLError) as exc:
            last_exc = exc
            if attempt == retries - 1:
                break
            time.sleep(2 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def active_sale(row: dict) -> bool:
    status = str(row.get("status") or "").strip()
    try:
        total = int(str(row.get("total") or "0").strip())
    except Exception:
        total = 0
    return status != "0" and total > 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute ERP average ticket price by weekday/time slot.")
    parser.add_argument("--start", required=True, help="Seance start lower bound in YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Seance start upper bound in YYYY-MM-DD")
    parser.add_argument(
        "--sales-start",
        help="Ticket sell-date lower bound in YYYY-MM-DD. Default: start minus 90 days",
    )
    parser.add_argument(
        "--sales-end",
        help="Ticket sell-date upper bound in YYYY-MM-DD. Default: today",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-tickets", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = datetime.fromisoformat(f"{args.start}T00:00:00+03:00")
    end = datetime.fromisoformat(f"{args.end}T23:59:59+03:00")
    sales_start = (
        datetime.fromisoformat(f"{args.sales_start}T00:00:00+03:00")
        if args.sales_start
        else start - timedelta(days=90)
    )
    sales_end = (
        datetime.fromisoformat(f"{args.sales_end}T23:59:59+03:00")
        if args.sales_end
        else datetime.now(MSK)
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows_out: list[dict[str, str | int | float]] = []
    for unit, port in UNITS.items():
        shows = fetch_json_with_retries(port, "/shows/get", {"from": fmt_ts(start), "to": fmt_ts(end)})
        target_shows: dict[str, datetime] = {}
        for row in shows:
            show_id = row.get("show_id")
            show_start = row.get("show_start")
            if show_id is None or not show_start:
                continue
            target_shows[str(show_id)] = datetime.fromisoformat(show_start)

        slot_totals = defaultdict(lambda: {"revenue": 0, "tickets": 0, "seances": set()})
        for chunk_start, chunk_end in month_ranges(sales_start, sales_end):
            sales = fetch_json_with_retries(
                port,
                "/tickets/by-sell",
                {"from": fmt_ts(chunk_start), "to": fmt_ts(chunk_end)},
            )
            for sale in sales:
                if not active_sale(sale):
                    continue
                sid = str(sale.get("seance_id") or "")
                show_dt = target_shows.get(sid)
                if show_dt is None:
                    continue
                slot = f"{WEEKDAY[show_dt.isoweekday()]} {show_dt.strftime('%H:%M')}"
                slot_totals[slot]["revenue"] += int(str(sale.get("total") or "0"))
                slot_totals[slot]["tickets"] += 1
                slot_totals[slot]["seances"].add(sid)

        for slot, data in slot_totals.items():
            tickets = data["tickets"]
            if tickets < args.min_tickets:
                continue
            avg_price_rub = data["revenue"] / tickets / 100
            rows_out.append(
                {
                    "unit": unit,
                    "slot": slot,
                    "tickets": tickets,
                    "seances": len(data["seances"]),
                    "avg_ticket_price_rub": round(avg_price_rub, 2),
                }
            )

    rows_out.sort(key=lambda row: (str(row["unit"]), -float(row["avg_ticket_price_rub"]), -int(row["tickets"]), str(row["slot"])))
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["unit", "slot", "tickets", "seances", "avg_ticket_price_rub"],
        )
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"rows={len(rows_out)} output={output_path}")


if __name__ == "__main__":
    main()
