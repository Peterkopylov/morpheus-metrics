#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import ssl
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "yandex_metrica_tracked_purchase_visits_weekly_to_fact_import_report.csv"
ENV_MAIN = ROOT / ".env.yandex_metrica"
ENV_SPB = ROOT / ".env.yandex_metrica_spb"
SSL_CONTEXT = ssl._create_unverified_context()
MSK = timezone(timedelta(hours=3))

COUNTERS = {
    "b2c_moscow": {
        "counter_id": "48759785",
        "env_path": ENV_MAIN,
        "token_key": "YANDEX_METRICA_ACCESS_TOKEN",
        "purchase_goal_id": "458052768",
    },
    "b2c_spb": {
        "counter_id": "97365452",
        "env_path": ENV_SPB,
        "token_key": "YANDEX_METRICA_SPB_ACCESS_TOKEN",
        "purchase_goal_id": "458089032",
    },
}

PERFORMANCE_REVENUE_METRIC_NAME = "Performance marketing revenue"
PERFORMANCE_ADV_ENGINE_IDS = {"ya_direct", "ya_undefined"}


def period_bounds(last_full_week_start: date | None = None) -> tuple[date, date]:
    if last_full_week_start:
        return last_full_week_start, last_full_week_start + timedelta(days=6)
    today = datetime.now(MSK).date()
    current_week_start = today - timedelta(days=today.weekday())
    last_week_start = current_week_start - timedelta(days=7)
    return last_week_start, last_week_start + timedelta(days=6)


def read_env_token(path: Path, key: str) -> str:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip()
    token = values.get(key, "")
    if not token:
        raise RuntimeError(f"Missing {key} in {path}")
    return token


def metrica_get(token: str, params: dict[str, str]) -> dict:
    url = "https://api-metrika.yandex.net/stat/v1/data?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"OAuth {token}"})
    with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_metric_id(conn, metric_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute("select metric_id from metric_catalogue where metric_name=%s", (metric_name,))
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"metric not found: {metric_name}")
        return int(row[0])


def normalize_channel(last_source_id: str | None, adv_engine_id: str | None) -> str:
    source_id = (last_source_id or "").strip()
    adv_id = (adv_engine_id or "").strip()
    if source_id == "organic":
        return "organic"
    if source_id == "referral":
        return "referral"
    if source_id == "recommend":
        return "referral"
    if source_id == "mail":
        return "email"
    if source_id in {"social", "messenger"}:
        return "social"
    if source_id == "ad":
        if adv_id in {"ya_direct", "ya_undefined", "instagram", "vkontakte", "facebook", "unknown"}:
            return "perfomance"
        return "perfomance"
    if source_id in {"direct", "internal"}:
        return "organic"
    if source_id in {"saved", "undefined"}:
        return "other"
    return "other"


