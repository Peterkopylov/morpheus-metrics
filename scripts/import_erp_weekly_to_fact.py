#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import ssl
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib import request

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "erp_weekly_to_fact_import_report.csv"
SSL_CONTEXT = ssl._create_unverified_context()
MSK = timezone(timedelta(hours=3))


UNITS = {
    "b2c_moscow": {"port": 45010, "city": "Moscow"},
    "b2c_spb": {"port": 45011, "city": "SPB"},
}

SHOW_CANON = {
    "Ответ Гиппократа": "Ответ Гиппократа",
    "До свадьбы доживёт": "До свадьбы доживёт",
    "22'07": "22'07",
    "ВДОХ": "ВДОХ",
    "Иное место": "Иное место",
    "Поезд, Чехов, два орла": "Поезд, Чехов, два орла",
    "Загадка амулета": "Загадка Амулета",
    "Загадка Амулета": "Загадка Амулета",
    "Судный день": "Судный день",
}

# Working partner mapping from ERP `agent_id` to canonical partner names.
# `None` means "own site/widget" and should stay out of partner-split rows.
PARTNER_BY_AGENT = {
    "b2c_moscow": {
        "39320770": None,  # site/widget, not partner
        "39320755": "яндекс.афиша",
        "39992173": "афиша.ру",
        "39996012": "кассир",
        "39995745": "others",
    },
    "b2c_spb": {
        "39801873": None,  # site/widget, supported by exact order-count match vs manual site row
        "39801847": "яндекс.афиша",  # `order@afisha.yandex.ru`
        "39993300": "афиша.ру",  # `Компания Афиша`, still best treated as afisha.ru / T-bank bucket
        "39996569": "кассир",  # `null@kassir.ru`
    },
}

OWN_SITE_AGENT_IDS = {
    "b2c_moscow": "39320770",
    "b2c_spb": "39801873",
}

ERP_BASE = "https://morpheus-server.ru:{port}{path}"
SHOW_LOOKUP_FORWARD_DAYS = 180


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


def is_active_sale(row: dict) -> bool:
    # ERP `tickets/by-sell` now uses `status`: 0 means cancellation, non-zero means active.
    if int(str(row.get("status") or "0")) == 0:
        return False
    return int(str(row.get("total") or "0")) > 0


def period_bounds(last_full_week_start: Optional[date] = None) -> tuple[date, date]:
    if last_full_week_start:
        return last_full_week_start, last_full_week_start + timedelta(days=6)
    today = datetime.now(MSK).date()
    current_week_start = today - timedelta(days=today.weekday())
    last_week_start = current_week_start - timedelta(days=7)
    return last_week_start, last_week_start + timedelta(days=6)


def start_end_datetimes(week_start: date, week_end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(week_start, time.min, tzinfo=MSK),
        datetime.combine(week_end, time(23, 59, 59), tzinfo=MSK),
    )


def sales_show_lookup_bounds(week_start: date, week_end: date) -> tuple[datetime, datetime]:
    # Ticket sales are grouped by sell date, but the performance can happen weeks later.
    # We expand the show lookup window so show-level sales attribution doesn't lose future seances.
    return (
        datetime.combine(week_start, time.min, tzinfo=MSK),
        datetime.combine(week_end + timedelta(days=SHOW_LOOKUP_FORWARD_DAYS), time(23, 59, 59), tzinfo=MSK),
    )


def fetch_metric_ids(conn) -> Dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("select metric_id, metric_name from metric_catalogue")
        return {metric_name: metric_id for metric_id, metric_name in cur.fetchall()}


