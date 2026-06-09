#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


BASE = Path("/Users/Peter/Documents/Morpheus Metrics")
AUDIT_CSV = BASE / "generated/google_sheet_row_audit_19Ssy4Esp0vG_7yIHA8mNpfuzjvko12TdQEklEPFxfC0_gid_582113259.csv"
OVERLAY_CSV = BASE / "generated/monthly_economics_canonical_overlay_for_mapping.csv"
USER_REVIEW_CSV = Path("/Users/Peter/Documents/monthly_economics_canonical_overlay_review_needed.csv")
OUTPUT_CSV = BASE / "generated/historical_sheet_canonical_metric_mapping.csv"


def normalize_text(value: str) -> str:
    return " ".join((value or "").replace("\xa0", " ").split()).strip()


def normalize_source_label(value: str) -> str:
    return normalize_text(value).rstrip(":")


def canonical_business_unit(source_business_unit: str, source_label: str, row_number: int) -> str:
    source_business_unit = normalize_text(source_business_unit)
    if row_number == 102 and normalize_source_label(source_label) == "Итого расходы на маркетинг":
        return "b2c_moscow"
    if normalize_source_label(source_label) == "Директорский процент":
        return "total"
    if source_business_unit == "Москва":
        return "b2c_moscow"
    if source_business_unit in {"СПб", "Спб", "Питер"}:
        return "b2c_spb"
    if source_business_unit == "B2B":
        return "b2b"
    if source_business_unit == "Франшиза":
        return "franchise"
    if source_business_unit == "Общее":
        return "general"
    if row_number >= 218:
        return "general"
    if source_label in {"Годовые бонусы", "ГОДОВЫЕ БОНУСЫ", "Сальдо", "Дополнительно"}:
        return "general"
    return ""


def marketing_channel_for_label(label: str) -> str:
    label = normalize_source_label(label).lower()
    if not label:
        return "general"
    if "контекст" in label or "директ" in label:
        return "perfomance"
    if any(token in label for token in ["таргет", "инстаграм", "тик-ток", "youtube", "рилс"]):
        return "smm"
    if any(token in label for token in ["pr", "блогер", "афиш", "дзен", "паблик", "кросс-промо", "seo"]):
        return "pr"
    if "агентск" in label:
        return "agency"
    if "маркетинг" in label or "реклама" in label or "продвижение франшизы" in label:
        return "other"
    return "general"


