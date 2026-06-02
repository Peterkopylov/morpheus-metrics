#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
WORKSHEET_NAME = "Статьи по периодам с прибылью"
PLANFACT_REFERENCE_DOC = "/Users/Peter/Documents/Morpheus Metrics/docs/planfact_monthly_pnl_fact_ingestion.md"
PLANFACT_HOW_COUNTED = "Imported from monthly PlanFact P&L report workbook by row label, business unit, and month"

# Important maintenance rule:
# when new PlanFact P&L row labels appear, we first update the canonical
# P&L hierarchy in `generated/pnl_structure_mapping_canonical.csv`, then update
# this row-label mapping, and only then reimport. The importer should not drift
# ahead of the declared P&L structure.


DEFAULT_WORKBOOK_PATHS = [
    Path("/Users/Peter/Downloads/Отчет о прибылях и убытках по периоду (5).xlsx"),
    Path("/Users/Peter/Downloads/Отчет о прибылях и убытках по периоду (7).xlsx"),
    Path("/Users/Peter/Downloads/Отчет о прибылях и убытках по периоду (6).xlsx"),
    Path("/Users/Peter/Downloads/Отчет о прибылях и убытках по периоду (8).xlsx"),
    Path("/Users/Peter/Downloads/B2B.xlsx"),
    Path("/Users/Peter/Downloads/Отчет о прибылях и убытках по периоду (9).xlsx"),
]

BUSINESS_UNIT_BY_WORKBOOK_NAME = {
    "Отчет о прибылях и убытках по периоду (5).xlsx": "total",
}


BUSINESS_UNIT_BY_PROJECT_LABEL = {
    "Общие [B2C]": "general",
    "Москва [B2C]": "b2c_moscow",
    "Санкт-Петербург [B2C]": "b2c_spb",
    "Корпоративы [B2B], Склад [B2B]": "b2b",
    "Франшиза [Проекты без группы]": "franchise",
}


MONTH_LABELS = {
    "авг 25": "2025-08-01",
    "сен 25": "2025-09-01",
    "окт 25": "2025-10-01",
    "ноя 25": "2025-11-01",
    "дек 25": "2025-12-01",
    "янв 26": "2026-01-01",
    "фев 26": "2026-02-01",
    "мар 26": "2026-03-01",
    "апр 26": "2026-04-01",
}


# Revenue stays one canonical metric, but for PlanFact we now import only the
# top observed subtotal row `Выручка`. Child revenue rows are skipped to avoid
# double counting the same monthly revenue inside one business unit.
FACT_ROW_MAPPING = {
    "Выручка": "Revenue",
    "Переменные расходы": "Variable costs",
    "Постоянные расходы": "Fixed costs",
    "Инвестиции": "Investment costs",
    "Основные расходы": "Operating expenses",
    "ФОТ": "Salary costs",
    "ФОТ - Переменные": "Costs - Salary variable",
    "ФОТ - Постоянные": "Costs - Salary fixed",
    "Другое ФОТ": "Cost article - Другое ФОТ",
    "IT ФОТ": "Cost article - IT ФОТ",
    "Управленческий персонал ФОТ": "Cost article - Управленческий персонал ФОТ",
    "Актёры ФОТ": "Cost article - Актёры ФОТ",
    "Административный персонал ФОТ": "Cost article - Административный персонал ФОТ",
    "Корпоративы фикс": "Cost article - Корпоративы фикс",
    "Ремонт в Малом зале": "Cost article - Ремонт в Малом зале",
    "Новый спектакль": "Cost article - Новый спектакль",
    "ПЕРЕЕЗД": "Relocation costs",
    "Техника": "Cost article - Техника",
    "Свет/Мебель/Предметы интерьера": "Cost article - Свет/Мебель/Предметы интерьера",
    "Ремонт/Стройка/Стройматериалы": "Cost article - Ремонт/Стройка/Стройматериалы",
    "ПРЕМИИ 2025": "Annual bonuses",
    "Премии управленч персонал": "Cost article - Премии управленч персонал",
    "Премии административный персонал": "Cost article - Премии административный персонал",
    "Премии актёры": "Cost article - Премии актёры",
    "Корпоративы ЗП проектные": "Costs - Salary variable",
    "Агентские": "Cost article - Агентские",
    "Услуги типографии": "Cost article - Услуги типографии",
    "Маркетинг и реклама - Услуги типографии": "Marketing costs",
    "Маркетинг и реклама - Агентские": "Marketing costs",
    "Маркетинг и реклама - PR и отзывы": "Marketing costs",
    "Маркетинг и реклама - SMM": "Marketing costs",
    "Маркетинг и реклама - Директ": "Marketing costs",
    "Маркетинг и реклама - Общее": "Marketing costs",
    "Другое": "Cost article - Другое",
    "Расходы на B2B (продакшн)": "Show production costs",
    "Возвраты": "Returns amount",
    "Для спектаклей": "Show production costs",
    "Тех оснащение": "Cost article - Тех оснащение",
    "Реквизит/костюмы": "Cost article - Реквизит/костюмы",
    "Маркетинг и реклама": "Marketing costs",
    "Помещение и офис": "Venue and office costs",
    "Уборка": "Cost article - Уборка",
    "Мебель и предметы интерьера": "Cost article - Мебель и предметы интерьера",
    "Ремонт и обслуживание": "Cost article - Ремонт и обслуживание",
    "Расходники (офисные)": "Cost article - Расходники (офисные)",
    "Ежемесячные счета": "Cost article - Ежемесячные счета",
    "Аренда и коммуналка": "Cost article - Аренда и коммуналка",
    "Сервисы и их настройка": "Services and setup costs",
    "КОМИССИИ БАНКОВ": "Cost article - КОМИССИИ БАНКОВ",
    "Отсмотр видео": "Cost article - Отсмотр видео",
    "Командировочные": "Business travel costs",
    "Логистика": "Variable logistics costs",
    "Доставка": "Cost article - Доставка",
    "Такси": "Cost article - Такси",
    "Разные налоги и взносы": "Cost article - Разные налоги и взносы",
    "Командные": "Team expenses",
    "Представительские": "Cost article - Представительские",
    "Операционная прибыль": "Operating profit",
    "Прочие доходы": "Other income",
    "Возвраты покупок": "Other income - Purchase returns",
    "Проценты по вкладам": "Other income - Deposit interest",
    "Прочие расходы": "Other expenses",
    "EBITDA": "EBITDA",
    "Амортизация": "Cost article - Амортизация",
    "Прибыль до процентов и налогов (EBIT)": "EBIT",
    "Проценты по кредитам и займам": "Cost article - Проценты по кредитам и займам",
    "Прибыль до налогов (EBT)": "EBT",
    "Налог на прибыль (доходы)": "Cost article - Налог на прибыль (доходы)",
    "Чистая прибыль (убыток)": "Net profit",
    "Дивиденды": "Dividends",
    "Нераспределенная прибыль": "Retained earnings",
}


