#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import Json

from import_erp_weekly_to_fact import (
    ERP_BASE,
    OWN_SITE_AGENT_IDS,
    PARTNER_BY_AGENT,
    SHOW_CANON,
    SHOW_LOOKUP_FORWARD_DAYS,
    UNITS,
    fetch_json,
    fetch_metric_ids,
    fmt_ts,
    insert_rows,
    is_active_sale,
)
from monthly_kpi_period_utils import month_bounds, sales_show_lookup_bounds, start_end_datetimes


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "erp_monthly_to_fact_import_report.csv"


def delete_existing(conn, source_run_id: str, period_start: date) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM fact_metric_observation
            WHERE source_system='erp'
              AND source_run_id=%s
              AND period_granularity='month'
              AND period_start=%s
            """,
            (source_run_id, period_start),
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
        "period_granularity": "month",
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
    parser.add_argument("--month-start", required=True)
    parser.add_argument("--source-run-id", default="erp_monthly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    period_start, period_end = month_bounds(date.fromisoformat(args.month_start))
    dt_from, dt_to = start_end_datetimes(period_start, period_end)
    sales_lookup_from, sales_lookup_to = sales_show_lookup_bounds(period_start, period_end, SHOW_LOOKUP_FORWARD_DAYS)

    conn = psycopg2.connect(args.database_url)
    metric_ids = fetch_metric_ids(conn)
    report_rows: list[dict] = []
    insert_payload: list[dict] = []

    for unit, meta in UNITS.items():
        tickets = fetch_json(meta["port"], "/tickets/by-sell", {"from": fmt_ts(dt_from), "to": fmt_ts(dt_to)})
        shows = fetch_json(meta["port"], "/shows/get", {"from": fmt_ts(dt_from), "to": fmt_ts(dt_to)})
        sales_lookup_shows = fetch_json(meta["port"], "/shows/get", {"from": fmt_ts(sales_lookup_from), "to": fmt_ts(sales_lookup_to)})

        shows_by_show_id = {str(row.get("show_id")): row for row in shows if row.get("show_id") is not None}
        sales_lookup_shows_by_show_id = {str(row.get("show_id")): row for row in sales_lookup_shows if row.get("show_id") is not None}
        positive_tickets = [row for row in tickets if is_active_sale(row)]
        paid_orders = {str(row.get("order_id")) for row in positive_tickets if str(row.get("order_id") or "0") not in {"", "0"}}

        own_site_agent_id = OWN_SITE_AGENT_IDS.get(unit)
        own_site_tickets = [row for row in positive_tickets if str(row.get("agent_id") or "") == own_site_agent_id]
        own_site_orders = {str(row.get("order_id")) for row in own_site_tickets if str(row.get("order_id") or "0") not in {"", "0"}}

        general_rows = [
            ("Number of tickets", Decimal(len(positive_tickets)), str(len(positive_tickets))),
            ("Number of orders", Decimal(len(paid_orders)), str(len(paid_orders))),
            ("Revenue", Decimal(sum(int(str(row.get("total") or "0")) for row in positive_tickets)) / Decimal(100), ""),
            ("Website orders", Decimal(len(own_site_orders)), str(len(own_site_orders))),
        ]
        for metric_name, value, raw in general_rows:
            insert_payload.append(
                base_row(
                    metric_ids[metric_name],
                    f"{unit}:{metric_name}:general:{period_start.isoformat()}",
                    args.source_run_id,
                    unit,
                    period_start,
                    period_end,
                    value,
                    raw or str(value),
                    {"loader": "import_erp_monthly_to_fact", "unit": unit, "metric_name": metric_name, "scope": "general", "sales_filter": "erp_status_non_zero_and_positive_total"},
                    currency_code="RUB" if metric_name == "Revenue" else None,
                )
            )
            report_rows.append({"unit": unit, "metric_name": metric_name, "scope": "general", "status": "inserted", "value": str(value), "reason": ""})

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
                        metric_ids[metric_name],
                        f"{unit}:{metric_name}:show:{show_name}:{period_start.isoformat()}",
                        args.source_run_id,
                        unit,
                        period_start,
                        period_end,
                        value,
                        str(value),
                        {
                            "loader": "import_erp_monthly_to_fact",
                            "unit": unit,
                            "metric_name": metric_name,
                            "scope": "show",
                            "show_name": show_name,
                            "sales_filter": "erp_status_non_zero_and_positive_total",
                            "sales_show_lookup_forward_days": SHOW_LOOKUP_FORWARD_DAYS,
                        },
                        show_name=show_name,
                        currency_code=currency,
                    )
                )
                report_rows.append({"unit": unit, "metric_name": metric_name, "scope": f"show:{show_name}", "status": "inserted", "value": str(value), "reason": ""})

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
                        metric_ids[metric_name],
                        f"{unit}:{metric_name}:partner:{partner_name}:{period_start.isoformat()}",
                        args.source_run_id,
                        unit,
                        period_start,
                        period_end,
                        value,
                        str(value),
                        {"loader": "import_erp_monthly_to_fact", "unit": unit, "metric_name": metric_name, "scope": "partner", "partner_name": partner_name, "sales_filter": "erp_status_non_zero_and_positive_total"},
                        partner_name=partner_name,
                        currency_code=currency,
                    )
                )
                report_rows.append({"unit": unit, "metric_name": metric_name, "scope": f"partner:{partner_name}", "status": "inserted", "value": str(value), "reason": ""})

        tickets_by_show_partner = defaultdict(list)
        for row in positive_tickets:
            agent_id = str(row.get("agent_id"))
            partner_name = partner_map.get(agent_id)
            if not partner_name:
                continue
            show = sales_lookup_shows_by_show_id.get(str(row.get("seance_id")))
            if not show:
                continue
            show_name = SHOW_CANON.get(show.get("event_title"))
            if not show_name:
                continue
            tickets_by_show_partner[(show_name, partner_name)].append(row)

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
                        metric_ids[metric_name],
                        f"{unit}:{metric_name}:show_partner:{show_name}:{partner_name}:{period_start.isoformat()}",
                        args.source_run_id,
                        unit,
                        period_start,
                        period_end,
                        value,
                        str(value),
                        {"loader": "import_erp_monthly_to_fact", "unit": unit, "metric_name": metric_name, "scope": "show_partner", "show_name": show_name, "partner_name": partner_name, "sales_filter": "erp_status_non_zero_and_positive_total"},
                        show_name=show_name,
                        partner_name=partner_name,
                        currency_code=currency,
                    )
                )
                report_rows.append({"unit": unit, "metric_name": metric_name, "scope": f"show_partner:{show_name}:{partner_name}", "status": "inserted", "value": str(value), "reason": ""})

        shows_by_name = defaultdict(list)
        for row in shows_by_show_id.values():
            canonical_show = SHOW_CANON.get(row.get("event_title"))
            if canonical_show:
                shows_by_name[canonical_show].append(row)

        for show_name, rows in shows_by_name.items():
            shows_count = Decimal(len(rows))
            cancelled_count = Decimal(sum(1 for row in rows if int(str(row.get("status") or "1")) == 0))
            visitors_count = Decimal(sum(int(str(row.get("visitors") or "0")) for row in rows))
            for metric_name, value in [
                ("Number of shows", shows_count),
                ("Number of shows cancelled", cancelled_count),
                ("Number of show visitors", visitors_count),
            ]:
                insert_payload.append(
                    base_row(
                        metric_ids[metric_name],
                        f"{unit}:{metric_name}:show:{show_name}:{period_start.isoformat()}",
                        args.source_run_id,
                        unit,
                        period_start,
                        period_end,
                        value,
                        str(value),
                        {"loader": "import_erp_monthly_to_fact", "unit": unit, "metric_name": metric_name, "scope": "show", "show_name": show_name},
                        show_name=show_name,
                    )
                )
                report_rows.append({"unit": unit, "metric_name": metric_name, "scope": f"show:{show_name}", "status": "inserted", "value": str(value), "reason": ""})

    if args.delete_existing:
        with conn:
            delete_existing(conn, args.source_run_id, period_start)
    with conn:
        insert_rows(conn, insert_payload)
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["unit", "metric_name", "scope", "status", "value", "reason"])
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"period={period_start}..{period_end} inserted={len(insert_payload)} report={report_path}")


if __name__ == "__main__":
    main()
