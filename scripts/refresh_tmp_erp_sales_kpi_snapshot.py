#!/usr/bin/env python3
import argparse
import json
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Tuple
from urllib import request

import psycopg2


MSK = timezone(timedelta(hours=3))
ERP_BASE = "https://morpheus-server.ru:{port}/tickets/by-sell"
SSL_CONTEXT = ssl._create_unverified_context()
ENV_PATH = "/opt/analytics/parser/.env"
UNITS = {
    "b2c_moscow": {"label": "Москва", "port": 45010, "weekly_metric_name": "Поступления на счет - B2C"},
    "b2c_spb": {"label": "СПб", "port": 45011, "weekly_metric_name": "Поступления на счет"},
}

CREATE_SQL = """
DROP TABLE IF EXISTS tmp_erp_sales_kpi_snapshot;

CREATE TABLE tmp_erp_sales_kpi_snapshot (
    id BIGSERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    as_of_msk TIMESTAMPTZ NOT NULL,
    unit TEXT NOT NULL,
    unit_label TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    display_order INTEGER NOT NULL,
    current_period_start TIMESTAMPTZ NOT NULL,
    current_period_end TIMESTAMPTZ NOT NULL,
    current_period_label TEXT NOT NULL,
    current_value_rub NUMERIC(18,2) NOT NULL,
    year_ago_period_start TIMESTAMPTZ,
    year_ago_period_end TIMESTAMPTZ,
    year_ago_period_label TEXT,
    year_ago_value_rub NUMERIC(18,2),
    is_temporary BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_tmp_erp_sales_kpi_snapshot_unit_snapshot
    ON tmp_erp_sales_kpi_snapshot(unit, snapshot_at DESC);

COMMENT ON TABLE tmp_erp_sales_kpi_snapshot IS
    'Temporary prototype table for ERP sales KPI dashboard. Safe to replace or drop after proper warehouse layer is built.';
"""


@dataclass
class Period:
    start: datetime
    end: datetime
    label: str
    day_count: int


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S+03:00")


def fmt_label(start: datetime, end: datetime) -> str:
    return f"{start.astimezone(MSK):%d.%m.%Y} - {end.astimezone(MSK):%d.%m.%Y}"


def fetch_sales_rows(port: int, period: Period) -> List[dict]:
    body = json.dumps({"from": fmt_ts(period.start), "to": fmt_ts(period.end)}).encode("utf-8")
    req = request.Request(
        ERP_BASE.format(port=port),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Temporary prototype: the ERP endpoint currently presents a cert chain
    # that does not validate cleanly in our local Python runtime.
    with request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


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


def sales_total_rub(rows: Iterable[dict]) -> float:
    total_kopecks = 0
    for row in rows:
        try:
            total = int(str(row.get("total", "0")))
        except ValueError:
            total = 0
        if total > 0:
            total_kopecks += total
    return round(total_kopecks / 100.0, 2)


def build_periods(as_of: datetime) -> Dict[str, Tuple[Period, Period]]:
    current_week_start = as_of.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=as_of.weekday())
    current_week = Period(
        start=current_week_start,
        end=as_of,
        label=fmt_label(current_week_start, as_of),
        day_count=(as_of.date() - current_week_start.date()).days + 1,
    )
    year_ago_week_start = current_week_start - timedelta(days=364)
    year_ago_week = Period(
        start=year_ago_week_start,
        end=year_ago_week_start + (as_of - current_week_start),
        label=fmt_label(year_ago_week_start, year_ago_week_start + (as_of - current_week_start)),
        day_count=current_week.day_count,
    )

    trailing_3m_start = (as_of - timedelta(days=89)).replace(hour=0, minute=0, second=0, microsecond=0)
    trailing_3m = Period(
        start=trailing_3m_start,
        end=as_of,
        label=fmt_label(trailing_3m_start, as_of),
        day_count=(as_of.date() - trailing_3m_start.date()).days + 1,
    )
    year_ago_3m_start = trailing_3m_start - timedelta(days=364)
    year_ago_3m = Period(
        start=year_ago_3m_start,
        end=year_ago_3m_start + (as_of - trailing_3m_start),
        label=fmt_label(year_ago_3m_start, year_ago_3m_start + (as_of - trailing_3m_start)),
        day_count=trailing_3m.day_count,
    )

    return {
        "sales_this_week": (current_week, year_ago_week),
        "avg_sales_per_day_this_week": (current_week, year_ago_week),
        "avg_sales_per_day_last_3m": (trailing_3m, year_ago_3m),
    }


