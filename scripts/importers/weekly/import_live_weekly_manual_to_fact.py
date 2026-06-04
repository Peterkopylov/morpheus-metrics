#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

import psycopg2
from psycopg2.extras import Json, execute_batch
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
LIVE_DIR = ROOT / "generated" / "live_sheet_outlines"
DEFAULT_REPORT_PATH = ROOT / "generated" / "live_weekly_manual_to_fact_import_report.csv"
DEFAULT_SOURCE_RUN_ID = "weekly_manual_live_v3"
GENERATED_DIR = ROOT / "generated"
DEFAULT_GOOGLE_SERVICE_ACCOUNT_JSON = Path(
    os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "/Users/Peter/Downloads/appointments-1084-0dcc0dd99d1b.json",
    )
)


PLAN_CONFIGS = [
    {
        "unit": "b2c_moscow",
        "plan_path": LIVE_DIR / "b2c_moscow_ingestion_plan_live_v3.csv",
        "sheet_id": "1gHuxPxZntVLAxhxY9yFuBRhvozm45r2LcnvId83CY-s",
        "gid": "1411303700",
        "tab": "Статистика_понедельно",
    },
    {
        "unit": "b2c_spb",
        "plan_path": LIVE_DIR / "b2c_spb_ingestion_plan_live_v3.csv",
        "sheet_id": "1q71g1XD5fwTMo7xbEe1fGvXVTRyPfEswCPxyjVTEZi0",
        "gid": "1411303700",
        "tab": "Статистика_понедельно",
    },
]


PARTNER_MAP = {
    "яндекс афиша": "яндекс.афиша",
    "билеты яндекс афиша": "яндекс.афиша",
    "афиша.ру": "афиша.ру",
    "афиша.ру (+т-банк)": "афиша.ру",
    "афиша.ру (т-банк)": "афиша.ру",
    "кассир": "кассир",
    "тикетленд": "тикетлэнд",
    "тикетлэнд": "тикетлэнд",
    "билеты от остальных агрегаторов": "others",
    "билеты сд от остальных агрегаторов": "others",
    "сертификаты через партнеров": "others",
}


SHOW_MAP = {
    "ответ гиппократа": "Ответ Гиппократа",
    "до свадьбы доживет": "До свадьбы доживёт",
    "до свадьбы доживёт": "До свадьбы доживёт",
    "22’07": "22'07",
    "22'07": "22'07",
    "вдох": "ВДОХ",
    "иное место": "Иное место",
    "поезд, чехов, два орла": "Поезд, Чехов, два орла",
    "загадка амулета": "Загадка Амулета",
    "судный день": "Судный день",
}


@dataclass
class PlanRow:
    row_number: int
    col_a: str
    col_b: str
    action: str
    target: str
    source_override: str
    import_as_source: str
    layer: str
    note: str


def col_to_a1(col_number_1_based: int) -> str:
    result = ""
    num = col_number_1_based
    while num > 0:
        num, rem = divmod(num - 1, 26)
        result = chr(65 + rem) + result
    return result


def build_sheet_cell_a1(row_number_1_based: int, col_number_1_based: int) -> str:
    return f"{col_to_a1(col_number_1_based)}{row_number_1_based}"


def build_sheet_cell_url(sheet_id: str, gid: str, tab: str, row_number_1_based: int, col_number_1_based: int) -> str:
    a1 = build_sheet_cell_a1(row_number_1_based, col_number_1_based)
    tab_name = tab or ""
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit?gid={gid}#gid={gid}&range={tab_name}!{a1}"


def norm(text: str) -> str:
    text = (text or "").replace("\xa0", " ").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def load_plan(path: Path) -> Dict[int, PlanRow]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    result: Dict[int, PlanRow] = {}
    for row in rows:
        result[int(row["row_number"])] = PlanRow(
            row_number=int(row["row_number"]),
            col_a=(row.get("col_a") or "").strip(),
            col_b=(row.get("col_b") or "").strip(),
            action=(row.get("ingestion_action") or "").strip(),
            target=(row.get("target_metric_or_metrics") or "").strip(),
            source_override=(row.get("source_system_override") or "").strip(),
            import_as_source=(row.get("import_as_source") or "").strip(),
            layer=(row.get("layer") or "").strip(),
            note=(row.get("note") or "").strip(),
        )
    return result


