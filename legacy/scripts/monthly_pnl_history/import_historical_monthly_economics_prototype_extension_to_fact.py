#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import csv
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import psycopg2
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials
from psycopg2.extras import Json, execute_batch


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
DEFAULT_MAPPING_PATH = ROOT / "artifacts" / "snapshots" / "historical_sheet_canonical_metric_mapping.csv"
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "run_reports" / "historical_monthly_economics_new_prototype_import_report.csv"
DEFAULT_GOOGLE_SERVICE_ACCOUNT_JSON = Path(
    os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_JSON",
        "/Users/Peter/Downloads/appointments-1084-0dcc0dd99d1b.json",
    )
)

SPREADSHEET_ID = "19Ssy4Esp0vG_7yIHA8mNpfuzjvko12TdQEklEPFxfC0"
SHEET_GID = "277036993"
SHEET_NAME = "ЭКОНОМИКА (P&L) - Новый прототип"
SOURCE_SYSTEM = "google_sheets_monthly_economics_historical"
SOURCE_RUN_ID = f"{SPREADSHEET_ID}:{SHEET_GID}"
MERGE_RULE_SUM = "sum"
TARGET_PERIODS = {
    date(2025, 4, 1),
    date(2025, 5, 1),
    date(2025, 6, 1),
}

INSERT_SQL = """
INSERT INTO fact_metric_observation (
    metric_id,
    rule_id,
    source_system,
    source_record_key,
    source_run_id,
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
    payload
)
VALUES (
    %(metric_id)s,
    NULL,
    %(source_system)s,
    %(source_record_key)s,
    %(source_run_id)s,
    %(business_unit)s,
    %(show_name)s,
    %(partner_name)s,
    %(channel_name)s,
    'month',
    %(period_start)s,
    %(period_end)s,
    %(value_numeric)s,
    NULL,
    %(value_raw)s,
    %(currency_code)s,
    FALSE,
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
    value_numeric = EXCLUDED.value_numeric,
    value_raw = EXCLUDED.value_raw,
    payload = EXCLUDED.payload,
    currency_code = EXCLUDED.currency_code,
    loaded_at = NOW()
"""

DELETE_SQL = """
DELETE FROM fact_metric_observation
WHERE source_system = %(source_system)s
  AND source_run_id = %(source_run_id)s
"""


@dataclass(frozen=True)
class MappingRow:
    layer: str
    canonical_metric: str
    business_unit: str
    show: str
    channel: str
    agent: str
    merge_rule: str
    mapping_status: str
    mapping_note: str


def normalize_text(value: str) -> str:
    return " ".join((value or "").replace("\xa0", " ").split()).strip()


def normalize_source_label(value: str) -> str:
    return normalize_text(value).rstrip(":")


def col_to_a1(col_number_1_based: int) -> str:
    result = ""
    num = col_number_1_based
    while num > 0:
        num, rem = divmod(num - 1, 26)
        result = chr(65 + rem) + result
    return result


def sheet_cell_a1(row_number_1_based: int, col_number_1_based: int) -> str:
    return f"{col_to_a1(col_number_1_based)}{row_number_1_based}"


def sheet_cell_url(row_number_1_based: int, col_number_1_based: int) -> str:
    a1 = sheet_cell_a1(row_number_1_based, col_number_1_based)
    return (
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
        f"?gid={SHEET_GID}#gid={SHEET_GID}&range={SHEET_NAME}!{a1}"
    )


def month_end(period_start: date) -> date:
    return date(period_start.year, period_start.month, calendar.monthrange(period_start.year, period_start.month)[1])


