#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import urllib.error
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

from import_yandex_metrica_tracked_purchase_visits_weekly_to_fact import (
    COUNTERS,
    MSK,
    PERFORMANCE_ADV_ENGINE_IDS,
    PERFORMANCE_REVENUE_METRIC_NAME,
    fetch_metric_id,
    insert_rows,
    metrica_get,
    normalize_channel,
    read_env_token,
)
from monthly_kpi_period_utils import month_bounds


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "yandex_metrica_tracked_purchase_visits_monthly_to_fact_import_report.csv"


def metrica_get_with_month_fallback(token: str, params: dict[str, str], period_start: date, period_end: date) -> dict:
    try:
        return metrica_get(token, params)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code != 400 or "Query is too complicated" not in detail:
            raise RuntimeError(detail) from exc

    totals: list[Decimal] | None = None
    rows: dict[tuple[tuple[str | None, str | None], ...], dict] = {}
    chunk_start = period_start
    while chunk_start <= period_end:
        chunk_end = min(chunk_start + timedelta(days=6), period_end)
        chunk_params = dict(params)
        chunk_params["date1"] = chunk_start.isoformat()
        chunk_params["date2"] = chunk_end.isoformat()
        chunk_response = metrica_get(token, chunk_params)
        chunk_totals = [Decimal(str(value or 0)) for value in (chunk_response.get("totals") or [])]
        if totals is None:
            totals = [Decimal("0") for _ in chunk_totals]
        for idx, value in enumerate(chunk_totals):
            totals[idx] += value
        for row in chunk_response.get("data") or []:
            dimensions = row.get("dimensions") or []
            key = tuple((dimension.get("id"), dimension.get("name")) for dimension in dimensions)
            existing = rows.setdefault(
                key,
                {
                    "dimensions": dimensions,
                    "metrics": [0 for _ in (row.get("metrics") or [])],
                },
            )
            existing["metrics"] = [
                float(Decimal(str(old or 0)) + Decimal(str(new or 0)))
                for old, new in zip(existing.get("metrics") or [], row.get("metrics") or [])
            ]
        chunk_start = chunk_end + timedelta(days=1)

    return {
        "totals": [float(value) for value in (totals or [])],
        "data": list(rows.values()),
    }


def delete_existing(conn, source_run_id: str, period_start: date) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM fact_metric_observation
            WHERE source_system='yandex_metrica'
              AND source_run_id=%s
              AND period_granularity='month'
              AND period_start=%s
            """,
            (source_run_id, period_start),
        )


def build_row(metric_id: int, source_record_key: str, source_run_id: str, business_unit: str, period_start: date, period_end: date, value_numeric, value_raw: str, payload: dict, *, channel_name: str | None = None, currency_code: str | None = None) -> dict:
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
        "period_granularity": "month",
        "period_start": period_start,
        "period_end": period_end,
        "value_numeric": value_numeric,
        "value_text": None,
        "value_raw": value_raw,
        "currency_code": currency_code,
        "is_estimated": False,
        "observed_at": datetime.combine(period_end, time(23, 59, 59), tzinfo=MSK).astimezone(timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--month-start", required=True)
    parser.add_argument("--source-run-id", default="yandex_metrica_tracked_purchase_visits_monthly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    period_start, period_end = month_bounds(date.fromisoformat(args.month_start))
    conn = psycopg2.connect(args.database_url)
    metric_id = fetch_metric_id(conn, "Metrica tracked purchase visits")
    revenue_metric_id = fetch_metric_id(conn, PERFORMANCE_REVENUE_METRIC_NAME)
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
        response = metrica_get_with_month_fallback(token, params, period_start, period_end)
        total_value = Decimal(str((response.get("totals") or [0, 0])[1] or 0))
        insert_payload.append(build_row(metric_id, f"{unit}|general|tracked_purchase_visits|{period_start.isoformat()}", args.source_run_id, unit, period_start, period_end, total_value, str(total_value), {"source": "yandex_metrica", "goal_id": meta["purchase_goal_id"], "scope": "general"}))
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
            insert_payload.append(build_row(metric_id, f"{unit}|{channel_name}|{source_id}|{adv_id}|{period_start.isoformat()}", args.source_run_id, unit, period_start, period_end, tracked_visits, str(tracked_visits), {"source": "yandex_metrica", "goal_id": meta["purchase_goal_id"], "last_traffic_source": source_id, "last_adv_engine": adv_id, "scope": "channel"}, channel_name=channel_name))
            report_rows.append({"unit": unit, "scope": f"channel:{channel_name}", "status": "inserted", "value": str(tracked_visits), "reason": ""})

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
        revenue_response = metrica_get_with_month_fallback(token, revenue_params, period_start, period_end)
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
                revenue_components.append({"last_traffic_source": str(source_id), "last_adv_engine": str(adv_id), "value": str(value)})
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
    with report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["unit", "scope", "status", "value", "reason"])
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"period={period_start}..{period_end} inserted={len(report_rows)} report={report_path}")


if __name__ == "__main__":
    main()
