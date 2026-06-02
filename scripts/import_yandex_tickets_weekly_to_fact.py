#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import ssl
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, time as dt_time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "yandex_tickets_weekly_to_fact_import_report.csv"
ENV_MAIN = ROOT / ".env.yandex_tickets"
ENV_SPB = ROOT / ".env.yandex_tickets_spb"
SSL_CONTEXT = ssl._create_unverified_context()
MSK = timezone(timedelta(hours=3))

UNITS = {
    "b2c_moscow": {
        "env_path": ENV_MAIN,
        "login_key": "YANDEX_TICKETS_LOGIN",
        "password_key": "YANDEX_TICKETS_PASSWORD",
        "city_key": "YANDEX_TICKETS_CITY_ID",
        "required": True,
    },
    "b2c_spb": {
        "env_path": ENV_SPB,
        "login_key": "YANDEX_TICKETS_SPB_LOGIN",
        "password_key": "YANDEX_TICKETS_SPB_PASSWORD",
        "city_key": "YANDEX_TICKETS_SPB_CITY_ID",
        "required": False,
    },
}

PARTNER_MAP = {
    "b2c_moscow": {
        39320770: None,
        39320755: "яндекс.афиша",
        39992173: "афиша.ру",
        39996012: "кассир",
        39995745: "others",
        0: None,
    },
    "b2c_spb": {
        39801873: None,
        39801847: "яндекс.афиша",
        39993300: "афиша.ру",
        39996569: "кассир",
        0: None,
    },
}

SHOW_MAP = {
    "Ответ Гиппократа": "Ответ Гиппократа",
    "До свадьбы доживёт": "До свадьбы доживёт",
    "22'07": "22'07",
    "ВДОХ": "ВДОХ",
    "Иное место": "Иное место",
    "Поезд, Чехов, два орла": "Поезд, Чехов, два орла",
    "Загадка Амулета": "Загадка Амулета",
    "Судный день": "Судный день",
}

METRICS = ("Revenue", "Number of tickets", "Number of orders")


def period_bounds(last_full_week_start: date | None = None) -> tuple[date, date]:
    if last_full_week_start:
        return last_full_week_start, last_full_week_start + timedelta(days=6)
    today = datetime.now(MSK).date()
    current_week_start = today - timedelta(days=today.weekday())
    last_week_start = current_week_start - timedelta(days=7)
    return last_week_start, last_week_start + timedelta(days=6)


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip()
    return values


def make_auth(login: str, password: str) -> str:
    timestamp = str(int(time.time()))
    md5 = hashlib.md5(password.encode()).hexdigest()
    sha1 = hashlib.sha1((md5 + timestamp).encode()).hexdigest()
    return f"{login}:{sha1}:{timestamp}"


def tickets_post(params: dict[str, str]) -> dict:
    url = "https://api.tickets.yandex.net/api/crm/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_orders(login: str, password: str, city_id: str, week_start: date, week_end: date) -> list[dict]:
    auth = make_auth(login, password)
    params = {
        "action": "crm.order.list",
        "auth": auth,
        "city_id": city_id,
        "start_date": f"{week_start.isoformat()}T00:00:00+0300",
        "end_date": f"{week_end.isoformat()}T23:59:59+0300",
    }
    payload = tickets_post(params)
    if payload.get("status") != "0":
        raise RuntimeError(f"Yandex Tickets order.list error: {payload}")
    result = payload.get("result") or []
    orders: list[dict] = []
    for batch in result:
        if isinstance(batch, list):
            orders.extend(batch)
    filtered = []
    for order in orders:
        order_dt = datetime.strptime(order["order_date"], "%Y-%m-%d %H:%M:%S%z")
        if week_start <= order_dt.date() <= week_end:
            filtered.append(order)
    return filtered


def fetch_event_names(login: str, password: str, city_id: str, event_ids: list[int]) -> dict[int, str]:
    if not event_ids:
        return {}
    auth = make_auth(login, password)
    params = {
        "action": "crm.report.event",
        "auth": auth,
        "city_id": city_id,
        "event_ids": ",".join(str(eid) for eid in event_ids),
    }
    payload = tickets_post(params)
    if payload.get("status") != "0":
        raise RuntimeError(f"Yandex Tickets report.event error: {payload}")
    event_names: dict[int, str] = {}
    for item in payload.get("result") or []:
        try:
            event_id = int(item["event_id"])
        except Exception:
            continue
        event_names.setdefault(event_id, item.get("event_name") or "")
    return event_names