def explicit_override(label: str, source_bu: str) -> tuple[str, str, str, str, str, str]:
    label = normalize_source_label(label)
    source_bu = normalize_text(source_bu)

    mapping = {
        "Проведено шоу": ("fact", "Number of shows", "", "general", "general", "general"),
        "Гостей": ("fact", "Number of show visitors", "", "general", "general", "general"),
        "Среднее количество гостей": ("calc", "Средняя загрузка шоу (по факту дошедшие зрители)", "", "general", "general", "general"),
        "%заполняемости": ("calc", "Средняя загрузка шоу (по факту дошедшие зрители)", "", "general", "general", "general"),
        "Проведено СД": ("fact", "Number of shows", "", "general", "general", "sd"),
        "Реализация_шоу": ("fact", "Revenue", "", "general", "general", "general"),
        "Реализация шоу": ("fact", "Revenue", "", "general", "general", "general"),
        "Реализация_СД": ("fact", "Revenue", "", "general", "general", "sd"),
        "Реализация СД": ("fact", "Revenue", "", "general", "general", "sd"),
        "Выручка_сертификаты": ("exclude", "", "use only `Выручка_сертификаты с понижающем кэфом` for certificate revenue", "general", "general", "certificate"),
        "Выручка_сертификаты с понижающем кэфом": ("fact", "Revenue", "", "general", "general", "certificate"),
        "Франшиза_паушалка": ("fact", "Revenue", "", "general", "general", "general"),
        "Франшиза_роялти": ("fact", "Revenue", "", "general", "general", "general"),
        "Франшиза_тотал": ("fact", "Revenue", "", "general", "general", "general"),
        "Франшиза Китай": ("fact", "Revenue", "", "general", "general", "general"),
        "Спецпроекты_корпоративы": ("fact", "Revenue", "", "general", "general", "general"),
        "Спецпроекты_классический репертуар": ("fact", "Revenue", "", "general", "general", "general"),
        "Спецпроекты_СД": ("fact", "Revenue", "", "general", "general", "sd"),
        "Спецпроекты_онлайн": ("fact", "Revenue", "", "general", "general", "online"),
        "Спецпроекты_корпоративы_з/п актеров": ("fact", "Costs - Salary variable", "", "general", "general", "general"),
        "Спецпроекты_корпоративы_з/п креативная команда": ("fact", "Costs - Salary variable", "", "general", "general", "general"),
        "Спецпроекты_костюмы и реквизит": ("fact", "Show production costs", "", "general", "general", "general"),
        "Спецпроекты_разные услуги": ("fact", "Other expenses", "", "general", "general", "general"),
        "Спецпроекты_классический репуртуар_з/п актеров": ("fact", "Costs - Salary variable", "", "general", "general", "general"),
        "Спецпроекты_СД_з/п актеров": ("fact", "Costs - Salary variable", "", "general", "general", "SD"),
        "Спецпроекты_онлайн_з/п актеров": ("fact", "Costs - Salary variable", "", "general", "general", "Online"),
        "Переменные расходы": ("fact", "Variable costs", "", "general", "general", "general"),
        "Постоянные расходы": ("fact", "Fixed costs", "", "general", "general", "general"),
        "Итого переменные расходы": ("fact+calc", "Variable costs", "observed subtotal plus derived cross-check", "general", "general", "general"),
        "Итого постоянные расходы": ("fact+calc", "Fixed costs", "observed subtotal plus derived cross-check", "general", "general", "general"),
        "Маркетинг": ("fact", "Marketing costs", "", "other", "general", "general"),
        "Маркетинг и реклама": ("fact", "Marketing costs", "", "other", "general", "general"),
        "Итого расходы на маркетинг": ("fact+calc", "Marketing costs", "observed subtotal by marketing channels; store as total channel", "total", "general", "general"),
        "Контекстная реклама_бюджет_ритейл": ("fact", "Marketing costs", "", "perfomance", "general", "general"),
        "Контекстная реклама_бюджет_франшиза": ("fact", "Marketing costs", "", "perfomance", "general", "general"),
        "Контекст_ведение_ритейл": ("fact", "Marketing costs", "", "perfomance", "general", "general"),
        "Контекст_ведение_франшиза": ("fact", "Marketing costs", "", "perfomance", "general", "general"),
        "Контекстна реклама_корпоратив": ("fact", "Marketing costs", "", "perfomance", "general", "general"),
        "Контекстная реклама_ведение_ритейл": ("fact", "Marketing costs", "", "perfomance", "general", "general"),
        "Контекст_бюджет_ритейл": ("fact", "Marketing costs", "", "perfomance", "general", "general"),
        "Таргетированная реклама_бюджет": ("fact", "Marketing costs", "", "smm", "general", "general"),
        "Таргетолог_ведение": ("fact", "Marketing costs", "", "smm", "general", "general"),
        "Инстаграм_ведение": ("fact", "Marketing costs", "", "smm", "general", "general"),
        "Тик-Ток_ведение": ("fact", "Marketing costs", "", "smm", "general", "general"),
        "Тик-Ток_бюджет": ("fact", "Marketing costs", "", "smm", "general", "general"),
        "Youtube_ведение": ("fact", "Marketing costs", "", "smm", "general", "general"),
        "Youtube_бюджет": ("fact", "Marketing costs", "", "smm", "general", "general"),
        "Размещение у блогеров, афишах, дзене, паблики_бюджет": ("fact", "Marketing costs", "", "pr", "general", "general"),
        "Размещение у блогеров, афишах, дзене, паблики_ведение": ("fact", "Marketing costs", "", "pr", "general", "general"),
        "Размещение у блогеров, афишах, дзене, паблики": ("fact", "Marketing costs", "", "pr", "general", "general"),
        "PR": ("fact", "Marketing costs", "", "pr", "general", "general"),
        "Кросс-промо / Интеграция в фестивали": ("fact", "Marketing costs", "", "pr", "general", "general"),
        "Кросс-промо и SEO": ("fact", "Marketing costs", "", "pr", "general", "general"),
        "Кросс-промо и  SEO": ("fact", "Marketing costs", "", "pr", "general", "general"),
        "Рилс-мэйкинг": ("fact", "Marketing costs", "mapped to unified marketing spend", "smm", "general", "general"),
        "Продвижение франшизы": ("fact", "Marketing costs", "franchise marketing spend", "other", "general", "general"),
        "Прочие расходы на рекламу": ("fact", "Marketing costs", "", "other", "general", "general"),
        "Комиссии платежных систем": ("fact", "Cost article - Комиссия", "", "general", "general", "general"),
        "Комиссии платежных систем (агрегаторы)": ("fact", "Cost article - Комиссия", "", "general", "general", "general"),
        "Комиссии платежных систем (агрегаторы_МДТЗК)": ("fact", "Cost article - Комиссия", "", "general", "general", "general"),
        "Комиссии платежных систем (агрегаторы_ДТЗК)": ("fact", "Cost article - Комиссия", "", "general", "general", "general"),
        "Комиссии за снятие наличных": ("fact", "Cost article - Комиссия", "", "general", "general", "general"),
        "Банковское обслуживание": ("fact", "Cost article - КОМИССИИ БАНКОВ", "", "general", "general", "general"),
        "Налог6%": ("fact", "Cost article - Налог на прибыль (доходы)", "", "general", "general", "general"),
        "Налог страховые взносы": ("fact", "Cost article - Страховые взносы", "", "general", "general", "general"),
        "Возвраты": ("fact", "Returns amount", "", "general", "general", "general"),
        "процент возвратов от выручки": ("calc", "% возвратов от выручки", "", "general", "general", "general"),
        "Логистика": ("fact", "Variable logistics costs", "", "general", "general", "general"),
        "Логистика (командировки Москвы в Питер)": ("fact", "Business travel costs", "", "general", "general", "general"),
        "Прочие расходы": ("fact", "Other expenses", "", "general", "general", "general"),
        "Аренда помещения": ("fact", "Venue and office costs", "", "general", "general", "general"),
        "Аренда помещения и коммуналка": ("fact", "Venue and office costs", "", "general", "general", "general"),
        "Электроэнергия": ("fact", "Venue and office costs", "fold into venue/office utilities", "general", "general", "general"),
        "Уборка помещения": ("fact", "Cost article - Уборка", "", "general", "general", "general"),
        "Ремонт помещения": ("fact", "Cost article - Ремонт и обслуживание", "", "general", "general", "general"),
        "Хоз.расходы на помещение": ("fact", "Cost article - Расходники (офисные)", "", "general", "general", "general"),
        "Расходы на проведение спектаклей": ("fact", "Show production costs", "", "general", "general", "general"),
        "Реквизит для проведения спектаклей": ("fact", "Cost article - Реквизит/костюмы", "", "general", "general", "general"),
        "Электронные и бухгалтерские сервисы": ("fact", "Services and setup costs", "", "general", "general", "general"),
        "Электронные  и бухгалтерские сервисы": ("fact", "Services and setup costs", "", "general", "general", "general"),
        "Сайт, презентации, дизайн": ("fact", "Marketing costs", "", "other", "general", "general"),
        "Доработка софта, озвучка и пр": ("fact", "Investment costs", "", "general", "general", "general"),
        "Обучение": ("fact", "Team expenses", "", "general", "general", "general"),
        "Реквизит и оборудование": ("fact", "Show production costs", "", "general", "general", "general"),
        "Сценарии": ("fact", "Investment costs", "", "general", "general", "general"),
        "СRM": ("fact", "Services and setup costs", "", "general", "general", "general"),
        "Реклама": ("fact", "Marketing costs", "", "other", "general", "general"),
        "Оборудование и ремонт": ("fact", "Investment costs", "", "general", "general", "general"),
        "Европейская франшиза": ("fact", "Revenue", "", "general", "general", "general"),
        "Итого, расходы инвестиции Москва": ("fact", "Investment costs", "", "general", "general", "general"),
        "% инвестиций от выручки": ("calc", "% инвестиций от выручки", "", "general", "general", "general"),
        "Инвестии в Петербург": ("fact", "Investment costs", "", "general", "general", "general"),
        "Расчетная выручка периода (по реализации)": ("calc", "Revenue", "derived/diagnostic revenue equivalent", "general", "general", "general"),
        "% отнесения на выручку": ("calc", "% отнесения на выручку", "certificate allocation helper", "general", "general", "certificate"),
        "%к выручке": ("calc", "% общ. к выручке", "", "general", "general", "general"),
        "% к выручке": ("calc", "% общ. к выручке", "", "general", "general", "general"),
        "% от выручки": ("calc", "% общ. к выручке", "", "general", "general", "general"),
        "Маржинальный доход": ("calc", "Маржинальный доход", "", "general", "general", "general"),
        "% переменных расходов к выручке": ("calc", "% переменных расходов к выручке", "", "general", "general", "general"),
        "% к марже": ("calc", "% к марже", "", "general", "general", "general"),
        "%з/п исполнителей в бюджете на маркетинг от всего маркетинга": ("calc", "%з/п исполнителей в бюджете на маркетинг от всего маркетинга", "", "general", "general", "general"),
        "%постоянных расходов к выручке": ("calc", "%постоянных расходов к выручке", "", "general", "general", "general"),
        "% ФОТ в выручке ШОУ": ("calc", "% ФОТ в выручке ШОУ", "", "general", "general", "general"),
        "% ФОТ в выручке СД": ("exclude", "", "specific calculated show ratio", "general", "general", "sd"),
        "% ФОТ в выручке CД": ("exclude", "", "specific calculated show ratio", "general", "general", "sd"),
        "Средняя цена одного билета": ("calc", "Средняя цена одного билета", "", "general", "general", "general"),
        "Проведено шоу оффлайн": ("exclude", "", "subcut of show count, not separate canonical metric", "general", "general", "offline"),
        "Проведено шоу онлайн": ("exclude", "", "subcut of show count, not separate canonical metric", "general", "general", "online"),
        "Продажи актеров": ("fact", "Actor upsell sales", "candidate/new metric from historical economics sheet", "general", "general", "general"),
        "Иные выплаты актерам, надбавки": ("fact", "Costs - Salary variable", "mapped to variable actor compensation", "general", "general", "general"),
        "Митя_Бонус СД": ("fact", "Costs - Salary variable", "show-linked bonus", "general", "general", "sd"),
        "ЗП актеров по начислению_ классический репертуар": ("fact", "Costs - Salary variable", "actor payroll belongs to variable salary", "general", "general", "general"),
        "ЗП актеров по начислению": ("fact", "Costs - Salary variable", "actor payroll belongs to variable salary", "general", "general", "general"),
        "ЗП актеров-Судный день": ("fact", "Costs - Salary variable", "show-linked actor payroll belongs to variable salary", "general", "general", "sd"),
        "ЗП СД": ("fact", "Costs - Salary variable", "show-linked actor payroll belongs to variable salary", "general", "general", "sd"),
        "Другие затраты_Спецпроекты СД": ("fact", "Show production costs", "B2B production expense", "general", "general", "sd"),
        "Общие расходы спецпроекты_корпоративы": ("fact", "Show production costs", "B2B production expense", "general", "general", "general"),
        "Затраты франшиза Китай": ("fact", "Other expenses", "franchise-unit operating expense", "general", "general", "general"),
        "Затраты на реквизит для партнеров франшиза": ("fact", "Show production costs", "franchise production/setup expense", "general", "general", "general"),
        "Разработка и IT": ("fact", "Cost article - IT ФОТ", "", "general", "general", "general"),
        "Подарки": ("fact", "Team expenses", "", "general", "general", "general"),
        "Прибыль_театр Москва": ("fact", "Net profit", "", "general", "general", "general"),
        "Прибыль_театр Петербург": ("fact", "Net profit", "", "general", "general", "general"),
        "Прибыль_франшиза": ("fact", "Net profit", "", "general", "general", "general"),
        "Прибыль_Китай": ("fact", "Net profit", "", "general", "general", "general"),
        "Прибыль_корпоратив Москва": ("fact", "Net profit", "", "general", "general", "general"),
        "Прибыль_корпоратив Петербург": ("fact", "Net profit", "", "general", "general", "general"),
        "Прибыль_корпоратив общая": ("fact", "Net profit", "", "general", "general", "general"),
        "Общая прибыль": ("exclude", "", "duplicate total profit helper; use only `Прибыль для основателей` for Net profit", "general", "general", "general"),
        "Театр Москва": ("fact", "Net profit", "", "general", "general", "general"),
        "Театр Петербург": ("fact", "Net profit", "", "general", "general", "general"),
        "Корпоратив": ("fact", "Net profit", "", "general", "general", "general"),
        "Франшиза": ("fact", "Net profit", "", "general", "general", "general"),
        "Франшиза (без учета Китая и Чехии)": ("fact", "Net profit", "", "general", "general", "general"),
        "Китай": ("fact", "Net profit", "", "general", "general", "general"),
        "Годовые бонусы": ("fact", "Annual bonuses", "", "general", "general", "general"),
        "ГОДОВЫЕ БОНУСЫ": ("fact", "Annual bonuses", "", "general", "general", "general"),
        "Директорский процент": ("fact", "Cost article - Директорский процент", "historical owner distribution cost article used in total net profit bridge", "general", "general", "general"),
        "Итого, процент директора": ("exclude", "", "owner distribution layer, not canonical fact", "general", "general", "general"),
        "Прибыль для основателей": ("fact", "Net profit", "historical total net profit proxy from legacy monthly economics sheet", "general", "general", "general"),
        "Рентабельность общая после выплаты основателям": ("exclude", "", "owner distribution layer, not canonical fact", "general", "general", "general"),
        "Рентабельность общая после выплаты основателям": ("exclude", "", "owner distribution layer, not canonical fact", "general", "general", "general"),
        "Прибыль от европейской франшизы": ("fact", "Net profit", "", "general", "general", "general"),
        "Прибыль до выплаты акционерам,развития и % директора": ("exclude", "", "owner distribution helper", "general", "general", "general"),
        "12% прибыли": ("exclude", "", "owner distribution helper", "general", "general", "general"),
        "5 % прибыли": ("exclude", "", "owner distribution helper", "general", "general", "general"),
        "10 % прибыли": ("exclude", "", "owner distribution helper", "general", "general", "general"),
        "Снятие наличных/перевод на карту для ПСН": ("exclude", "", "cash management layer", "general", "general", "general"),
        "Комиссия за снятие наличных / налоги на ИП": ("exclude", "", "cash management layer", "general", "general", "general"),
        "Входящий остаток на начало периода, 1 число месяца": ("exclude", "", "cash balance layer", "general", "general", "general"),
        "Входящий остаток на начало периода,  1 число месяца": ("exclude", "", "cash balance layer", "general", "general", "general"),
        "Входящий остаток на конец периода, 1 число месяца": ("exclude", "", "cash balance layer", "general", "general", "general"),
        "Сальдо": ("exclude", "", "cash balance layer", "general", "general", "general"),
        "Вывод для ПСН (депозитный счет)": ("fact", "Dividends", "historical dividends proxy from legacy monthly economics sheet", "general", "general", "general"),
        "дата вывода": ("exclude", "", "service row", "general", "general", "general"),
        "СУММА К ПЕРЕВОДУ ПСН ПО РЕЗУЛЬТАТАМ МЕСЯЦА": ("exclude", "", "cash management layer", "general", "general", "general"),
        "СУММА К ПЕРЕВОДУ НАКОПИТЕЛЬНЫМ ИТОГОМ ЗА ГОД": ("exclude", "", "cash management layer", "general", "general", "general"),
        "СУММА ПЕРЕВЕДЕННАЯ ПО ИТОГУ МЕСЯЦА": ("exclude", "", "cash management layer", "general", "general", "general"),
        "СУММА ПЕРЕВЕДЕННАЯ НАКОПИТЕЛЬНЫМ ИТОГОМ ЗА ГОД": ("exclude", "", "cash management layer", "general", "general", "general"),
        "Отложено на депозит по итогу месяца": ("exclude", "", "cash management layer", "general", "general", "general"),
        "Отложено на депозит накопительным итогом за год": ("exclude", "", "cash management layer", "general", "general", "general"),
        "Сальдо с учетом депозита": ("exclude", "", "cash balance layer", "general", "general", "general"),
        "Дополнительно": ("exclude", "", "service row", "general", "general", "general"),
        "Процент выполнения годового плана": ("exclude", "", "planning KPI outside canonical fact layer", "general", "general", "general"),
        "Театр Москва накопительным итогом": ("exclude", "", "cumulative helper row", "general", "general", "general"),
        "Театр Петербург накопительным итогом": ("exclude", "", "cumulative helper row", "general", "general", "general"),
        "Франшиза накопительным итогом": ("exclude", "", "cumulative helper row", "general", "general", "general"),
        "Корпоратив накопительным итогом": ("exclude", "", "cumulative helper row", "general", "general", "general"),
        "Питер": ("exclude", "", "section divider", "general", "general", "general"),
        "МОРФЕУС САНКТ-ПЕТЕРБУРГ": ("exclude", "", "section divider", "general", "general", "general"),
        "ИТОГОВАЯ ПРИБЫЛЬ ПО НАПРАВЛЕНИЯМ": ("exclude", "", "section divider", "general", "general", "general"),
    }

    layer, metric, note, channel, agent, show = mapping.get(label, ("", "", "", "", "", ""))

    if label == "Среднее количество гостей" and source_bu in {"СПб", "Спб", "Питер"}:
        return ("calc", "Средняя загрузка шоу (по факту дошедшие зрители)", "", "general", "general", "general")
    if label == "%заполняемости" and source_bu in {"СПб", "Спб", "Питер"}:
        return ("calc", "Средняя загрузка шоу (по факту дошедшие зрители)", "", "general", "general", "general")
    if label == "Гостей" and source_bu in {"СПб", "Спб", "Питер"}:
        return ("fact", "Number of show visitors", "", "general", "general", "general")
    if label == "Налог6%":
        return ("fact", "Cost article - Налог на прибыль (доходы)", "", "general", "general", "general")
    return (layer, metric, note, channel, agent, show)


