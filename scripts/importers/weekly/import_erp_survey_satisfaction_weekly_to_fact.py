#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import ssl
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib import request

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "erp_survey_satisfaction_weekly_to_fact_import_report.csv"
SSL_CONTEXT = ssl._create_unverified_context()
MSK = timezone(timedelta(hours=3))
ERP_BASE = "https://morpheus-server.ru:{port}{path}"

UNITS = {
    "b2c_moscow": {"port": 45010},
    "b2c_spb": {"port": 45011},
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


def period_bounds(last_full_week_start: date | None = None) -> tuple[date, date]:
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


def fetch_metric_ids(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            select metric_name, metric_id
            from metric_catalogue
            where metric_name in (
                'Number of post-show survey responses',
                'Number of show rating responses',
                'Sum of post-show ratings',
                'Number of source-attribution responses',
                'Number of question 3 responses',
                'Number of question 4 responses'
            )
            """
        )
        return {name: metric_id for name, metric_id in cur.fetchall()}


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
    show_name: str,
    value_numeric: Decimal,
    value_raw: str,
    payload: dict,
    value_text: str | None = None,
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
        "partner_name": None,
        "channel_name": None,
        "period_granularity": "week",
        "period_start": period_start,
        "period_end": period_end,
        "value_numeric": value_numeric,
        "value_text": value_text,
        "value_raw": value_raw,
        "currency_code": None,
        "is_estimated": False,
        "observed_at": datetime.combine(period_end, time.min, tzinfo=timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


def normalize_show(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    return SHOW_CANON.get(s, s)


def normalize_q2(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    low = s.lower()
    if low in {"друзья, знакомые", "друг", "подруга"} or "подружка" in low or "пригласила" in low:
        return "От друзей"
    if low in {"я.афиша", "т банк афиша", "тафиша"}:
        return "Яндекс Афиша"
    if low == "яндекс / google":
        return "Яндекс / Google"
    if low == "соц. сети":
        return "Соц. сети"
    if low == "карты яндекс, google, 2гис":
        return "Карты Яндекс, Google, 2ГИС"
    if low == "подарили сертификат":
        return "Подарили сертификат"
    if low == "реклама в интернете":
        return "Реклама в интернете"
    if low == "сайт morpheus":
        return "Наш сайт"
    return s


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--week-start", help="YYYY-MM-DD for the Monday of the week to load")
    parser.add_argument("--source-run-id", default="erp_survey_satisfaction_weekly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    week_start = date.fromisoformat(args.week_start) if args.week_start else None
    period_start, period_end = period_bounds(week_start)
    dt_from, dt_to = start_end_datetimes(period_start, period_end)

    conn = psycopg2.connect(args.database_url)
    metric_ids = fetch_metric_ids(conn)
    if args.delete_existing:
        delete_existing(conn, args.source_run_id, period_start)
        conn.commit()

    report_rows: list[dict] = []
    insert_payload: list[dict] = []

    for unit, meta in UNITS.items():
        rows = fetch_json(meta["port"], "/survey/satisfaction", {"from": fmt_ts(dt_from), "to": fmt_ts(dt_to)})

        total_responses_general = 0
        total_responses_by_show = Counter()
        q1_count = Counter()
        q1_sum = defaultdict(Decimal)
        q2_counts_general = Counter()
        q2_counts_by_show = Counter()
        q3_counts_by_show = Counter()
        q4_counts_by_show = Counter()

        for row in rows:
            show_name = normalize_show(row.get("seance_name"))
            if not show_name:
                report_rows.append({"unit": unit, "metric_name": "survey/satisfaction", "scope": "", "status": "skipped", "value": "", "reason": "missing_show_name"})
                continue
            answers = row.get("answers") or {}

            q1 = str(answers.get("1") or "").strip()
            q2 = str(answers.get("2") or "").strip()
            q3 = str(answers.get("3") or "").strip()
            q4 = str(answers.get("4") or "").strip()

            # overall survey response count: any non-empty answer
            if any([q1, q2, q3, q4]):
                total_responses_general += 1
                total_responses_by_show[show_name] += 1

            if q1 and q1.isdigit():
                q1_count[show_name] += 1
                q1_sum[show_name] += Decimal(q1)

            if q2:
                cat = normalize_q2(q2)
                q2_counts_general[cat] += 1
                q2_counts_by_show[(show_name, cat)] += 1

            if q3:
                q3_counts_by_show[(show_name, q3)] += 1

            if q4:
                q4_counts_by_show[(show_name, q4)] += 1

        # post-show survey responses: general + by show
        insert_payload.append(
            base_row(
                metric_ids["Number of post-show survey responses"],
                f"{unit}|general|survey_responses|{period_start.isoformat()}",
                args.source_run_id,
                unit,
                period_start,
                period_end,
                "general",
                Decimal(total_responses_general),
                str(total_responses_general),
                {"source": "erp_survey_satisfaction", "question": "any_nonempty", "unit": unit},
            )
        )
        report_rows.append({"unit": unit, "metric_name": "Number of post-show survey responses", "scope": "show:general", "status": "inserted", "value": str(total_responses_general), "reason": ""})
        for show_name, count in sorted(total_responses_by_show.items()):
            insert_payload.append(
                base_row(
                    metric_ids["Number of post-show survey responses"],
                    f"{unit}|{show_name}|survey_responses|{period_start.isoformat()}",
                    args.source_run_id,
                    unit,
                    period_start,
                    period_end,
                    show_name,
                    Decimal(count),
                    str(count),
                    {"source": "erp_survey_satisfaction", "question": "any_nonempty", "unit": unit},
                )
            )
            report_rows.append({"unit": unit, "metric_name": "Number of post-show survey responses", "scope": f"show:{show_name}", "status": "inserted", "value": str(count), "reason": ""})

        # q1 by show
        for show_name, count in sorted(q1_count.items()):
            insert_payload.append(
                base_row(
                    metric_ids["Number of show rating responses"],
                    f"{unit}|{show_name}|q1_count|{period_start.isoformat()}",
                    args.source_run_id,
                    unit,
                    period_start,
                    period_end,
                    show_name,
                    Decimal(count),
                    str(count),
                    {"source": "erp_survey_satisfaction", "question": 1, "measure": "count"},
                )
            )
            report_rows.append({"unit": unit, "metric_name": "Number of show rating responses", "scope": f"show:{show_name}", "status": "inserted", "value": str(count), "reason": ""})
        for show_name, total in sorted(q1_sum.items()):
            insert_payload.append(
                base_row(
                    metric_ids["Sum of post-show ratings"],
                    f"{unit}|{show_name}|q1_sum|{period_start.isoformat()}",
                    args.source_run_id,
                    unit,
                    period_start,
                    period_end,
                    show_name,
                    total,
                    str(total),
                    {"source": "erp_survey_satisfaction", "question": 1, "measure": "sum"},
                )
            )
            report_rows.append({"unit": unit, "metric_name": "Sum of post-show ratings", "scope": f"show:{show_name}", "status": "inserted", "value": str(total), "reason": ""})

        # q2 source attribution counts general + by show/category
        for category, count in sorted(q2_counts_general.items()):
            insert_payload.append(
                base_row(
                    metric_ids["Number of source-attribution responses"],
                    f"{unit}|general|q2|{category}|{period_start.isoformat()}",
                    args.source_run_id,
                    unit,
                    period_start,
                    period_end,
                    "general",
                    Decimal(count),
                    str(count),
                    {"source": "erp_survey_satisfaction", "question": 2, "response_category": category, "scope": "general"},
                    value_text=category,
                )
            )
            report_rows.append({"unit": unit, "metric_name": "Number of source-attribution responses", "scope": f"general:{category}", "status": "inserted", "value": str(count), "reason": ""})
        for (show_name, category), count in sorted(q2_counts_by_show.items()):
            insert_payload.append(
                base_row(
                    metric_ids["Number of source-attribution responses"],
                    f"{unit}|{show_name}|q2|{category}|{period_start.isoformat()}",
                    args.source_run_id,
                    unit,
                    period_start,
                    period_end,
                    show_name,
                    Decimal(count),
                    str(count),
                    {"source": "erp_survey_satisfaction", "question": 2, "response_category": category, "scope": "show"},
                    value_text=category,
                )
            )
            report_rows.append({"unit": unit, "metric_name": "Number of source-attribution responses", "scope": f"show:{show_name}|{category}", "status": "inserted", "value": str(count), "reason": ""})

        # q3 by show/category
        for (show_name, category), count in sorted(q3_counts_by_show.items()):
            insert_payload.append(
                base_row(
                    metric_ids["Number of question 3 responses"],
                    f"{unit}|{show_name}|q3|{category}|{period_start.isoformat()}",
                    args.source_run_id,
                    unit,
                    period_start,
                    period_end,
                    show_name,
                    Decimal(count),
                    str(count),
                    {"source": "erp_survey_satisfaction", "question": 3, "response_category": category},
                    value_text=category,
                )
            )
            report_rows.append({"unit": unit, "metric_name": "Number of question 3 responses", "scope": f"show:{show_name}|{category}", "status": "inserted", "value": str(count), "reason": ""})

        # q4 by show/category
        for (show_name, category), count in sorted(q4_counts_by_show.items()):
            insert_payload.append(
                base_row(
                    metric_ids["Number of question 4 responses"],
                    f"{unit}|{show_name}|q4|{category}|{period_start.isoformat()}",
                    args.source_run_id,
                    unit,
                    period_start,
                    period_end,
                    show_name,
                    Decimal(count),
                    str(count),
                    {"source": "erp_survey_satisfaction", "question": 4, "response_category": category},
                    value_text=category,
                )
            )
            report_rows.append({"unit": unit, "metric_name": "Number of question 4 responses", "scope": f"show:{show_name}|{category}", "status": "inserted", "value": str(count), "reason": ""})

    insert_rows(conn, insert_payload)
    conn.commit()
    conn.close()

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