def build_row(
    metric_id: int,
    source_record_key: str,
    source_run_id: str,
    business_unit: str,
    period_start: date,
    period_end: date,
    value_numeric: Decimal,
    value_raw: str,
    payload: dict,
    *,
    channel_name: str | None = None,
    currency_code: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "metric_id": metric_id,
        "rule_id": None,
        "source_system": "yandex_metrica",
        "source_record_key": source_record_key,
        "source_run_id": source_run_id,
        "source_cell_a1": None,
        "source_cell_url": None,
        "business_unit": business_unit,
        "show_name": None,
        "partner_name": None,
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


def insert_rows(conn, rows: list[dict]) -> None:
    if not rows:
        return
    sql = """
    INSERT INTO fact_metric_observation (
        metric_id, rule_id, source_system, source_record_key, source_run_id, source_cell_a1, source_cell_url,
        business_unit, show_name, partner_name, channel_name, period_granularity, period_start, period_end,
        value_numeric, value_text, value_raw, currency_code, is_estimated, observed_at, loaded_at, payload
    )
    VALUES (
        %(metric_id)s, %(rule_id)s, %(source_system)s, %(source_record_key)s, %(source_run_id)s, %(source_cell_a1)s, %(source_cell_url)s,
        %(business_unit)s, %(show_name)s, %(partner_name)s, %(channel_name)s, %(period_granularity)s, %(period_start)s, %(period_end)s,
        %(value_numeric)s, %(value_text)s, %(value_raw)s, %(currency_code)s, %(is_estimated)s, %(observed_at)s, %(loaded_at)s, %(payload)s
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
            WHERE source_system='yandex_metrica'
              AND source_run_id=%s
              AND period_granularity='week'
              AND period_start=%s
            """,
            (source_run_id, week_start),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--week-start", help="YYYY-MM-DD for the Monday of the week to load")
    parser.add_argument("--source-run-id", default="yandex_metrica_tracked_purchase_visits_weekly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    week_start = date.fromisoformat(args.week_start) if args.week_start else None
    period_start, period_end = period_bounds(week_start)

    conn = psycopg2.connect(args.database_url)
    metric_id = fetch_metric_id(conn, "Metrica tracked purchase visits")
    if args.delete_existing:
        delete_existing(conn, args.source_run_id, period_start)
        conn.commit()

    report_rows: list[dict[str, str]] = []
    insert_payload: list[dict] = []

    for unit, meta in COUNTERS.items():
        token = read_env_token(meta["env_path"], meta["token_key"])
        params = {
            "ids": meta["counter_id"],
            "metrics": f"ym:s:visits,ym:s:goal{meta['purchase_goal_id']}visits",
            "dimensions": "ym:s:lastTrafficSource,ym:s:lastAdvEngine",
            "date1": period_start.isoformat(),
            "date2": period_end.isoformat(),
            "limit": "100",
        }
        response = metrica_get(token, params)
        total_value = Decimal(str((response.get("totals") or [0, 0])[1] or 0))
        insert_payload.append(
            build_row(
                metric_id,
                f"{unit}|general|tracked_purchase_visits|{period_start.isoformat()}",
                args.source_run_id,
                unit,
                period_start,
                period_end,
                total_value,
                str(total_value),
                {"source": "yandex_metrica", "goal_id": meta["purchase_goal_id"], "scope": "general"},
            )
        )
        report_rows.append({"unit": unit, "scope": "general", "status": "inserted", "value": str(total_value), "reason": ""})

        for row in response.get("data") or []:
            dims = row.get("dimensions") or [{}, {}]
            metrics = row.get("metrics") or [0, 0]
            tracked_visits = Decimal(str(metrics[1] or 0))
            if tracked_visits == 0:
                continue
            source_id = dims[0].get("id")
            adv_id = dims[1].get("id")
            channel_name = normalize_channel(source_id, adv_id)
            insert_payload.append(
                build_row(
                    metric_id,
                    f"{unit}|{channel_name}|{source_id}|{adv_id}|{period_start.isoformat()}",
                    args.source_run_id,
                    unit,
                    period_start,
                    period_end,
                    tracked_visits,
                    str(tracked_visits),
                    {
                        "source": "yandex_metrica",
                        "goal_id": meta["purchase_goal_id"],
                        "last_traffic_source": source_id,
                        "last_adv_engine": adv_id,
                        "scope": "channel",
                    },
                    channel_name=channel_name,
                )
            )
            report_rows.append({"unit": unit, "scope": f"channel:{channel_name}", "status": "inserted", "value": str(tracked_visits), "reason": ""})

        revenue_metric_id = fetch_metric_id(conn, PERFORMANCE_REVENUE_METRIC_NAME)
        revenue_params = {
            "ids": meta["counter_id"],
            "metrics": "ym:s:favoriteGoalsConvertedRUBRevenue",
            "dimensions": "ym:s:<attribution>TrafficSource,ym:s:<attribution>AdvEngine",
            "date1": period_start.isoformat(),
            "date2": period_end.isoformat(),
            "limit": "100",
            "accuracy": "full",
            "attribution": "automatic",
        }
        revenue_response = metrica_get(token, revenue_params)
        revenue_components: list[dict[str, str]] = []
        performance_revenue = Decimal("0")
        for row in revenue_response.get("data") or []:
            dims = row.get("dimensions") or [{}, {}]
            metrics = row.get("metrics") or [0]
            source_id = dims[0].get("id")
            adv_id = dims[1].get("id")
            value = Decimal(str(metrics[0] or 0)).quantize(Decimal("0.01"))
            if source_id == "ad" and adv_id in PERFORMANCE_ADV_ENGINE_IDS:
                performance_revenue += value
                revenue_components.append(
                    {
                        "last_traffic_source": str(source_id),
                        "last_adv_engine": str(adv_id),
                        "value": str(value),
                    }
                )
        insert_payload.append(
            build_row(
                revenue_metric_id,
                f"{unit}|perfomance|performance_revenue|{period_start.isoformat()}",
                args.source_run_id,
                unit,
                period_start,
                period_end,
                performance_revenue,
                str(performance_revenue),
                {
                    "source": "yandex_metrica",
                    "metric": "ym:s:favoriteGoalsConvertedRUBRevenue",
                    "dimensions": "ym:s:<attribution>TrafficSource,ym:s:<attribution>AdvEngine",
                    "attribution": "automatic",
                    "included_adv_engines": sorted(PERFORMANCE_ADV_ENGINE_IDS),
                    "components": revenue_components,
                    "scope": "channel",
                    "note": "Performance revenue is Metrica favorite-goals converted RUB revenue for Yandex Direct + Yandex Direct: Undetermined.",
                },
                channel_name="perfomance",
                currency_code="RUB",
            )
        )
        report_rows.append({"unit": unit, "scope": "channel:perfomance:revenue", "status": "inserted", "value": str(performance_revenue), "reason": ""})

    insert_rows(conn, insert_payload)
    conn.commit()
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["unit", "scope", "status", "value", "reason"])
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"period={period_start}..{period_end} inserted={len(report_rows)} report={report_path}")


if __name__ == "__main__":
    main()