def insert_rows(conn, rows: list[dict]) -> None:
    if not rows:
        return
    sql = """
    INSERT INTO fact_metric_observation (
        metric_id,
        rule_id,
        source_system,
        source_record_key,
        source_run_id,
        source_cell_a1,
        source_cell_url,
        business_unit,
        show_name,
        partner_name,
        channel_name,
        period_granularity,
        period_start,
        period_end,
        value_numeric,
        value_text,
        value_raw,
        currency_code,
        is_estimated,
        observed_at,
        loaded_at,
        payload
    )
    VALUES (
        %(metric_id)s,
        %(rule_id)s,
        %(source_system)s,
        %(source_record_key)s,
        %(source_run_id)s,
        %(source_cell_a1)s,
        %(source_cell_url)s,
        %(business_unit)s,
        %(show_name)s,
        %(partner_name)s,
        %(channel_name)s,
        %(period_granularity)s,
        %(period_start)s,
        %(period_end)s,
        %(value_numeric)s,
        %(value_text)s,
        %(value_raw)s,
        %(currency_code)s,
        %(is_estimated)s,
        %(observed_at)s,
        %(loaded_at)s,
        %(payload)s
    )
    ON CONFLICT (
        metric_id,
        source_system,
        business_unit,
        show_name_norm,
        partner_name_norm,
        channel_name_norm,
        period_granularity,
        period_start,
        period_end,
        source_record_key_norm
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
            WHERE source_system='erp'
              AND source_run_id=%s
              AND period_granularity='week'
              AND period_start=%s
            """,
            (source_run_id, week_start),
        )