def fetch_week_rows(conn, unit: str, requested_period_start: Optional[date] = None) -> Tuple[date, date, Dict[int, dict]]:
    with conn.cursor() as cur:
        if requested_period_start is None:
            cur.execute(
                """
                select max(period_start), max(period_end)
                from fact_metrics
                where aggregation_level='week' and unit=%s
                """,
                (unit,),
            )
            period_start, period_end = cur.fetchone()
        else:
            cur.execute(
                """
                select min(period_start), max(period_end)
                from fact_metrics
                where aggregation_level='week' and unit=%s and period_start=%s
                """,
                (unit, requested_period_start),
            )
            period_start, period_end = cur.fetchone()
        if period_start is None:
            raise RuntimeError(f"No weekly fact_metrics rows found for unit={unit} period_start={requested_period_start}")
        cur.execute(
            """
            select row_order, metric_group, metric_name, value, value_raw, value_type,
                   source_sheet_id, source_gid, source_tab, period_label, col_order,
                   source_cell_a1, source_cell_url
            from fact_metrics
            where aggregation_level='week' and unit=%s and period_start=%s
            order by row_order
            """,
            (unit, period_start),
        )
        rows = {}
        for (
            row_order,
            metric_group,
            metric_name,
            value,
            value_raw,
            value_type,
            source_sheet_id,
            source_gid,
            source_tab,
            period_label,
            col_order,
            source_cell_a1,
            source_cell_url,
        ) in cur.fetchall():
            rows[row_order] = {
                "metric_group": metric_group,
                "metric_name": metric_name,
                "value": value,
                "value_raw": value_raw,
                "value_type": value_type,
                "source_sheet_id": source_sheet_id,
                "source_gid": source_gid,
                "source_tab": source_tab,
                "period_label": period_label,
                "col_order": col_order,
                "source_cell_a1": source_cell_a1,
                "source_cell_url": source_cell_url,
            }
    return period_start, period_end, rows


def fetch_metric_ids(conn) -> Dict[str, int]:
    with conn.cursor() as cur:
        cur.execute("select metric_id, metric_name from metric_catalogue")
        return {metric_name: metric_id for metric_id, metric_name in cur.fetchall()}


def week_key(period_start: date) -> str:
    return period_start.isoformat().replace("-", "_")


def candidate_live_value_paths(period_start: date) -> List[Path]:
    key = week_key(period_start)
    return [
        GENERATED_DIR / f"manual_table_live_transfer_status_{key}_reconciled.csv",
        GENERATED_DIR / f"manual_table_live_transfer_status_{key}.csv",
    ]


def load_live_value_rows(period_start: date) -> Dict[Tuple[str, int], dict]:
    for path in candidate_live_value_paths(period_start):
        if not path.exists():
            continue
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        result: Dict[Tuple[str, int], dict] = {}
        for row in rows:
            try:
                key = (row["sheet_unit"], int(row["row_number"]))
            except (KeyError, ValueError):
                continue
            result[key] = row
        return result
    return {}


def build_google_authorized_session() -> Optional[AuthorizedSession]:
    if not DEFAULT_GOOGLE_SERVICE_ACCOUNT_JSON.exists():
        return None
    creds = Credentials.from_service_account_file(
        str(DEFAULT_GOOGLE_SERVICE_ACCOUNT_JSON),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return AuthorizedSession(creds)


def fetch_sheet_ranges(
    session: AuthorizedSession,
    sheet_id: str,
    ranges: List[str],
) -> Dict[str, List[List[str]]]:
    encoded_ranges = "&".join(f"ranges={quote(r)}" for r in ranges)
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values:batchGet"
        f"?majorDimension=ROWS&valueRenderOption=FORMATTED_VALUE&{encoded_ranges}"
    )
    response = session.get(url, timeout=60)
    response.raise_for_status()
    payload = response.json()
    result: Dict[str, List[List[str]]] = {}
    for block in payload.get("valueRanges", []):
        raw_range = block.get("range", "")
        result[raw_range] = block.get("values", [])
        result[raw_range.replace("'", "")] = block.get("values", [])
    return result


def infer_week_column(staging_rows: Dict[int, dict]) -> Optional[int]:
    for row in staging_rows.values():
        col_order = row.get("col_order")
        if col_order:
            return int(col_order)
    return None


def infer_sheet_meta(staging_rows: Dict[int, dict], config: dict) -> dict:
    meta = {
        "sheet_id": config.get("sheet_id"),
        "gid": config.get("gid"),
        "tab": config.get("tab"),
    }
    for row in staging_rows.values():
        if row.get("source_sheet_id"):
            meta["sheet_id"] = row["source_sheet_id"]
        if row.get("source_gid"):
            meta["gid"] = row["source_gid"]
        if meta["sheet_id"] and meta["gid"]:
            break
    return meta