def canonical_show_name(raw_name: str) -> str | None:
    if not raw_name:
        return None
    if "сертификат" in raw_name.lower():
        return "сертификаты"
    return SHOW_MAP.get(raw_name, raw_name)


def sold_orders(orders: list[dict]) -> list[dict]:
    result = []
    for order in orders:
        if int(order.get("status") or 0) == 0:
            continue
        if int(order.get("is_returned") or 0) == 1:
            continue
        result.append(order)
    return result


def fetch_metric_ids(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("select metric_id, metric_name from metric_catalogue")
        return {metric_name: metric_id for metric_id, metric_name in cur.fetchall()}


def insert_rows(conn, rows: list[dict]) -> None:
    if not rows:
        return
    sql = """
    INSERT INTO fact_metric_observation (
        metric_id, rule_id, source_system, source_record_key, source_run_id,
        source_cell_a1, source_cell_url, business_unit, show_name, partner_name, channel_name,
        period_granularity, period_start, period_end, value_numeric, value_text, value_raw,
        currency_code, is_estimated, observed_at, loaded_at, payload
    )
    VALUES (
        %(metric_id)s, %(rule_id)s, %(source_system)s, %(source_record_key)s, %(source_run_id)s,
        %(source_cell_a1)s, %(source_cell_url)s, %(business_unit)s, %(show_name)s, %(partner_name)s, %(channel_name)s,
        %(period_granularity)s, %(period_start)s, %(period_end)s, %(value_numeric)s, %(value_text)s, %(value_raw)s,
        %(currency_code)s, %(is_estimated)s, %(observed_at)s, %(loaded_at)s, %(payload)s
    )
    ON CONFLICT (
        metric_id, source_system, business_unit, show_name_norm, partner_name_norm, channel_name_norm,
        period_granularity, period_start, period_end, source_record_key_norm
    )
    DO UPDATE SET
        source_run_id = EXCLUDED.source_run_id,
        value_numeric = EXCLUDED.value_numeric,
        value_text = EXCLUDED.value_text,
        value_raw = EXCLUDED.value_raw,
        currency_code = EXCLUDED.currency_code,
        is_estimated = EXCLUDED.is_estimated,
        observed_at = EXCLUDED.observed_at,
        loaded_at = EXCLUDED.loaded_at,
        payload = EXCLUDED.payload
    """
    with conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=200)