def load_overlay_mapping():
    overlay = {}
    with OVERLAY_CSV.open() as f:
        for row in csv.DictReader(f):
            key = (normalize_text(row["source_business_unit"]), normalize_source_label(row["source_label"]))
            overlay[key] = row
    return overlay


def load_user_review():
    review = {}
    if not USER_REVIEW_CSV.exists():
        return review
    with USER_REVIEW_CSV.open() as f:
        for row in csv.DictReader(f, delimiter=";"):
            key = (normalize_text(row["source_business_unit"]), normalize_source_label(row["source_label"]))
            review[key] = row
    return review


def main():
    overlay = load_overlay_mapping()
    review = load_user_review()

    with AUDIT_CSV.open() as f:
        audit_rows = list(csv.DictReader(f))

    output_rows = []
    for row in audit_rows:
        row_number = int(row["row_number"])
        first_column = normalize_text(row["first_column"])
        second_column = normalize_source_label(row["second_column"])

        if row_number <= 4:
            continue
        if not second_column:
            continue

        bu = canonical_business_unit(first_column, second_column, row_number)
        overlay_key = (normalize_text(first_column), second_column)
        overlay_row = overlay.get(overlay_key)
        review_row = review.get(overlay_key)

        layer, metric, note, channel, agent, show = explicit_override(second_column, first_column)
        status = "mapped" if metric or layer == "exclude" else "review_needed"

        if not layer and overlay_row:
            if overlay_row["status"] == "exclude":
                layer = "exclude"
                status = "excluded"
            else:
                layer = overlay_row["mapped_layer"]
                metric = overlay_row["mapped_metric"]
                status = overlay_row["status"] or "mapped"

        if review_row and review_row.get("upd_layer"):
            upd_layer = normalize_text(review_row["upd_layer"]).lower()
            upd_metric = normalize_text(review_row.get("upd_metric", ""))
            upd_note = normalize_text(review_row.get("upd_note", ""))
            if upd_layer in {"exclude", "skip"}:
                layer = "exclude"
                metric = ""
                status = "excluded"
            elif "metrics" in upd_layer and "calculated" in upd_layer:
                layer = "fact+calc"
                status = "mapped_from_user_review"
            elif upd_layer == "calculated":
                layer = "calc"
                status = "mapped_from_user_review"
            elif upd_layer in {"metrics", "fact"}:
                layer = "fact"
                status = "mapped_from_user_review"
            if upd_metric:
                metric = upd_metric
            if upd_note:
                note = upd_note

        if metric == "ФОТ IT":
            metric = "Cost article - IT ФОТ"

        if second_column == "Директорский процент":
            layer = "fact"
            metric = "Cost article - Директорский процент"
            bu = "total"
            channel = "general"
            agent = "general"
            show = "general"
            status = "mapped"
            note = "historical owner distribution cost article used in total net profit bridge"

        if row_number == 210 and first_column == "Общее" and second_column == "Общая прибыль":
            layer = "exclude"
            metric = ""
            bu = "general"
            channel = ""
            agent = ""
            show = ""
            status = "excluded"
            note = "main historical sheet row 210 must stay excluded; use only `Прибыль для основателей` for total Net profit"

        if row_number == 219 and first_column == "Общее" and second_column == "Прибыль для основателей":
            layer = "fact"
            metric = "Net profit"
            bu = "total"
            channel = "general"
            agent = "general"
            show = "general"
            status = "mapped"
            note = "main historical sheet row 219 is total Net profit, never general"

        if row_number in {248, 250, 254} and second_column in {
            "Театр Москва",
            "Театр Петербург",
            "Корпоратив",
        }:
            layer = "exclude"
            metric = ""
            bu = "general"
            channel = ""
            agent = ""
            show = ""
            status = "excluded"
            note = "main historical sheet percentage helper row; never include in Net profit"

        if row_number == 79 and second_column == "Итого переменные расходы":
            layer = "fact"
            metric = "Variable costs"
            bu = "total"
            channel = "general"
            agent = "general"
            show = "general"
            status = "mapped"
            note = "main historical sheet row 79 is historical total variable costs subtotal, never general"

        if row_number == 119 and second_column == "Итого постоянные расходы":
            layer = "fact"
            metric = "Fixed costs"
            bu = "total"
            channel = "general"
            agent = "general"
            show = "general"
            status = "mapped"
            note = "main historical sheet row 119 is historical total fixed costs subtotal, never general"

        if first_column == "Москва" and second_column in {
            "Доработка софта, озвучка и пр",
            "Обучение",
            "Реквизит и оборудование",
            "Сценарии",
            "СRM",
            "CRM",
            "Реклама",
            "Оборудование и ремонт",
        }:
            layer = "exclude"
            metric = ""
            bu = "b2c_moscow"
            channel = ""
            agent = ""
            show = ""
            status = "excluded"
            note = "excluded because `Итого, расходы инвестиции Москва` is the investment subtotal for Moscow"

        if not bu and overlay_row:
            bu = overlay_row.get("canonical_business_unit", "")

        if not channel:
            channel = marketing_channel_for_label(second_column) if metric == "Marketing costs" else "general"
        if not agent:
            agent = "general"

        formula_or_input = "formula" if row["has_formula"] == "yes" else "input"
        filled_cell_count = row["filled_cell_count"]

        if layer == "fact+calc":
            for split_layer in ("fact", "calc"):
                output_rows.append(
                    {
                        "row_number": row_number,
                        "source_business_unit": first_column,
                        "source_label": second_column,
                        "formula_or_input": formula_or_input,
                        "filled_cell_count": filled_cell_count,
                        "layer": split_layer,
                        "canonical_metric": metric,
                        "business_unit": bu,
                        "show": show,
                        "channel": channel,
                        "agent": agent,
                        "merge_rule": "sum" if metric else "",
                        "mapping_status": status,
                        "mapping_note": note,
                    }
                )
            continue

        output_rows.append(
            {
                "row_number": row_number,
                "source_business_unit": first_column,
                "source_label": second_column,
                "formula_or_input": formula_or_input,
                "filled_cell_count": filled_cell_count,
                "layer": layer or "",
                "canonical_metric": metric or "",
                "business_unit": bu,
                "show": show if layer and layer != "exclude" else "",
                "channel": channel if layer and layer != "exclude" else "",
                "agent": agent if layer and layer != "exclude" else "",
                "merge_rule": "sum" if metric else "",
                "mapping_status": status,
                "mapping_note": note,
            }
        )

    with OUTPUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "row_number",
                "source_business_unit",
                "source_label",
                "formula_or_input",
                "filled_cell_count",
                "layer",
                "canonical_metric",
                "business_unit",
                "show",
                "channel",
                "agent",
                "merge_rule",
                "mapping_status",
                "mapping_note",
            ],
        )
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Wrote {len(output_rows)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