def load_live_value_rows_from_google(
    config: dict,
    plan: Dict[int, PlanRow],
    staging_rows: Dict[int, dict],
) -> Dict[Tuple[str, int], dict]:
    session = build_google_authorized_session()
    if not session:
        return {}

    week_col_order = infer_week_column(staging_rows)
    if not week_col_order:
        return {}

    max_row = max(plan) if plan else 0
    if max_row <= 0:
        return {}

    meta = infer_sheet_meta(staging_rows, config)
    if not (meta["sheet_id"] and meta["gid"] and meta["tab"]):
        return {}

    tab = meta["tab"]
    week_col_a1 = col_to_a1(week_col_order)
    ranges = [
        f"{tab}!A1:A{max_row}",
        f"{tab}!B1:B{max_row}",
        f"{tab}!{week_col_a1}1:{week_col_a1}{max_row}",
    ]
    values = fetch_sheet_ranges(session, meta["sheet_id"], ranges)
    col_a_rows = values.get(ranges[0], [])
    col_b_rows = values.get(ranges[1], [])
    week_rows = values.get(ranges[2], [])

    def row_value(rows: List[List[str]], row_number: int) -> str:
        idx = row_number - 1
        if idx < 0 or idx >= len(rows):
            return ""
        return rows[idx][0] if rows[idx] else ""

    result: Dict[Tuple[str, int], dict] = {}
    for row_number in sorted(plan):
        result[(config["unit"], row_number)] = {
            "sheet_unit": config["unit"],
            "row_number": str(row_number),
            "col_a": row_value(col_a_rows, row_number),
            "col_b": row_value(col_b_rows, row_number),
            "value": row_value(week_rows, row_number),
            "source_cell_a1": build_sheet_cell_a1(row_number, week_col_order),
            "source_cell_url": build_sheet_cell_url(
                meta["sheet_id"],
                meta["gid"],
                tab,
                row_number,
                week_col_order,
            ),
        }
    return result


def parse_live_numeric_value(raw: str) -> Optional[Decimal]:
    raw = (raw or "").replace("\xa0", " ").strip()
    if not raw:
        return None
    normalized = raw.replace(" ", "").replace("%", "").replace(",", ".").replace("−", "-")
    if normalized in {"", "-"}:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def parse_google_sheet_metadata_from_url(url: str) -> dict:
    url = url or ""
    meta = {
        "source_sheet_id": None,
        "source_gid": None,
        "source_tab": None,
    }
    match = re.search(r"/spreadsheets/d/([^/]+)/edit\?gid=([0-9]+)", url)
    if match:
        meta["source_sheet_id"] = match.group(1)
        meta["source_gid"] = match.group(2)
    range_match = re.search(r"[#&]range=([^!]+)!", url)
    if range_match:
        meta["source_tab"] = range_match.group(1)
    return meta


def build_live_fallback_staging(row_number: int, live_row: Optional[dict]) -> Optional[dict]:
    if not live_row:
        return None
    value_raw = (live_row.get("value") or "").strip()
    value_numeric = parse_live_numeric_value(value_raw)
    if value_numeric is None and value_raw == "":
        return None
    meta = parse_google_sheet_metadata_from_url(live_row.get("source_cell_url", ""))
    return {
        "metric_group": live_row.get("col_a", ""),
        "metric_name": live_row.get("col_b", ""),
        "value": value_numeric,
        "value_raw": value_raw,
        "value_type": "live_fallback",
        "source_sheet_id": meta["source_sheet_id"],
        "source_gid": meta["source_gid"],
        "source_tab": meta["source_tab"],
        "period_label": "",
        "col_order": None,
        "source_cell_a1": live_row.get("source_cell_a1") or None,
        "source_cell_url": live_row.get("source_cell_url") or None,
    }


def derive_business_unit(plan: PlanRow, default_unit: str) -> str:
    if plan.col_a == "ФРАНШИЗА":
        return "franchise"
    if plan.col_a == "КОРПОРАТИВЫ":
        return "b2b"
    if "immersivny" in norm(plan.col_b):
        return "immersivny"
    if "corporative" in norm(plan.col_b):
        return "b2b"
    return default_unit


