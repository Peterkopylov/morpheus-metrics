#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import ssl
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REPORT_PATH = ROOT / "generated" / "yandex_metrica_weekly_to_fact_import_report.csv"
ENV_MAIN = ROOT / ".env.yandex_metrica"
ENV_SPB = ROOT / ".env.yandex_metrica_spb"
SSL_CONTEXT = ssl._create_unverified_context()
MSK = timezone(timedelta(hours=3))

COUNTERS = {
    "b2c_moscow": {
        "counter_id": "48759785",
        "env_path": ENV_MAIN,
        "token_key": "YANDEX_METRICA_ACCESS_TOKEN",
    },
    "b2c_spb": {
        "counter_id": "97365452",
        "env_path": ENV_SPB,
        "token_key": "YANDEX_METRICA_SPB_ACCESS_TOKEN",
    },
}

SHOW_PATHS = {
    "Ответ Гиппократа": "/gippocrat",
    "Судный день": "/sudnyj-den",
    "До свадьбы доживёт": "/do-svadby-dozhivet",
    "22'07": "/2207",
    "ВДОХ": "/vdoh",
    "Загадка Амулета": "/zagadka-amuleta",
    "Иное место": "/inoe-mesto",
    "Поезд, Чехов, два орла": "/poezd-chehov-dva-orla",
}

B2B_PAGE_PATH = "/corporative"


def path_filter(path: str) -> str:
    return (
        f"ym:pv:URLPathFull=~'^{path}([?#].*)?$' "
        f"OR ym:pv:URLPathFull=~'^{path}/([?#].*)?$'"
    )


def period_bounds(last_full_week_start: date | None = None) -> tuple[date, date]:
    if last_full_week_start:
        return last_full_week_start, last_full_week_start + timedelta(days=6)
    today = datetime.now(MSK).date()
    current_week_start = today - timedelta(days=today.weekday())
    last_week_start = current_week_start - timedelta(days=7)
    return last_week_start, last_week_start + timedelta(days=6)