def build_google_session(service_account_json: Path) -> AuthorizedSession:
    creds = Credentials.from_service_account_file(
        str(service_account_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return AuthorizedSession(creds)


def fetch_range(session: AuthorizedSession, render_option: str, max_row: int, max_col: int) -> list[list[str]]:
    end_col = col_to_a1(max_col)
    data_range = f"{SHEET_NAME}!A1:{end_col}{max_row}"
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{data_range}"
    response = session.get(
        url,
        params={
            "majorDimension": "ROWS",
            "valueRenderOption": render_option,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json().get("values", [])


def sheet_value(grid: list[list[str]], row_1_based: int, col_1_based: int) -> str:
    row_idx = row_1_based - 1
    col_idx = col_1_based - 1
    if row_idx < 0 or row_idx >= len(grid):
        return ""
    row = grid[row_idx]
    if col_idx < 0 or col_idx >= len(row):
        return ""
    value = row[col_idx]
    return "" if value is None else str(value)


def parse_target_month_columns(formatted_grid: list[list[str]], max_col: int) -> list[tuple[int, date, str]]:
    result: list[tuple[int, date, str]] = []
    for col in range(2, max_col + 1):
        raw_date = sheet_value(formatted_grid, 2, col).strip()
        raw_label = sheet_value(formatted_grid, 3, col).strip()
        if not raw_date:
            continue
        try:
            period_start = datetime.strptime(raw_date, "%d.%m.%Y").date()
        except ValueError:
            continue
        if period_start not in TARGET_PERIODS:
            continue
        result.append((col, period_start, raw_label or raw_date))
    return result


def should_keep_period(period_start: date, month_start: date | None, month_end_value: date | None) -> bool:
    if month_start and period_start < month_start:
        return False
    if month_end_value and period_start > month_end_value:
        return False
    return True


def parse_numeric(value: str) -> Optional[Decimal]:
    raw = (value or "").replace("\xa0", "").replace(" ", "").strip()
    if raw in {"", "-", "—"}:
        return None
    raw = raw.replace("₽", "")
    if raw.lower().startswith("р."):
        raw = raw[2:]
    elif raw.lower().startswith("р"):
        raw = raw[1:]
    raw = raw.strip()
    if raw.endswith("%"):
        raw = raw[:-1].replace(",", ".")
        try:
            return Decimal(raw) / Decimal("100")
        except InvalidOperation:
            return None
    raw = raw.replace(",", ".")
    if raw.startswith("(") and raw.endswith(")"):
        raw = f"-{raw[1:-1]}"
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def decimal_to_raw(value: Decimal) -> str:
    return format(value.normalize(), "f")


def normalize_dimension(value: str, kind: str) -> Optional[str]:
    normalized = (value or "").strip()
    if not normalized or normalized.lower() == "general":
        return None
    if kind == "show":
        mapping = {
            "certificate": "Certificate",
            "sd": "SD",
            "online": "Online",
        }
        return mapping.get(normalized.lower(), normalized)
    return normalized


def load_mapping(path: Path) -> dict[tuple[str, str], MappingRow]:
    mapping: dict[tuple[str, str], MappingRow] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (
                normalize_text(row.get("source_business_unit", "")),
                normalize_source_label(row.get("source_label", "")),
            )
            if not key[1]:
                continue
            mapping[key] = MappingRow(
                layer=(row.get("layer") or "").strip().lower(),
                canonical_metric=(row.get("canonical_metric") or "").strip(),
                business_unit=(row.get("business_unit") or "").strip(),
                show=(row.get("show") or "").strip(),
                channel=(row.get("channel") or "").strip(),
                agent=(row.get("agent") or "").strip(),
                merge_rule=(row.get("merge_rule") or "").strip().lower(),
                mapping_status=(row.get("mapping_status") or "").strip().lower(),
                mapping_note=(row.get("mapping_note") or "").strip(),
            )
    return mapping


def infer_section(row_number: int, label: str, current: str) -> str:
    normalized = normalize_source_label(label)
    if normalized == "МОРФЕУС МОСКВА, ФРАНШИЗА И КОРПОРАТЫ":
        return "moscow"
    if normalized == "МОРФЕУС САНКТ-ПЕТЕРБУРГ":
        return "spb"
    if row_number >= 214:
        return "summary"
    return current


def infer_source_business_unit(section: str, label: str, row_number: int) -> str:
    normalized = normalize_source_label(label)
    lower = normalized.lower()

    franchise_labels = {
        "З/п запуск партнеров франшиза",
        "Затраты франшиза Китай",
        "Затраты на реквизит для партнеров франшиза",
        "Европейская франшиза",
        "Франшиза Китай",
    }
    b2b_labels = {
        "Реализация - B2B",
        "Спецпроекты_классический репертуар",
        "Спецпроекты_СД",
        "Спецпроекты_онлайн",
        "Спецпроекты (корпоративы)",
        "З/п бонус админа_корпоратив",
        "З/п бонус админа_корпоратив театр",
        "B2B_Участие в Сцене",
        "Спецпроекты_классический репуртуар_з/п актеров",
        "Спецпроекты_СД_з/п актеров",
        "Другие затраты_Спецпроекты СД",
        "Спецпроекты_онлайн_з/п актеров",
        "B2B корпоративы з/п фикс",
        "B2B директор фикс",
        "B2B общие расходы на реализацию корпоратива",
        "B2B корпоративы з/п актеров",
        "B2B корпоративы з/п актеров ",
        "B2B корпоративы з/п креативная команда",
        "B2B корпоративы костюмы и реквизит",
        "B2B корпоративы разные услуги",
        "Общие расходы спецпроекты_корпоративы",
    }

    if section == "summary":
        return "Общее"
    if section == "spb":
        if normalized in {"Спецпроекты (корпоративы)", "Общие расходы спецпроекты_корпоративы"}:
            return "B2B"
        return "СПб"
    if section == "moscow":
        if normalized in franchise_labels or lower.startswith("франшиза"):
            return "Франшиза"
        if normalized in b2b_labels or normalized.startswith("B2B ") or normalized.startswith("Спецпроекты_"):
            return "B2B"
        return "Москва"
    return "Общее"


def direct_mapping(source_bu: str, label: str, row_number: int, section: str, leaf_only: bool = False) -> Optional[MappingRow]:
    normalized = normalize_source_label(label)
    source_bu = normalize_text(source_bu)
    if leaf_only and normalized in {
        "Итого расходы на маркетинг",
        "Итого переменные расходы",
        "Итого постоянные расходы",
        "Переменные расходы",
        "Постоянные расходы",
        "Постоянные расходы Мск",
    }:
        return MappingRow("exclude", "", "", "", "", "", "", "mapped_direct", "excluded subtotal row in leaf-only mode")
    if section == "spb":
        if row_number == 149:
            return MappingRow("fact", "Number of shows", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
        if row_number == 150:
            return MappingRow("fact", "Number of show visitors", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
        if row_number == 151:
            return MappingRow("calc", "Средняя загрузка шоу (по факту дошедшие зрители)", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
        if row_number == 152:
            return MappingRow("calc", "Средняя загрузка шоу (по факту дошедшие зрители)", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
        if row_number == 153:
            return MappingRow("fact", "Number of shows", "b2c_spb", "sd", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
        if row_number == 154:
            return MappingRow("fact", "Number of show visitors", "b2c_spb", "sd", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
        if row_number == 155:
            return MappingRow("calc", "Средняя загрузка шоу (по факту дошедшие зрители)", "b2c_spb", "sd", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
        if row_number == 156:
            return MappingRow("calc", "Средняя загрузка шоу (по факту дошедшие зрители)", "b2c_spb", "sd", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")

    if normalized == "Реализация - B2B":
        return MappingRow("fact", "Revenue", "b2b", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Выручка_сертификаты и маски":
        return MappingRow(
            "exclude",
            "",
            "",
            "",
            "",
            "",
            "",
            "mapped_direct",
            "use only `Выручка_сертификаты с понижающем кэфом` for certificate revenue",
        )
    if normalized == "Доход от депозита":
        return MappingRow("fact", "Other income - Deposit interest", "general", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Спецпроекты (корпоративы)":
        return MappingRow("fact", "Revenue", "b2b", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized in {"ЗП актеров по начислению_ классический репертуар", "ЗП актеров по начислению", "Выплаты актерам за разные услуги"}:
        business_unit = "b2c_spb" if source_bu == "СПб" else "b2c_moscow"
        return MappingRow("fact", "Costs - Salary variable", business_unit, "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized in {"ЗП актеров-Судный день", "ЗП СД"}:
        business_unit = "b2c_spb" if source_bu == "СПб" else "b2c_moscow"
        return MappingRow("fact", "Costs - Salary variable", business_unit, "sd", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized in {"З/п бонус админа_корпоратив", "З/п бонус админа_корпоратив театр", "B2B корпоративы з/п фикс", "B2B директор фикс"}:
        return MappingRow("fact", "Costs - Salary fixed", "b2b", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized in {"B2B общие расходы на реализацию корпоратива", "B2B корпоративы костюмы и реквизит", "Общие расходы спецпроекты_корпоративы"}:
        return MappingRow("fact", "Show production costs", "b2b", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized in {"B2B корпоративы з/п актеров", "B2B корпоративы з/п креативная команда"}:
        return MappingRow("fact", "Costs - Salary variable", "b2b", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "B2B корпоративы разные услуги":
        return MappingRow("fact", "Other expenses", "b2b", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Митя_Бонус СД":
        return MappingRow("fact", "Costs - Salary variable", "b2c_spb", "sd", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "B2B_Участие в Сцене":
        return MappingRow("fact", "Marketing costs", "b2b", "general", "pr", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Комиссии за снятие наличных и переводы физическим лицам":
        return MappingRow("fact", "Cost article - Комиссия", "general", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized in {"Комиссии платежных систем", "Комиссии платежных систем (агрегаторы)", "Комиссии платежных систем (агрегаторы_ДТЗК)"} and source_bu == "СПб":
        return MappingRow("fact", "Cost article - Комиссия", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Налог6%" and source_bu == "СПб":
        return MappingRow("fact", "Cost article - Налог на прибыль (доходы)", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Налог страховые взносы" and source_bu == "СПб":
        return MappingRow("fact", "Cost article - Страховые взносы", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Возвраты" and source_bu == "СПб":
        return MappingRow("fact", "Returns amount", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Прочие расходы" and source_bu == "СПб":
        return MappingRow("fact", "Other expenses", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Прочие расходы" and source_bu == "Москва":
        return MappingRow("fact", "Other expenses", "b2c_moscow", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Дизайн, полиграфия":
        return MappingRow("fact", "Marketing costs", "b2c_spb", "general", "pos", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Дизайн, новый сайт, полиграфия, цели и seo":
        return MappingRow("fact", "Marketing costs", "b2c_moscow", "general", "other", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "ЗП  худрука, админов  и ХПЧ":
        return MappingRow("fact", "Costs - Salary fixed", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "ЗП худрука, админов и ХПЧ":
        return MappingRow("fact", "Costs - Salary fixed", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Электронные  и бухгалтерские сервисы":
        return MappingRow("fact", "Services and setup costs", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Электронные и бухгалтерские сервисы":
        return MappingRow("fact", "Services and setup costs", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Логистика (+командировки Москвы и Питера)":
        return MappingRow("fact", "Business travel costs", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Логистика":
        business_unit = "b2c_spb" if source_bu == "СПб" else "b2c_moscow"
        return MappingRow("fact", "Variable logistics costs", business_unit, "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Маркетинг":
        return MappingRow("fact", "Marketing costs", "b2c_spb", "general", "other", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Итого расходы на маркетинг":
        business_unit = "b2c_spb" if source_bu == "СПб" else "b2c_moscow"
        return MappingRow("fact", "Marketing costs", business_unit, "general", "total", "general", MERGE_RULE_SUM, "mapped_direct", "observed subtotal by marketing channels")
    if normalized == "PR":
        return MappingRow("fact", "Marketing costs", "b2c_spb", "general", "pr", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Кросс-промо и SEO":
        return MappingRow("fact", "Marketing costs", "b2c_spb", "general", "pr", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Прочие расходы на рекламу":
        return MappingRow("fact", "Marketing costs", "b2c_spb", "general", "other", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Контекстная реклама_ведение_ритейл":
        return MappingRow("fact", "Marketing costs", "b2c_spb", "general", "direct", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Контекст_бюджет_ритейл":
        return MappingRow("fact", "Marketing costs", "b2c_spb", "general", "direct", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Инстаграм_ведение":
        return MappingRow("fact", "Marketing costs", "b2c_spb", "general", "smm", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Размещение у блогеров, афишах, дзене, паблики":
        return MappingRow("fact", "Marketing costs", "b2c_spb", "general", "pr", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Разработка и IT" and source_bu == "СПб":
        return MappingRow("fact", "Cost article - IT ФОТ", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Подарки" and source_bu == "СПб":
        return MappingRow("fact", "Team expenses", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Реализация шоу" and source_bu == "СПб":
        return MappingRow("fact", "Revenue", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Реализация СД" and source_bu == "СПб":
        return MappingRow("fact", "Revenue", "b2c_spb", "sd", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Выручка_сертификаты с понижающем кэфом" and source_bu == "СПб":
        return MappingRow("fact", "Revenue", "b2c_spb", "certificate", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Итого переменные расходы":
        business_unit = "b2c_spb" if source_bu == "СПб" else "b2c_moscow"
        return MappingRow("fact", "Variable costs", business_unit, "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Итого постоянные расходы":
        business_unit = "b2c_spb" if source_bu == "СПб" else "b2c_moscow"
        return MappingRow("fact", "Fixed costs", business_unit, "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Переменные расходы" and source_bu == "СПб":
        return MappingRow("fact", "Variable costs", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Постоянные расходы" and source_bu == "СПб":
        return MappingRow("fact", "Fixed costs", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Постоянные расходы Мск":
        return MappingRow("fact", "Fixed costs", "b2c_moscow", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Продвижение франшизы":
        return MappingRow("fact", "Marketing costs", "b2c_moscow", "general", "other", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Накрутка отзывов":
        return MappingRow("fact", "Marketing costs", "b2c_moscow", "general", "pr", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if source_bu == "Москва" and normalized in {
        "Доработка софта, озвучка и пр",
        "Обучение",
        "Реквизит и оборудование",
        "Сценарии",
        "СRM",
        "CRM",
        "Реклама",
        "Оборудование и ремонт",
    }:
        return MappingRow("exclude", "", "", "", "", "", "", "mapped_direct", "excluded because `Итого, расходы инвестиции Москва` is the investment subtotal for Moscow")
    if normalized == "Разработка и IT" and source_bu == "Москва":
        return MappingRow("fact", "Cost article - IT ФОТ", "b2c_moscow", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Неопознанные пока траты":
        return MappingRow("fact", "Other expenses", "b2c_moscow", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Инвестии в Петербург":
        return MappingRow("fact", "Investment costs", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Европейская франшиза":
        return MappingRow("fact", "Revenue", "franchise", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Аренда помещения и коммуналка":
        return MappingRow("fact", "Venue and office costs", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "ЗП директор фикс":
        return MappingRow("fact", "Costs - Salary fixed", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Уборка помещения":
        return MappingRow("fact", "Cost article - Уборка", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Ремонт помещения":
        return MappingRow("fact", "Cost article - Ремонт и обслуживание", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Хоз.расходы на помещение":
        return MappingRow("fact", "Cost article - Расходники (офисные)", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Расходы на проведение спектаклей":
        return MappingRow("fact", "Show production costs", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Реквизит для проведения спектаклей":
        return MappingRow("fact", "Cost article - Реквизит/костюмы", "b2c_spb", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized in {
        "Прибыль_театр Москва",
        "Прибыль_театр Петербург",
        "Прибыль_франшиза",
        "Прибыль_Китай",
        "Прибыль_корпоратив Москва",
        "Прибыль_корпоратив Петербург",
        "Прибыль_корпоратив общая",
        "Прибыль от европейской франшизы",
    }:
        return MappingRow("fact", "Net profit", "general", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Прибыль для основателей":
        return MappingRow("fact", "Net profit", "total", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized == "Директорский процент":
        return MappingRow("fact", "Cost article - Директорский процент", "total", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "historical owner distribution cost article used in total net profit bridge")
    if normalized == "Итого, процент директора":
        return MappingRow("fact", "Cost article - Директорский процент", "total", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "historical owner distribution cost article used in total net profit bridge")
    if normalized == "Общая прибыль":
        return MappingRow("exclude", "", "", "", "", "", "", "mapped_direct", "")
    if normalized == "Годовые бонусы":
        return MappingRow("fact", "Annual bonuses", "general", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    if normalized in {
        "Питер",
        "Театр Москва",
        "Театр Петербург",
        "Корпоратив",
        "Франшиза",
        "Китай",
        "дата вывода",
        "Отложено на депозит по итогу месяца",
        "Отложено на депозит накопительным итогом за год",
        "Снято с депозита и переведено наличными",
        "Сальдо итоговое",
        "Дополнительно",
        "Процент выполнения годового плана",
        "Театр Москва накопительным итогом",
        "Театр Петербург накопительным итогом",
        "Франшиза (без учета Китая и Чехии)",
        "Франшиза накопительным итогом",
        "Корпоратив накопительным итогом",
        "Прибыль до выплаты акционерам,развития и % директора",
        "12% прибыли",
        "5 % прибыли",
        "10 % прибыли",
        "% от выручки",
        "Расчетная выручка периода (по реализации)",
        "Маржинальный доход",
        "% переменных расходов к выручке",
        "% к марже",
        "% к выручке",
        "%з/п исполнителей в бюджете на маркетинг от всего маркетинга",
        "%постоянных расходов к выручке",
        "% отнесения на выручку",
        "% ФОТ в выручке ШОУ",
        "% ФОТ в выручке CД",
        "Среднее количество гостей",
        "%заполняемости",
        "Зарплаты на 1 шоу",
    }:
        return MappingRow("exclude", "", "", "", "", "", "", "mapped_direct", "")
    if normalized == "Вывод для ПСН (депозитный счет):":
        return MappingRow("fact", "Dividends", "general", "general", "general", "general", MERGE_RULE_SUM, "mapped_direct", "")
    return None


def should_skip_row(label: str) -> bool:
    normalized = normalize_source_label(label)
    if not normalized:
        return True
    section_headers = {
        "МОРФЕУС МОСКВА, ФРАНШИЗА И КОРПОРАТЫ",
        "МОРФЕУС САНКТ-ПЕТЕРБУРГ",
        "ИТОГОВАЯ ПРИБЫЛЬ ПО НАПРАВЛЕНИЯМ",
        "СУММА К ПЕРЕВОДУ ПСН ПО РЕЗУЛЬТАТАМ МЕСЯЦА",
        "СУММА К ПЕРЕВОДУ НАКОПИТЕЛЬНЫМ ИТОГОМ ЗА ГОД",
        "ГОДОВЫЕ БОНУСЫ",
        "СУММА ПЕРЕВЕДЕННАЯ ПО ИТОГУ МЕСЯЦА",
        "СУММА ПЕРЕВЕДЕННАЯ НАКОПИТЕЛЬНЫМ ИТОГОМ ЗА ГОД",
    }
    return normalized in section_headers


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "status",
                "period_start",
                "source_row_number",
                "source_business_unit",
                "source_label",
                "canonical_metric",
                "business_unit",
                "show",
                "channel",
                "agent",
                "cell_a1",
                "value_raw",
                "value_numeric",
                "reason",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--mapping-path", default=str(DEFAULT_MAPPING_PATH))
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--service-account-json", default=str(DEFAULT_GOOGLE_SERVICE_ACCOUNT_JSON))
    parser.add_argument("--source-system", default=SOURCE_SYSTEM)
    parser.add_argument("--source-run-id", default=SOURCE_RUN_ID)
    parser.add_argument("--month-start", help="Optional YYYY-MM-DD lower month bound")
    parser.add_argument("--month-end", help="Optional YYYY-MM-DD upper month bound")
    parser.add_argument("--leaf-only", action="store_true")
    parser.add_argument("--delete-existing", action="store_true")
    args = parser.parse_args()

    mapping = load_mapping(Path(args.mapping_path))
    report_path = Path(args.report_path)
    service_account_json = Path(args.service_account_json)
    source_system = args.source_system
    source_run_id = args.source_run_id
    month_start = date.fromisoformat(args.month_start) if args.month_start else None
    month_end_value = date.fromisoformat(args.month_end) if args.month_end else None

    session = build_google_session(service_account_json)
    max_row = 280
    max_col = 74
    formatted_grid = fetch_range(session, "FORMATTED_VALUE", max_row, max_col)
    formula_grid = fetch_range(session, "FORMULA", max_row, max_col)
    month_columns = parse_target_month_columns(formatted_grid, max_col)

    resolved_rows = []
    section = "moscow"
    report_rows: list[dict[str, str]] = []

    for row_number in range(4, max_row + 1):
        label = sheet_value(formatted_grid, row_number, 1)
        section = infer_section(row_number, label, section)
        normalized_label = normalize_source_label(label)
        if should_skip_row(normalized_label):
            continue
        source_bu = infer_source_business_unit(section, normalized_label, row_number)
        key = (normalize_text(source_bu), normalized_label)
        mapping_row = mapping.get(key)
        direct_row = direct_mapping(source_bu, normalized_label, row_number, section, args.leaf_only)
        if direct_row is not None:
            mapping_row = direct_row

        if mapping_row is None:
            report_rows.append(
                {
                    "status": "unmapped_row",
                    "period_start": "",
                    "source_row_number": str(row_number),
                    "source_business_unit": source_bu,
                    "source_label": normalized_label,
                    "canonical_metric": "",
                    "business_unit": "",
                    "show": "",
                    "channel": "",
                    "agent": "",
                    "cell_a1": "",
                    "value_raw": "",
                    "value_numeric": "",
                    "reason": "no_mapping_found",
                }
            )
            continue
        if args.leaf_only and (
            (mapping_row.business_unit or "").strip().lower() in {"", "general", "total"}
            and mapping_row.canonical_metric != "Cost article - Директорский процент"
        ):
            continue
        if mapping_row.layer != "fact" or not mapping_row.canonical_metric or mapping_row.merge_rule != MERGE_RULE_SUM:
            continue
        if mapping_row.mapping_status and not mapping_row.mapping_status.startswith("mapped"):
            continue
        resolved_rows.append((row_number, source_bu, normalized_label, mapping_row))

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT metric_id, metric_name, value_kind FROM metric_catalogue")
                metric_meta = {
                    metric_name: {"metric_id": metric_id, "value_kind": value_kind}
                    for metric_id, metric_name, value_kind in cur.fetchall()
                }

                missing_metrics = sorted(
                    {row.canonical_metric for _, _, _, row in resolved_rows if row.canonical_metric not in metric_meta}
                )
                if missing_metrics:
                    raise RuntimeError(f"Missing metrics in metric_catalogue: {missing_metrics}")

                if args.delete_existing:
                    delete_sql = DELETE_SQL
                    delete_params = {
                        "source_system": source_system,
                        "source_run_id": source_run_id,
                    }
                    if month_start:
                        delete_sql += "\n  AND period_start >= %(month_start)s"
                        delete_params["month_start"] = month_start
                    if month_end_value:
                        delete_sql += "\n  AND period_start <= %(month_end)s"
                        delete_params["month_end"] = month_end_value
                    cur.execute(delete_sql, delete_params)

                aggregates: dict[tuple, dict] = {}

                for row_number, source_bu, source_label, mapping_row in resolved_rows:
                    metric_info = metric_meta[mapping_row.canonical_metric]
                    for col_1_based, period_start, month_label in month_columns:
                        if not should_keep_period(period_start, month_start, month_end_value):
                            continue
                        formatted_value = sheet_value(formatted_grid, row_number, col_1_based)
                        formula_value = sheet_value(formula_grid, row_number, col_1_based)
                        numeric_value = parse_numeric(formatted_value)
                        cell_mode = "formula" if formula_value.startswith("=") else "input"
                        cell_a1 = sheet_cell_a1(row_number, col_1_based)
                        if numeric_value is None:
                            report_rows.append(
                                {
                                    "status": "skipped",
                                    "period_start": period_start.isoformat(),
                                    "source_row_number": str(row_number),
                                    "source_business_unit": source_bu,
                                    "source_label": source_label,
                                    "canonical_metric": mapping_row.canonical_metric,
                                    "business_unit": mapping_row.business_unit,
                                    "show": mapping_row.show,
                                    "channel": mapping_row.channel,
                                    "agent": mapping_row.agent,
                                    "cell_a1": cell_a1,
                                    "value_raw": formatted_value,
                                    "value_numeric": "",
                                    "reason": "blank_or_non_numeric",
                                }
                            )
                            continue

                        show_name = normalize_dimension(mapping_row.show, "show")
                        channel_name = normalize_dimension(mapping_row.channel, "channel")
                        partner_name = normalize_dimension(mapping_row.agent, "agent")
                        business_unit = (mapping_row.business_unit or "").strip() or None
                        period_end = month_end(period_start)

                        aggregate_key = (
                            mapping_row.canonical_metric,
                            business_unit,
                            show_name,
                            channel_name,
                            partner_name,
                            period_start,
                            period_end,
                        )
                        aggregate = aggregates.setdefault(
                            aggregate_key,
                            {
                                "metric_id": metric_info["metric_id"],
                                "metric_name": mapping_row.canonical_metric,
                                "value_kind": metric_info["value_kind"],
                                "business_unit": business_unit,
                                "show_name": show_name,
                                "channel_name": channel_name,
                                "partner_name": partner_name,
                                "period_start": period_start,
                                "period_end": period_end,
                                "total": Decimal("0"),
                                "source_rows": [],
                                "source_modes": set(),
                                "source_cells": [],
                                "source_cell_urls": [],
                                "source_labels": [],
                                "source_business_units": [],
                                "month_labels": set(),
                                "source_value_details": [],
                            },
                        )
                        aggregate["total"] += numeric_value
                        aggregate["source_rows"].append(row_number)
                        aggregate["source_modes"].add(cell_mode)
                        aggregate["source_cells"].append(cell_a1)
                        aggregate["source_cell_urls"].append(sheet_cell_url(row_number, col_1_based))
                        aggregate["source_labels"].append(source_label)
                        aggregate["source_business_units"].append(source_bu)
                        aggregate["month_labels"].add(month_label)
                        aggregate["source_value_details"].append(
                            {
                                "row_number": row_number,
                                "cell_a1": cell_a1,
                                "cell_url": sheet_cell_url(row_number, col_1_based),
                                "raw_value": formatted_value,
                                "numeric_value": decimal_to_raw(numeric_value),
                                "formula_or_input": cell_mode,
                                "source_label": source_label,
                                "source_business_unit": source_bu,
                                "month_label": month_label,
                                "period_start": period_start.isoformat(),
                            }
                        )
                        report_rows.append(
                            {
                                "status": "aggregated",
                                "period_start": period_start.isoformat(),
                                "source_row_number": str(row_number),
                                "source_business_unit": source_bu,
                                "source_label": source_label,
                                "canonical_metric": mapping_row.canonical_metric,
                                "business_unit": mapping_row.business_unit,
                                "show": mapping_row.show,
                                "channel": mapping_row.channel,
                                "agent": mapping_row.agent,
                                "cell_a1": cell_a1,
                                "value_raw": formatted_value,
                                "value_numeric": decimal_to_raw(numeric_value),
                                "reason": "",
                            }
                        )

                inserts = []
                def aggregate_sort_key(item):
                    metric_name, business_unit, show_name, channel_name, partner_name, period_start, period_end = item[0]
                    return (
                        metric_name or "",
                        business_unit or "",
                        show_name or "",
                        channel_name or "",
                        partner_name or "",
                        period_start.isoformat(),
                        period_end.isoformat(),
                    )

                for (
                    metric_name,
                    business_unit,
                    show_name,
                    channel_name,
                    partner_name,
                    period_start,
                    period_end,
                ), aggregate in sorted(aggregates.items(), key=aggregate_sort_key):
                    source_record_key = (
                        f"historical_monthly_economics_new_prototype:"
                        f"{metric_name}:"
                        f"{business_unit or 'none'}:"
                        f"{show_name or 'none'}:"
                        f"{channel_name or 'none'}:"
                        f"{partner_name or 'none'}:"
                        f"{period_start.isoformat()}"
                    )
                    total = aggregate["total"]
                    value_raw = decimal_to_raw(total)
                    currency_code = "RUB" if aggregate["value_kind"] == "currency" else None
                    payload = {
                        "sheet_role": "historical_monthly_economics_new_prototype_extension",
                        "sheet_id": SPREADSHEET_ID,
                        "sheet_gid": SHEET_GID,
                        "sheet_name": SHEET_NAME,
                        "sheet_url": f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit?gid={SHEET_GID}#gid={SHEET_GID}",
                        "source_rows": sorted(set(aggregate["source_rows"])),
                        "source_labels": sorted(set(aggregate["source_labels"])),
                        "source_business_units": sorted(set(aggregate["source_business_units"])),
                        "source_cells": sorted(set(aggregate["source_cells"])),
                        "source_cell_urls": sorted(set(aggregate["source_cell_urls"])),
                        "source_modes": sorted(aggregate["source_modes"]),
                        "source_month_labels": sorted(aggregate["month_labels"]),
                        "source_value_details": aggregate["source_value_details"],
                        "merge_rule": MERGE_RULE_SUM,
                        "mapping_file": str(args.mapping_path),
                    }
                    inserts.append(
                        {
                            "metric_id": aggregate["metric_id"],
                            "source_system": source_system,
                            "source_record_key": source_record_key,
                            "source_run_id": source_run_id,
                            "business_unit": business_unit,
                            "show_name": show_name,
                            "partner_name": partner_name,
                            "channel_name": channel_name,
                            "period_start": period_start,
                            "period_end": period_end,
                            "value_numeric": total,
                            "value_raw": value_raw,
                            "currency_code": currency_code,
                            "payload": Json(payload),
                        }
                    )

                execute_batch(cur, INSERT_SQL, inserts, page_size=200)

                for insert in inserts:
                    metric_name = next(
                        name
                        for name, meta in metric_meta.items()
                        if meta["metric_id"] == insert["metric_id"]
                    )
                    report_rows.append(
                        {
                            "status": "inserted",
                            "period_start": insert["period_start"].isoformat(),
                            "source_row_number": "",
                            "source_business_unit": insert["business_unit"] or "",
                            "source_label": "",
                            "canonical_metric": metric_name,
                            "business_unit": insert["business_unit"] or "",
                            "show": insert["show_name"] or "",
                            "channel": insert["channel_name"] or "",
                            "agent": insert["partner_name"] or "",
                            "cell_a1": "",
                            "value_raw": insert["value_raw"],
                            "value_numeric": insert["value_raw"],
                            "reason": "",
                        }
                    )

                write_report(report_path, report_rows)
                print(
                    json.dumps(
                        {
                            "inserted_rows": len(inserts),
                            "aggregated_source_rows": len([row for row in report_rows if row["status"] == "aggregated"]),
                            "unmapped_rows": len([row for row in report_rows if row["status"] == "unmapped_row"]),
                            "report_path": str(report_path),
                            "source_run_id": source_run_id,
                            "periods": [d.isoformat() for d in sorted(TARGET_PERIODS)],
                        },
                        ensure_ascii=False,
                    )
                )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