def derive_partner(plan: PlanRow) -> Optional[str]:
    candidates = [norm(plan.col_b), norm(plan.col_a)]
    for candidate in candidates:
        if candidate in PARTNER_MAP:
            return PARTNER_MAP[candidate]
    return None


def derive_show(plan: PlanRow, target_metric: str) -> Optional[str]:
    candidates = [norm(plan.col_b), norm(plan.col_a)]
    for candidate in candidates:
        if candidate in SHOW_MAP:
            return SHOW_MAP[candidate]
    if "сертификат" in norm(plan.col_b) and target_metric == "Revenue":
        return "сертификаты"
    return None


def derive_channel(plan: PlanRow) -> Optional[str]:
    label = norm(plan.col_b)
    if not label:
        return None
    if any(token in label for token in ["контекст", "яндекс", "гугл"]):
        return "perfomance"
    if any(token in label for token in ["таргет", "vk", "fb", "youtube", "instagram", "вк"]):
        return "social"
    if any(token in label for token in ["афиша", "тикет", "best benefits", "kuda", "пиар"]):
        return "partners"
    if any(token in label for token in ["почта", "email"]):
        return "email"
    if any(token in label for token in ["прочие", "обшие", "общие", "другое"]):
        return "other"
    return None


def is_website_orders_reference_row(unit: str, staging: dict, target_metric: str) -> bool:
    if target_metric != "Number of orders":
        return False
    group_label = norm(staging.get("metric_group") or "")
    metric_label = norm(staging.get("metric_name") or "")
    if unit == "b2c_moscow":
        return group_label == "сайт" and metric_label == "заказов всего (я.билеты)"
    if unit == "b2c_spb":
        return group_label == "количество заказов" and metric_label == ""
    return False


def split_targets(target: str) -> List[str]:
    return [part.strip() for part in target.split(";") if part.strip()]


def should_skip_multi_target(plan: PlanRow) -> bool:
    targets = split_targets(plan.target)
    return len(targets) != 1


def build_insert_row(
    metric_id: int,
    source_system: str,
    source_record_key: str,
    source_run_id: str,
    source_cell_a1: Optional[str],
    source_cell_url: Optional[str],
    business_unit: str,
    show_name: Optional[str],
    partner_name: Optional[str],
    channel_name: Optional[str],
    period_start,
    period_end,
    value_numeric,
    value_text: Optional[str],
    value_raw: str,
    payload: dict,
) -> dict:
    now = datetime.now(timezone.utc)
    currency_code = "RUB" if metric_id else None
    return {
        "metric_id": metric_id,
        "rule_id": None,
        "source_system": source_system,
        "source_record_key": source_record_key,
        "source_run_id": source_run_id,
        "source_cell_a1": source_cell_a1,
        "source_cell_url": source_cell_url,
        "business_unit": business_unit,
        "show_name": show_name,
        "partner_name": partner_name,
        "channel_name": channel_name,
        "period_granularity": "week",
        "period_start": period_start,
        "period_end": period_end,
        "value_numeric": value_numeric,
        "value_text": value_text,
        "value_raw": value_raw,
        "currency_code": currency_code if value_numeric is not None and payload.get("target_metric") and "Revenue" in payload["target_metric"] or payload.get("target_metric") in {"Marketing costs", "Account balance", "Returns amount", "Returns amount - theater fault", "Returns amount - non-theater fault"} else None,
        "is_estimated": False,
        "observed_at": datetime.combine(period_end, datetime.min.time(), tzinfo=timezone.utc),
        "loaded_at": now,
        "payload": Json(payload),
    }


INSERT_SQL = """
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
    rule_id = EXCLUDED.rule_id,
    source_run_id = EXCLUDED.source_run_id,
    source_cell_a1 = EXCLUDED.source_cell_a1,
    source_cell_url = EXCLUDED.source_cell_url,
    value_numeric = EXCLUDED.value_numeric,
    value_text = EXCLUDED.value_text,
    value_raw = EXCLUDED.value_raw,
    currency_code = EXCLUDED.currency_code,
    is_estimated = EXCLUDED.is_estimated,
    observed_at = EXCLUDED.observed_at,
    loaded_at = EXCLUDED.loaded_at,
    payload = EXCLUDED.payload
"""