def read_env_token(path: Path, key: str) -> str:
    if not path.exists():
        raise RuntimeError(f"Env file not found: {path}")
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
            WHERE source_system='yandex_metrica'
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
    value_raw: str,
    payload: dict,
    *,
    show_name: str | None = None,
    channel_name: str | None = None,
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
        "show_name": show_name,
        "partner_name": None,
        "channel_name": channel_name,
        "period_granularity": "week",
        "period_start": period_start,
        "period_end": period_end,
        "value_numeric": value_numeric,
        "value_text": None,
        "value_raw": value_raw,
        "currency_code": None,
        "is_estimated": False,
        "observed_at": datetime.combine(period_end, time.min, tzinfo=timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


def normalize_channel(last_source_id: str | None, adv_engine_id: str | None) -> str | None:
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


def channel_rows(
    token: str,
    counter_id: str,
    period_start: date,
    period_end: date,
    *,
    filters: str | None = None,
    payload_extra: dict | None = None,
) -> list[dict]:
    params = {
        "ids": counter_id,
        "date1": period_start.isoformat(),
        "date2": period_end.isoformat(),
        "dimensions": "ym:s:lastTrafficSource,ym:s:lastAdvEngine",
        "metrics": "ym:s:visits",
        "limit": "100",
    }
    if filters:
        params["filters"] = filters
    data = metrica_get(token, params)
    grouped: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    debug_rows: list[dict] = []
    for row in data.get("data", []):
        dims = row.get("dimensions", [])
        last_source_id = dims[0].get("id") if len(dims) > 0 and dims[0] else None
        adv_engine_id = dims[1].get("id") if len(dims) > 1 and dims[1] else None
        channel = normalize_channel(last_source_id, adv_engine_id)
        if not channel:
            continue
        visits = Decimal(str(row.get("metrics", [0])[0] or 0))
        grouped[channel] += visits
        debug_rows.append(
            {
                "last_source_id": last_source_id,
                "last_source_name": dims[0].get("name") if len(dims) > 0 and dims[0] else None,
                "adv_engine_id": adv_engine_id,
                "adv_engine_name": dims[1].get("name") if len(dims) > 1 and dims[1] else None,
                "visits": float(visits),
                "normalized_channel": channel,
            }
        )
    result = []
    for channel, value in grouped.items():
        payload = {
            "counter_id": counter_id,
            "raw_metric": "ym:s:visits",
            "raw_dimensions": ["ym:s:lastTrafficSource", "ym:s:lastAdvEngine"],
            "normalized_from": debug_rows,
        }
        if filters:
            payload["filter"] = filters
        if payload_extra:
            payload.update(payload_extra)
        result.append(
            {
                "channel_name": channel,
                "value_numeric": value,
                "value_raw": str(value),
                "payload": payload,
            }
        )
    return sorted(result, key=lambda item: item["channel_name"])


def show_pageviews(token: str, counter_id: str, path: str, period_start: date, period_end: date) -> tuple[Decimal, dict]:
    regex = path_filter(path)
    data = metrica_get(
        token,
        {
            "ids": counter_id,
            "date1": period_start.isoformat(),
            "date2": period_end.isoformat(),
            "metrics": "ym:pv:pageviews",
            "filters": regex,
        },
    )
    value = Decimal(str((data.get("totals") or [0])[0] or 0))
    return value, {
        "counter_id": counter_id,
        "raw_metric": "ym:pv:pageviews",
        "filter": regex,
        "path": path,
        "query": data.get("query"),
    }


def path_visits(token: str, counter_id: str, path: str, period_start: date, period_end: date) -> tuple[Decimal, dict]:
    regex = path_filter(path)
    data = metrica_get(
        token,
        {
            "ids": counter_id,
            "date1": period_start.isoformat(),
            "date2": period_end.isoformat(),
            "metrics": "ym:s:visits",
            "filters": regex,
        },
    )
    value = Decimal(str((data.get("totals") or [0])[0] or 0))
    return value, {
        "counter_id": counter_id,
        "raw_metric": "ym:s:visits",
        "filter": regex,
        "path": path,
        "query": data.get("query"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--week-start", default="2026-04-20")
    parser.add_argument("--source-run-id", default="yandex_metrica_weekly_v1")
    parser.add_argument("--delete-existing", action="store_true")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    period_start = date.fromisoformat(args.week_start)
    period_end = period_start + timedelta(days=6)

    conn = psycopg2.connect(args.database_url)
    metric_id = fetch_metric_id(conn, "Website visits")

    if args.delete_existing:
        delete_existing(conn, args.source_run_id, period_start)
        conn.commit()

    report_rows: list[dict] = []
    insert_payload: list[dict] = []

    for business_unit, meta in COUNTERS.items():
        token = read_env_token(meta["env_path"], meta["token_key"])
        counter_id = meta["counter_id"]

        for item in channel_rows(token, counter_id, period_start, period_end):
            insert_payload.append(
                build_row(
                    metric_id,
                    f"{business_unit}|channel|{item['channel_name']}",
                    args.source_run_id,
                    business_unit,
                    period_start,
                    period_end,
                    item["value_numeric"],
                    item["value_raw"],
                    item["payload"],
                    channel_name=item["channel_name"],
                )
            )
            report_rows.append(
                {
                    "business_unit": business_unit,
                    "metric_name": "Website visits",
                    "scope": f"channel:{item['channel_name']}",
                    "status": "inserted",
                    "value": str(item["value_numeric"]),
                    "note": "ym:s:visits by normalized traffic channel",
                }
            )

        for show_name, path in SHOW_PATHS.items():
            value, payload = show_pageviews(token, counter_id, path, period_start, period_end)
            insert_payload.append(
                build_row(
                    metric_id,
                    f"{business_unit}|show_page|{show_name}",
                    args.source_run_id,
                    business_unit,
                    period_start,
                    period_end,
                    value,
                    str(value),
                    payload,
                    show_name=show_name,
                )
            )
            report_rows.append(
                {
                    "business_unit": business_unit,
                    "metric_name": "Website visits",
                    "scope": f"show:{show_name}",
                    "status": "inserted",
                    "value": str(value),
                    "note": "ym:pv:pageviews by canonical show page path",
                }
            )

    main_token = read_env_token(COUNTERS["b2c_moscow"]["env_path"], COUNTERS["b2c_moscow"]["token_key"])
    main_counter_id = COUNTERS["b2c_moscow"]["counter_id"]
    b2b_filter = path_filter(B2B_PAGE_PATH)
    for item in channel_rows(
        main_token,
        main_counter_id,
        period_start,
        period_end,
        filters=b2b_filter,
        payload_extra={"path": B2B_PAGE_PATH},
    ):
        insert_payload.append(
            build_row(
                metric_id,
                f"b2b|channel|{item['channel_name']}",
                args.source_run_id,
                "b2b",
                period_start,
                period_end,
                item["value_numeric"],
                item["value_raw"],
                item["payload"],
                channel_name=item["channel_name"],
            )
        )
        report_rows.append(
            {
                "business_unit": "b2b",
                "metric_name": "Website visits",
                "scope": f"channel:{item['channel_name']}",
                "status": "inserted",
                "value": str(item["value_numeric"]),
                "note": "ym:s:visits for /corporative by normalized traffic channel",
            }
        )

    b2b_value, b2b_payload = path_visits(main_token, main_counter_id, B2B_PAGE_PATH, period_start, period_end)
    insert_payload.append(
        build_row(
            metric_id,
            "b2b|page|corporative",
            args.source_run_id,
            "b2b",
            period_start,
            period_end,
            b2b_value,
            str(b2b_value),
            b2b_payload,
        )
    )
    report_rows.append(
        {
            "business_unit": "b2b",
            "metric_name": "Website visits",
            "scope": "page:/corporative",
            "status": "inserted",
            "value": str(b2b_value),
            "note": "ym:s:visits for /corporative",
        }
    )

    insert_rows(conn, insert_payload)
    conn.commit()
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["business_unit", "metric_name", "scope", "status", "value", "note"])
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"inserted={len(insert_payload)}")
    print(f"report={report_path}")


if __name__ == "__main__":
    main()