def weekly_base_year_ago(conn, unit: str, weekly_metric_name: str, current_week_start: datetime) -> Dict[str, object]:
    exact_week_start = current_week_start - timedelta(days=364)
    exact_week_end = exact_week_start + timedelta(days=6)
    trailing_12w_start = exact_week_start - timedelta(weeks=11)
    trailing_12w_end = exact_week_end

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT period_start::date, value::numeric
            FROM fact_metrics
            WHERE aggregation_level = 'week'
              AND unit = %s
              AND metric_name = %s
              AND period_start::date BETWEEN %s::date AND %s::date
            ORDER BY period_start::date
            """,
            (unit, weekly_metric_name, trailing_12w_start.date(), trailing_12w_end.date()),
        )
        rows = cur.fetchall()

    if not rows:
        return {
            "last_week_start": None,
            "last_week_end": None,
            "last_week_label": None,
            "last_week_value": None,
            "avg_12w_per_day": None,
        }

    last_week_row = next((row for row in rows if row[0] == exact_week_start.date()), None)
    if last_week_row is None:
        return {
            "last_week_start": None,
            "last_week_end": None,
            "last_week_label": None,
            "last_week_value": None,
            "avg_12w_per_day": None,
        }

    last_week_start = datetime.combine(exact_week_start.date(), datetime.min.time(), tzinfo=MSK)
    last_week_end = exact_week_end
    total_12w = sum(float(row[1]) for row in rows)
    return {
        "last_week_start": last_week_start,
        "last_week_end": last_week_end,
        "last_week_label": fmt_label(last_week_start, last_week_end),
        "last_week_value": round(float(last_week_row[1]), 2),
        "avg_12w_per_day": round(total_12w / (7 * 12), 2),
    }


def current_rows(as_of: datetime, conn) -> List[Tuple]:
    periods = build_periods(as_of)
    output = []
    metric_defs = [
        ("sales_this_week", "Продажи на этой неделе", 1),
        ("avg_sales_per_day_this_week", "Средние продажи в день на этой неделе", 2),
        ("avg_sales_per_day_last_3m", "Средние продажи в день за последние 3 месяца", 3),
    ]

    for unit, cfg in UNITS.items():
        year_ago_from_weekly = weekly_base_year_ago(
            conn,
            unit,
            cfg["weekly_metric_name"],
            periods["sales_this_week"][0].start,
        )
        current_week_rows = fetch_sales_rows(cfg["port"], periods["sales_this_week"][0])
        current_3m_rows = fetch_sales_rows(cfg["port"], periods["avg_sales_per_day_last_3m"][0])

        current_week_total = sales_total_rub(current_week_rows)
        current_3m_total = sales_total_rub(current_3m_rows)

        metric_values = {
            "sales_this_week": (
                current_week_total,
                year_ago_from_weekly["last_week_value"],
                periods["sales_this_week"][0],
                Period(
                    start=year_ago_from_weekly["last_week_start"],
                    end=year_ago_from_weekly["last_week_end"],
                    label=year_ago_from_weekly["last_week_label"],
                    day_count=7,
                ) if year_ago_from_weekly["last_week_start"] else None,
            ),
            "avg_sales_per_day_this_week": (
                round(current_week_total / periods["avg_sales_per_day_this_week"][0].day_count, 2),
                year_ago_from_weekly["last_week_value"] / 7 if year_ago_from_weekly["last_week_value"] is not None else None,
                periods["avg_sales_per_day_this_week"][0],
                Period(
                    start=year_ago_from_weekly["last_week_start"],
                    end=year_ago_from_weekly["last_week_end"],
                    label=year_ago_from_weekly["last_week_label"],
                    day_count=7,
                ) if year_ago_from_weekly["last_week_start"] else None,
            ),
            "avg_sales_per_day_last_3m": (
                round(current_3m_total / periods["avg_sales_per_day_last_3m"][0].day_count, 2),
                year_ago_from_weekly["avg_12w_per_day"],
                periods["avg_sales_per_day_last_3m"][0],
                Period(
                    start=year_ago_from_weekly["last_week_start"] - timedelta(weeks=11) if year_ago_from_weekly["last_week_start"] else None,
                    end=year_ago_from_weekly["last_week_end"],
                    label=fmt_label(
                        year_ago_from_weekly["last_week_start"] - timedelta(weeks=11),
                        year_ago_from_weekly["last_week_end"],
                    ) if year_ago_from_weekly["last_week_start"] else None,
                    day_count=84,
                ) if year_ago_from_weekly["last_week_start"] else None,
            ),
        }

        for metric_key, metric_name, display_order in metric_defs:
            current_value, year_ago_value, current_period, year_ago_period = metric_values[metric_key]
            output.append(
                (
                    as_of,
                    unit,
                    cfg["label"],
                    metric_key,
                    metric_name,
                    display_order,
                    current_period.start,
                    current_period.end,
                    current_period.label,
                    current_value,
                    year_ago_period.start if year_ago_period else None,
                    year_ago_period.end if year_ago_period else None,
                    year_ago_period.label if year_ago_period else None,
                    year_ago_value,
                )
            )
    return output


def replace_snapshot(conn, rows: List[Tuple]) -> None:
    with conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_SQL)
            cur.executemany(
                """
                INSERT INTO tmp_erp_sales_kpi_snapshot (
                    as_of_msk,
                    unit,
                    unit_label,
                    metric_key,
                    metric_name,
                    display_order,
                    current_period_start,
                    current_period_end,
                    current_period_label,
                    current_value_rub,
                    year_ago_period_start,
                    year_ago_period_end,
                    year_ago_period_label,
                    year_ago_value_rub
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        rows = current_rows(as_of, conn)
        replace_snapshot(conn, rows)
    finally:
        conn.close()

    print(
        json.dumps(
            {
                "snapshot_rows": len(rows),
                "as_of_msk": as_of.isoformat(),
                "units": sorted(UNITS.keys()),
                "table": "tmp_erp_sales_kpi_snapshot",
                "temporary_note": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