DELETE_SQL = """
DELETE FROM fact_metric_observation
WHERE source_system = 'manual_table'
  AND source_run_id = %(source_run_id)s
  AND period_granularity = 'week'
  AND period_start = %(period_start)s
  AND business_unit in ('b2c_moscow', 'b2c_spb', 'b2b', 'franchise', 'immersivny')
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--week-start", help="YYYY-MM-DD for the Monday of the week to load")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--source-run-id", default=DEFAULT_SOURCE_RUN_ID)
    parser.add_argument("--delete-existing", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(args.database_url)
    metric_ids = fetch_metric_ids(conn)
    requested_period_start = date.fromisoformat(args.week_start) if args.week_start else None

    report_rows: List[dict] = []
    insert_rows: List[dict] = []
    period_starts_to_delete = set()
    live_rows_by_key: Dict[Tuple[str, int], dict] = {}
    live_rows_loaded_for_unit_period: set[Tuple[str, date]] = set()

    for config in PLAN_CONFIGS:
        unit = config["unit"]
        plan = load_plan(config["plan_path"])
        period_start, period_end, staging_rows = fetch_week_rows(conn, unit, requested_period_start)
        if (unit, period_start) not in live_rows_loaded_for_unit_period:
            direct_live_rows = load_live_value_rows(period_start)
            if direct_live_rows:
                live_rows_by_key.update(direct_live_rows)
            google_live_rows = load_live_value_rows_from_google(config, plan, staging_rows)
            if google_live_rows:
                live_rows_by_key.update(google_live_rows)
            live_rows_loaded_for_unit_period.add((unit, period_start))
        period_starts_to_delete.add(period_start)

        for row_number, plan_row in plan.items():
            staging = staging_rows.get(row_number)
            live_row = live_rows_by_key.get((unit, row_number))
            base_report = {
                "sheet_unit": unit,
                "period_start": str(period_start),
                "period_end": str(period_end),
                "row_number": row_number,
                "col_a": plan_row.col_a,
                "col_b": plan_row.col_b,
                "ingestion_action": plan_row.action,
                "target_metric_or_metrics": plan_row.target,
                "source_system_override": plan_row.source_override,
            }

            if plan_row.action != "map_to_metric":
                report_rows.append({**base_report, "status": "skipped", "reason": "not_map_to_metric"})
                continue

            if should_skip_multi_target(plan_row):
                report_rows.append({**base_report, "status": "skipped", "reason": "multi_target_metric"})
                continue

            target_metric = split_targets(plan_row.target)[0]
            metric_id = metric_ids.get(target_metric)
            if not metric_id:
                report_rows.append({**base_report, "status": "skipped", "reason": "metric_missing_in_catalog"})
                continue

            fallback_used = False
            if not staging:
                staging = build_live_fallback_staging(row_number, live_row)
                if staging:
                    fallback_used = True
                else:
                    report_rows.append({**base_report, "status": "skipped", "reason": "missing_staging_row"})
                    continue

            if staging["value"] is None and not staging["value_raw"]:
                fallback_staging = build_live_fallback_staging(row_number, live_row)
                if fallback_staging:
                    staging = fallback_staging
                    fallback_used = True
                else:
                    report_rows.append({**base_report, "status": "skipped", "reason": "empty_value"})
                    continue

            if staging["value_type"] in {"date", "text"} and staging["value"] is None:
                fallback_staging = build_live_fallback_staging(row_number, live_row)
                if fallback_staging:
                    staging = fallback_staging
                    fallback_used = True
                else:
                    report_rows.append({**base_report, "status": "skipped", "reason": f"unsupported_value_type:{staging['value_type']}"})
                    continue

            business_unit = derive_business_unit(plan_row, unit)
            partner_name = derive_partner(plan_row)
            show_name = derive_show(plan_row, target_metric)
            channel_name = derive_channel(plan_row) if target_metric in {"Marketing costs"} else None

            # Keep source-share and some website fragments for later, until taxonomy is finalized.
            if target_metric == "Source share":
                report_rows.append({**base_report, "status": "skipped", "reason": "source_share_taxonomy_pending"})
                continue

            # B2B website traffic is sourced from Yandex Metrica on /corporative, not from the manual sheet snapshot.
            if target_metric == "Website visits" and business_unit == "b2b":
                report_rows.append({**base_report, "status": "skipped", "reason": "b2b_website_visits_use_yandex_metrica"})
                continue

            value_numeric = staging["value"]
            value_text = None
            value_raw = staging["value_raw"] or ""
            payload = {
                "loader": "import_live_weekly_manual_to_fact",
                "sheet_unit": unit,
                "target_metric": target_metric,
                "source_sheet_id": staging["source_sheet_id"],
                "source_gid": staging["source_gid"],
                "source_tab": staging["source_tab"],
                "fact_metrics_metric_group": staging["metric_group"],
                "fact_metrics_metric_name": staging["metric_name"],
                "fact_metrics_value_type": staging["value_type"],
                "fact_metrics_period_label": staging["period_label"],
                "plan_col_a": plan_row.col_a,
                "plan_col_b": plan_row.col_b,
                "plan_note": plan_row.note,
                "value_source": "live_sheet_fallback" if fallback_used else "fact_metrics_staging",
            }
            if staging.get("source_cell_a1"):
                source_cell_a1 = staging["source_cell_a1"]
            elif staging.get("col_order"):
                source_cell_a1 = build_sheet_cell_a1(row_number, int(staging["col_order"]))
            else:
                source_cell_a1 = None
            if staging.get("source_cell_url"):
                source_cell_url = staging["source_cell_url"]
            elif staging.get("source_sheet_id") and staging.get("source_gid") and staging.get("col_order"):
                source_cell_url = build_sheet_cell_url(
                    staging["source_sheet_id"],
                    staging["source_gid"],
                    staging.get("source_tab") or "",
                    row_number,
                    int(staging["col_order"]),
                )
            else:
                source_cell_url = None
            source_record_key = f"{unit}:row:{row_number}"
            insert_rows.append(
                build_insert_row(
                    metric_id=metric_id,
                    source_system="manual_table",
                    source_record_key=source_record_key,
                    source_run_id=args.source_run_id,
                    source_cell_a1=source_cell_a1,
                    source_cell_url=source_cell_url,
                    business_unit=business_unit,
                    show_name=show_name,
                    partner_name=partner_name,
                    channel_name=channel_name,
                    period_start=period_start,
                    period_end=period_end,
                    value_numeric=value_numeric,
                    value_text=value_text,
                    value_raw=value_raw,
                    payload=payload,
                )
            )
            if is_website_orders_reference_row(unit, staging, target_metric):
                website_orders_metric_id = metric_ids.get("Website orders")
                if website_orders_metric_id:
                    website_orders_payload = dict(payload)
                    website_orders_payload["target_metric"] = "Website orders"
                    website_orders_payload["metric_alias_reason"] = "site_orders_reference_row"
                    insert_rows.append(
                        build_insert_row(
                            metric_id=website_orders_metric_id,
                            source_system="manual_table",
                            source_record_key=f"{unit}:row:{row_number}:website_orders",
                            source_run_id=args.source_run_id,
                            source_cell_a1=source_cell_a1,
                            source_cell_url=source_cell_url,
                            business_unit=business_unit,
                            show_name=None,
                            partner_name=None,
                            channel_name=None,
                            period_start=period_start,
                            period_end=period_end,
                            value_numeric=value_numeric,
                            value_text=value_text,
                            value_raw=value_raw,
                            payload=website_orders_payload,
                        )
                    )
            report_rows.append(
                {
                    **base_report,
                    "status": "inserted",
                    "reason": "fallback_live_sheet" if fallback_used else "",
                    "business_unit": business_unit,
                    "show_name": show_name or "",
                    "partner_name": partner_name or "",
                    "channel_name": channel_name or "",
                    "source_cell_a1": source_cell_a1,
                    "source_cell_url": source_cell_url,
                    "value_numeric": str(value_numeric) if value_numeric is not None else "",
                }
            )

    with conn:
        with conn.cursor() as cur:
            if args.delete_existing:
                for period_start in sorted(period_starts_to_delete):
                    cur.execute(DELETE_SQL, {"source_run_id": args.source_run_id, "period_start": period_start})
            if insert_rows:
                execute_batch(cur, INSERT_SQL, insert_rows, page_size=200)

    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sheet_unit",
        "period_start",
        "period_end",
        "row_number",
        "col_a",
        "col_b",
        "ingestion_action",
        "target_metric_or_metrics",
        "source_system_override",
        "status",
        "reason",
        "business_unit",
        "show_name",
        "partner_name",
        "channel_name",
        "source_cell_a1",
        "source_cell_url",
        "value_numeric",
    ]
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)

    inserted = sum(1 for row in report_rows if row["status"] == "inserted")
    skipped = sum(1 for row in report_rows if row["status"] == "skipped")
    print(f"inserted={inserted} skipped={skipped} report={report_path}")


if __name__ == "__main__":
    main()