def base_row(
    metric_id: int,
    source_record_key: str,
    source_run_id: str,
    business_unit: str,
    period_start: date,
    period_end: date,
    value_numeric: Decimal,
    value_raw: str,
    payload: dict,
    show_name: Optional[str] = None,
    partner_name: Optional[str] = None,
    channel_name: Optional[str] = None,
    currency_code: Optional[str] = None,
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "metric_id": metric_id,
        "rule_id": None,
        "source_system": "erp",
        "source_record_key": source_record_key,
        "source_run_id": source_run_id,
        "source_cell_a1": None,
        "source_cell_url": None,
        "business_unit": business_unit,
        "show_name": show_name,
        "partner_name": partner_name,
        "channel_name": channel_name,
        "period_granularity": "week",
        "period_start": period_start,
        "period_end": period_end,
        "value_numeric": value_numeric,
        "value_text": None,
        "value_raw": value_raw,
        "currency_code": currency_code,
        "is_estimated": False,
        "observed_at": datetime.combine(period_end, time.min, tzinfo=timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--week-start", help="YYYY-MM-DD for the Monday of the week to load")
    parser.add_argument("--source-run-id", default="erp_weekly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    week_start = date.fromisoformat(args.week_start) if args.week_start else None
    period_start, period_end = period_bounds(week_start)
    dt_from, dt_to = start_end_datetimes(period_start, period_end)
    sales_lookup_from, sales_lookup_to = sales_show_lookup_bounds(period_start, period_end)

    conn = psycopg2.connect(args.database_url)
    metric_ids = fetch_metric_ids(conn)
    report_rows: list[dict] = []
    insert_payload: list[dict] = []

    for unit, meta in UNITS.items():
        tickets = fetch_json(meta["port"], "/tickets/by-sell", {"from": fmt_ts(dt_from), "to": fmt_ts(dt_to)})
        shows = fetch_json(meta["port"], "/shows/get", {"from": fmt_ts(dt_from), "to": fmt_ts(dt_to)})
        sales_lookup_shows = fetch_json(
            meta["port"],
            "/shows/get",
            {"from": fmt_ts(sales_lookup_from), "to": fmt_ts(sales_lookup_to)},
        )

        shows_by_show_id = {str(row.get("show_id")): row for row in shows if row.get("show_id") is not None}
        sales_lookup_shows_by_show_id = {
            str(row.get("show_id")): row for row in sales_lookup_shows if row.get("show_id") is not None
        }
        positive_tickets = [row for row in tickets if is_active_sale(row)]
        paid_orders = {str(row.get("order_id")) for row in positive_tickets if str(row.get("order_id") or "0") not in {"", "0"}}

        own_site_agent_id = OWN_SITE_AGENT_IDS.get(unit)
        own_site_tickets = [row for row in positive_tickets if str(row.get("agent_id") or "") == own_site_agent_id]
        own_site_orders = {
            str(row.get("order_id"))
            for row in own_site_tickets
            if str(row.get("order_id") or "0") not in {"", "0"}
        }

        # General metrics
        general_rows = [
            ("Number of tickets", Decimal(len(positive_tickets)), str(len(positive_tickets))),
            ("Number of orders", Decimal(len(paid_orders)), str(len(paid_orders))),
            ("Revenue", Decimal(sum(int(str(row.get("total") or "0")) for row in positive_tickets)) / Decimal(100), ""),
            ("Website orders", Decimal(len(own_site_orders)), str(len(own_site_orders))),
        ]
        for metric_name, value, raw in general_rows:
            insert_payload.append(
                base_row(
                    metric_id=metric_ids[metric_name],
                    source_record_key=f"{unit}:{metric_name}:general:{period_start.isoformat()}",
                    source_run_id=args.source_run_id,
                    business_unit=unit,
                    period_start=period_start,
                    period_end=period_end,
                    value_numeric=value,
                    value_raw=raw or str(value),
                    payload={"loader": "import_erp_weekly_to_fact", "unit": unit, "metric_name": metric_name, "scope": "general", "sales_filter": "erp_status_non_zero_and_positive_total"},
                    currency_code="RUB" if metric_name == "Revenue" else None,
                )
            )
            report_rows.append({"unit": unit, "metric_name": metric_name, "scope": "general", "status": "inserted", "value": str(value), "reason": ""})

        # Show-level tickets / orders / revenue
        tickets_by_show = defaultdict(list)
        missing_show_join = 0
        for row in positive_tickets:
            show = sales_lookup_shows_by_show_id.get(str(row.get("seance_id")))
            if not show:
                missing_show_join += 1
                continue
            canonical_show = SHOW_CANON.get(show.get("event_title"))
            if not canonical_show:
                report_rows.append({"unit": unit, "metric_name": "show_join", "scope": show.get("event_title"), "status": "skipped", "value": "", "reason": "unknown_show_name"})
                continue
            tickets_by_show[canonical_show].append((row, show))

        if missing_show_join:
            report_rows.append({"unit": unit, "metric_name": "show_join", "scope": "", "status": "skipped", "value": str(missing_show_join), "reason": "missing_show_join"})

        for show_name, rows in tickets_by_show.items():
            value_tickets = Decimal(len(rows))
            value_orders = Decimal(len({str(t[0].get('order_id')) for t in rows if str(t[0].get('order_id') or '0') not in {'', '0'}}))
            value_revenue = Decimal(sum(int(str(t[0].get("total") or "0")) for t in rows)) / Decimal(100)
            for metric_name, value, currency in [
                ("Number of tickets", value_tickets, None),
                ("Number of orders", value_orders, None),
                ("Revenue", value_revenue, "RUB"),
            ]:
                insert_payload.append(
                    base_row(
                        metric_id=metric_ids[metric_name],
                        source_record_key=f"{unit}:{metric_name}:show:{show_name}:{period_start.isoformat()}",
                        source_run_id=args.source_run_id,
                        business_unit=unit,
                        show_name=show_name,
                        period_start=period_start,
                        period_end=period_end,
                        value_numeric=value,
                        value_raw=str(value),
                        payload={
                            "loader": "import_erp_weekly_to_fact",
                            "unit": unit,
                            "metric_name": metric_name,
                            "scope": "show",
                            "show_name": show_name,
                            "sales_filter": "erp_status_non_zero_and_positive_total",
                            "sales_show_lookup_forward_days": SHOW_LOOKUP_FORWARD_DAYS,
                        },
                        currency_code=currency,
                    )
                )
                report_rows.append({"unit": unit, "metric_name": metric_name, "scope": f"show:{show_name}", "status": "inserted", "value": str(value), "reason": ""})

        # Partner-level tickets / orders only when mapping is known.
        partner_map = PARTNER_BY_AGENT.get(unit, {})
        partner_ticket_groups = defaultdict(list)
        for row in positive_tickets:
            agent_id = str(row.get("agent_id"))
            if agent_id not in partner_map:
                continue
            partner_name = partner_map[agent_id]
            if not partner_name:
                continue
            partner_ticket_groups[partner_name].append(row)

        for partner_name, rows in partner_ticket_groups.items():
            value_tickets = Decimal(len(rows))
            value_orders = Decimal(len({str(r.get('order_id')) for r in rows if str(r.get('order_id') or '0') not in {'', '0'}}))
            value_revenue = Decimal(sum(int(str(r.get("total") or "0")) for r in rows)) / Decimal(100)
            for metric_name, value, currency in [
                ("Number of tickets", value_tickets, None),
                ("Number of orders", value_orders, None),
                ("Revenue", value_revenue, "RUB"),
            ]:
                insert_payload.append(
                    base_row(
                        metric_id=metric_ids[metric_name],
                        source_record_key=f"{unit}:{metric_name}:partner:{partner_name}:{period_start.isoformat()}",
                        source_run_id=args.source_run_id,
                        business_unit=unit,
                        partner_name=partner_name,
                        period_start=period_start,
                        period_end=period_end,
                        value_numeric=value,
                        value_raw=str(value),
                        payload={"loader": "import_erp_weekly_to_fact", "unit": unit, "metric_name": metric_name, "scope": "partner", "partner_name": partner_name, "sales_filter": "erp_status_non_zero_and_positive_total"},
                        currency_code=currency,
                    )
                )
                report_rows.append({"unit": unit, "metric_name": metric_name, "scope": f"partner:{partner_name}", "status": "inserted", "value": str(value), "reason": ""})

        # Show+partner rows are needed for downstream partner commission metrics.
        tickets_by_show_partner = defaultdict(list)
        for row in positive_tickets:
            agent_id = str(row.get("agent_id"))
            partner_name = partner_map.get(agent_id)
            if not partner_name:
                continue
            show = sales_lookup_shows_by_show_id.get(str(row.get("seance_id")))
            if not show:
                continue
            canonical_show = SHOW_CANON.get(show.get("event_title"))
            if not canonical_show:
                continue
            tickets_by_show_partner[(canonical_show, partner_name)].append(row)

        for (show_name, partner_name), rows in tickets_by_show_partner.items():
            value_tickets = Decimal(len(rows))
            value_orders = Decimal(len({str(r.get('order_id')) for r in rows if str(r.get('order_id') or '0') not in {'', '0'}}))
            value_revenue = Decimal(sum(int(str(r.get("total") or "0")) for r in rows)) / Decimal(100)
            for metric_name, value, currency in [
                ("Number of tickets", value_tickets, None),
                ("Number of orders", value_orders, None),
                ("Revenue", value_revenue, "RUB"),
            ]:
                insert_payload.append(
                    base_row(
                        metric_id=metric_ids[metric_name],
                        source_record_key=f"{unit}:{metric_name}:show_partner:{show_name}:{partner_name}:{period_start.isoformat()}",
                        source_run_id=args.source_run_id,
                        business_unit=unit,
                        show_name=show_name,
                        partner_name=partner_name,
                        period_start=period_start,
                        period_end=period_end,
                        value_numeric=value,
                        value_raw=str(value),
                        payload={
                            "loader": "import_erp_weekly_to_fact",
                            "unit": unit,
                            "metric_name": metric_name,
                            "scope": "show_partner",
                            "show_name": show_name,
                            "partner_name": partner_name,
                            "sales_filter": "erp_status_non_zero_and_positive_total",
                            "sales_show_lookup_forward_days": SHOW_LOOKUP_FORWARD_DAYS,
                        },
                        currency_code=currency,
                    )
                )
                report_rows.append(
                    {
                        "unit": unit,
                        "metric_name": metric_name,
                        "scope": f"show:{show_name}|partner:{partner_name}",
                        "status": "inserted",
                        "value": str(value),
                        "reason": "",
                    }
                )

        # Shows / cancelled / visitors by show
        by_show_non_cancelled = defaultdict(int)
        by_show_cancelled = defaultdict(int)
        by_show_visitors = defaultdict(Decimal)
        for row in shows:
            canonical_show = SHOW_CANON.get(row.get("event_title"))
            if not canonical_show:
                report_rows.append({"unit": unit, "metric_name": "shows/get", "scope": row.get("event_title") or "", "status": "skipped", "value": "", "reason": "unknown_show_name"})
                continue
            cancelled = bool(row.get("cancelled"))
            guests = Decimal(int(str(row.get("guests") or "0")))
            if cancelled:
                by_show_cancelled[canonical_show] += 1
            else:
                by_show_non_cancelled[canonical_show] += 1
                by_show_visitors[canonical_show] += guests

        for show_name, value in by_show_non_cancelled.items():
            insert_payload.append(
                base_row(
                    metric_id=metric_ids["Number of shows"],
                    source_record_key=f"{unit}:Number of shows:show:{show_name}:{period_start.isoformat()}",
                    source_run_id=args.source_run_id,
                    business_unit=unit,
                    show_name=show_name,
                    period_start=period_start,
                    period_end=period_end,
                    value_numeric=Decimal(value),
                    value_raw=str(value),
                    payload={"loader": "import_erp_weekly_to_fact", "unit": unit, "metric_name": "Number of shows", "scope": "show", "show_name": show_name},
                )
            )
            report_rows.append({"unit": unit, "metric_name": "Number of shows", "scope": f"show:{show_name}", "status": "inserted", "value": str(value), "reason": ""})

        for show_name, value in by_show_cancelled.items():
            insert_payload.append(
                base_row(
                    metric_id=metric_ids["Number of shows cancelled"],
                    source_record_key=f"{unit}:Number of shows cancelled:show:{show_name}:{period_start.isoformat()}",
                    source_run_id=args.source_run_id,
                    business_unit=unit,
                    show_name=show_name,
                    period_start=period_start,
                    period_end=period_end,
                    value_numeric=Decimal(value),
                    value_raw=str(value),
                    payload={"loader": "import_erp_weekly_to_fact", "unit": unit, "metric_name": "Number of shows cancelled", "scope": "show", "show_name": show_name},
                )
            )
            report_rows.append({"unit": unit, "metric_name": "Number of shows cancelled", "scope": f"show:{show_name}", "status": "inserted", "value": str(value), "reason": ""})

        for show_name, value in by_show_visitors.items():
            insert_payload.append(
                base_row(
                    metric_id=metric_ids["Number of show visitors"],
                    source_record_key=f"{unit}:Number of show visitors:show:{show_name}:{period_start.isoformat()}",
                    source_run_id=args.source_run_id,
                    business_unit=unit,
                    show_name=show_name,
                    period_start=period_start,
                    period_end=period_end,
                    value_numeric=value,
                    value_raw=str(value),
                    payload={"loader": "import_erp_weekly_to_fact", "unit": unit, "metric_name": "Number of show visitors", "scope": "show", "show_name": show_name},
                )
            )
            report_rows.append({"unit": unit, "metric_name": "Number of show visitors", "scope": f"show:{show_name}", "status": "inserted", "value": str(value), "reason": ""})

        # Direct-source-share and survey ratings are not available directly yet.
        report_rows.append({"unit": unit, "metric_name": "Source share", "scope": "", "status": "skipped", "value": "", "reason": "direct_erp_source_share_not_available"})
        report_rows.append({"unit": unit, "metric_name": "Quality - Internal", "scope": "survey", "status": "skipped", "value": "", "reason": "survey_endpoints_not_working"})

    if args.delete_existing:
        with conn:
            delete_existing(conn, args.source_run_id, period_start)
    with conn:
        insert_rows(conn, insert_payload)
    conn.close()

    import csv
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["unit", "metric_name", "scope", "status", "value", "reason"])
        writer.writeheader()
        writer.writerows(report_rows)

    inserted = sum(1 for r in report_rows if r["status"] == "inserted")
    skipped = sum(1 for r in report_rows if r["status"] == "skipped")
    print(f"period={period_start}..{period_end} inserted={inserted} skipped={skipped} report={report_path}")


if __name__ == "__main__":
    main()