REVENUE_DETAIL_ROWS = {
    "Корректировка неучтенного",
    "Другие продажи",
    "Франшиза",
    "Паушалка",
    "Роялти",
    "Продажа билетов B2C",
    "Организация мероприятий (B2B)",
    "Нераспределенный доход",
}


CALCULATED_ROWS = {
    "Операционная рентабельность",
    "Рентабельность по EBITDA",
    "Рентабельность по EBIT",
    "Рентабельность по EBT",
    "Рентабельность чистой прибыли",
}


LEAF_ONLY_EXCLUDED_ROWS = {
    "Переменные расходы",
    "Постоянные расходы",
    "Инвестиции",
    "Основные расходы",
    "ФОТ",
    "ФОТ - Переменные",
    "ФОТ - Постоянные",
    "ПРЕМИИ 2025",
    "Маркетинг и реклама",
    "Для спектаклей",
    "ПЕРЕЕЗД",
    "Помещение и офис",
    "Сервисы и их настройка",
    "Командировочные",
    "Логистика",
    "Командные",
    "Прочие расходы",
    "Операционная прибыль",
    "Прочие доходы",
    "EBITDA",
    "Прибыль до процентов и налогов (EBIT)",
    "Прибыль до налогов (EBT)",
    "Чистая прибыль (убыток)",
    "Дивиденды",
    "Нераспределенная прибыль",
}


REMOVED_METRIC_NAMES = {
    "Revenue - Unaccounted adjustment",
    "Revenue - Other sales",
    "Revenue - Franchise total",
    "Revenue - Franchise lump sum",
    "Revenue - Franchise royalty",
    "Revenue - B2C ticket sales",
    "Revenue - B2B events",
    "Revenue - Unallocated",
}


CHANNEL_BY_ROW_LABEL = {
    "Маркетинг и реклама - Услуги типографии": "pos",
    "Маркетинг и реклама - Агентские": "partners",
    "Маркетинг и реклама - PR и отзывы": "pr",
    "Маркетинг и реклама - SMM": "smm",
    "Маркетинг и реклама - Директ": "direct",
    "Маркетинг и реклама - Общее": "general",
}


def business_unit_from_project_label(project_label: str) -> str:
    return BUSINESS_UNIT_BY_PROJECT_LABEL.get(project_label.strip(), "")


def business_unit_from_workbook_name(workbook_name: str) -> str:
    return BUSINESS_UNIT_BY_WORKBOOK_NAME.get(workbook_name.strip(), "")


def detect_layout(worksheet) -> tuple[int, int]:
    header_marker = str(worksheet.cell(5, 1).value or "").strip()
    if header_marker == "Статьи учета":
        return 5, 6
    return 6, 7


def planfact_report_type_for_business_unit(business_unit: str) -> str:
    return "monthly_pnl_report_total" if business_unit == "total" else "monthly_pnl_report_by_business_unit"


def channel_from_row_label(label: str) -> str:
    return CHANNEL_BY_ROW_LABEL.get(label.strip(), "")


def should_import_leaf_only_planfact_row(*, label: str, has_children: bool) -> tuple[bool, str]:
    normalized = label.strip()
    if normalized in CALCULATED_ROWS:
        return False, "calculated_row"
    if normalized in REVENUE_DETAIL_ROWS:
        return False, "revenue_child_row_skipped"
    if normalized == "Выручка":
        return True, ""
    if normalized in LEAF_ONLY_EXCLUDED_ROWS:
        return False, "subtotal_or_result_row_skipped"
    if has_children:
        return False, "non_leaf_row_skipped"
    return True, ""


def should_alert_on_leaf_to_parent_change(label: str) -> bool:
    normalized = label.strip()
    if normalized == "Выручка":
        return False
    if normalized in CALCULATED_ROWS:
        return False
    if normalized in REVENUE_DETAIL_ROWS:
        return False
    if normalized in LEAF_ONLY_EXCLUDED_ROWS:
        return False
    return normalized in FACT_ROW_MAPPING