def delete_existing(conn, source_run_id: str, week_start: date) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM fact_metric_observation
            WHERE source_system='yandex_tickets'
              AND source_run_id=%s
              AND period_granularity='week'
              AND period_start=%s
            """,
            (source_run_id, week_start),
        )


def build_row(
    metric_id: int,
    source_record_key: str,
    source_run_id: str,
    business_unit: str,
    period_start: date,
    period_end: date,
    value_numeric: Decimal,
    payload: dict,
    *,
    show_name: str | None = None,
    partner_name: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    is_currency = payload["metric_name"] == "Revenue"
    return {
        "metric_id": metric_id,
        "rule_id": None,
        "source_system": "yandex_tickets",
        "source_record_key": source_record_key,
        "source_run_id": source_run_id,
        "source_cell_a1": None,
        "source_cell_url": None,
        "business_unit": business_unit,
        "show_name": show_name,
        "partner_name": partner_name,
        "channel_name": None,
        "period_granularity": "week",
        "period_start": period_start,
        "period_end": period_end,
        "value_numeric": value_numeric,
        "value_text": None,
        "value_raw": str(value_numeric),
        "currency_code": "RUB" if is_currency else None,
        "is_estimated": False,
        "observed_at": datetime.combine(period_end, dt_time(23, 59, 59), tzinfo=MSK).astimezone(timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--week-start", help="YYYY-MM-DD for the Monday of the week to load")
    parser.add_argument("--source-run-id", default="yandex_tickets_weekly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    week_start, week_end = period_bounds(date.fromisoformat(args.week_start) if args.week_start else None)
    conn = psycopg2.connect(args.database_url)
    metric_ids = fetch_metric_ids(conn)
    if args.delete_existing:
        with conn:
            delete_existing(conn, args.source_run_id, week_start)

    report_rows: list[dict] = []
    insert_rows_buffer: list[dict] = []

    for business_unit, meta in UNITS.items():
        env = read_env(meta["env_path"])
        login = env.get(meta["login_key"], "")
        password = env.get(meta["password_key"], "")
        city_id = env.get(meta["city_key"], "")
        if not (login and password and city_id):
            report_rows.append(
                {
                    "business_unit": business_unit,
                    "status": "skipped",
                    "reason": "missing_credentials",
                    "orders_seen": "",
                    "orders_sold": "",
                    "rows_inserted": "",
                }
            )
            continue

        raw_orders = fetch_orders(login, password, city_id, week_start, week_end)
        orders = sold_orders(raw_orders)
        event_ids = sorted({int(order["event_id"]) for order in orders if int(order.get("event_id") or 0) > 0})
        event_names = fetch_event_names(login, password, city_id, event_ids)

        totals_general = {metric: Decimal("0") for metric in METRICS}
        totals_show: dict[str, dict[str, Decimal]] = defaultdict(lambda: {metric: Decimal("0") for metric in METRICS})
        totals_partner: dict[str, dict[str, Decimal]] = defaultdict(lambda: {metric: Decimal("0") for metric in METRICS})

        for order in orders:
            revenue = Decimal(str(order.get("sum") or 0))
            tickets = Decimal(str(order.get("tickets_count") or 0))
            show_name = canonical_show_name(event_names.get(int(order.get("event_id") or 0), ""))
            agent_id = int(order.get("agent_id") or 0)
            partner_name = PARTNER_MAP.get(business_unit, {}).get(agent_id)
            if partner_name is None and agent_id not in PARTNER_MAP.get(business_unit, {}):
                partner_name = "others" if agent_id else None

            totals_general["Revenue"] += revenue
            totals_general["Number of tickets"] += tickets
            totals_general["Number of orders"] += Decimal("1")

            if show_name:
                totals_show[show_name]["Revenue"] += revenue
                totals_show[show_name]["Number of tickets"] += tickets
                totals_show[show_name]["Number of orders"] += Decimal("1")

            if partner_name:
                totals_partner[partner_name]["Revenue"] += revenue
                totals_partner[partner_name]["Number of tickets"] += tickets
                totals_partner[partner_name]["Number of orders"] += Decimal("1")

        for metric_name in METRICS:
            metric_id = metric_ids[metric_name]
            insert_rows_buffer.append(
                build_row(
                    metric_id,
                    f"{business_unit}:{metric_name}:general",
                    args.source_run_id,
                    business_unit,
                    week_start,
                    week_end,
                    totals_general[metric_name],
                    {
                        "loader": "import_yandex_tickets_weekly_to_fact",
                        "metric_name": metric_name,
                        "orders_count": len(orders),
                        "city_id": city_id,
                        "scope": "general",
                    },
                )
            )
            for show_name, metric_values in totals_show.items():
                insert_rows_buffer.append(
                    build_row(
                        metric_id,
                        f"{business_unit}:{metric_name}:show:{show_name}",
                        args.source_run_id,
                        business_unit,
                        week_start,
                        week_end,
                        metric_values[metric_name],
                        {
                            "loader": "import_yandex_tickets_weekly_to_fact",
                            "metric_name": metric_name,
                            "orders_count": len(orders),
                            "city_id": city_id,
                            "scope": "show",
                            "show_name": show_name,
                        },
                        show_name=show_name,
                    )
                )
            for partner_name, metric_values in totals_partner.items():
                insert_rows_buffer.append(
                    build_row(
                        metric_id,
                        f"{business_unit}:{metric_name}:partner:{partner_name}",
                        args.source_run_id,
                        business_unit,
                        week_start,
                        week_end,
                        metric_values[metric_name],
                        {
                            "loader": "import_yandex_tickets_weekly_to_fact",
                            "metric_name": metric_name,
                            "orders_count": len(orders),
                            "city_id": city_id,
                            "scope": "partner",
                            "partner_name": partner_name,
                        },
                        partner_name=partner_name,
                    )
                )

        report_rows.append(
            {
                "business_unit": business_unit,
                "status": "inserted",
                "reason": "",
                "orders_seen": str(len(raw_orders)),
                "orders_sold": str(len(orders)),
                "rows_inserted": str(3 + 3 * len(totals_show) + 3 * len(totals_partner)),
            }
        )

    with conn:
        insert_rows(conn, insert_rows_buffer)
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["business_unit", "status", "reason", "orders_seen", "orders_sold", "rows_inserted"],
        )
        writer.writeheader()
        writer.writerows(report_rows)

    inserted_rows = len(insert_rows_buffer)
    skipped_units = sum(1 for row in report_rows if row["status"] == "skipped")
    print(f"inserted={inserted_rows} skipped_units={skipped_units} report={report_path}")


if __name__ == "__main__":
    main()
