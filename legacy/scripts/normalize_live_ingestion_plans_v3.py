#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
LIVE_DIR = ROOT / "generated" / "live_sheet_outlines"
CATALOG_PATHS = [
    ROOT / "generated" / "legacy_seed" / "metric_catalogue_v4.csv",
    ROOT / "generated" / "legacy_seed" / "metric_catalogue_v2.csv",
]


PLAN_FILES = [
    LIVE_DIR / "b2c_moscow_ingestion_plan_live_v2.csv",
    LIVE_DIR / "b2c_spb_ingestion_plan_live_v2.csv",
]


NEW_METRICS = [
    ("Returns amount - theater fault", "returns", "currency", "Returns amount caused by theater fault."),
    ("Returns amount - non-theater fault", "returns", "currency", "Returns amount not caused by theater fault."),
    (
        "Number of cancelled non-SD shows - no tickets sold",
        "shows_cancelled_reason",
        "count",
        "Cancelled non-SD shows because tickets were not sold.",
    ),
    (
        "Number of cancelled non-SD shows - special shows",
        "shows_cancelled_reason",
        "count",
        "Cancelled non-SD shows because of special shows.",
    ),
    (
        "Number of cancelled non-SD shows - actor/master shortage",
        "shows_cancelled_reason",
        "count",
        "Cancelled non-SD shows because of actor or master shortage.",
    ),
    (
        "Number of cancelled SD shows - no tickets sold",
        "shows_cancelled_reason",
        "count",
        "Cancelled SD shows because tickets were not sold.",
    ),
    (
        "Number of cancelled SD shows - special shows",
        "shows_cancelled_reason",
        "count",
        "Cancelled SD shows because of special shows.",
    ),
    (
        "Number of cancelled SD shows - actor/master shortage",
        "shows_cancelled_reason",
        "count",
        "Cancelled SD shows because of actor or master shortage.",
    ),
    ("Number of new Yandex Maps reviews", "reviews", "count", "New Yandex Maps reviews during the period."),
    ("Number of genuine reviews", "reviews", "count", "Reviews considered genuine during the period."),
    ("Number of non-genuine reviews", "reviews", "count", "Reviews considered non-genuine during the period."),
    ("Average review rating weekly overall", "reviews", "score", "Average review rating for the week, all reviews."),
    ("Average review rating weekly genuine", "reviews", "score", "Average review rating for the week, genuine reviews only."),
    ("Share of negative reviews from visitors", "reviews", "ratio", "Share of negative reviews from visitors."),
    ("Number of resolved negative reviews", "reviews", "count", "Number of negative reviews that were resolved."),
    (
        "Average review rating weekly without negatives after resolution",
        "reviews",
        "score",
        "Average review rating for the week excluding negatives after resolution.",
    ),
    ("Average review rating overall", "reviews", "score", "Overall average review rating."),
    ("Number of reviewed shows", "quality_internal", "count", "Number of reviewed shows."),
    ("Share of reviewed shows without violations", "quality_internal", "ratio", "Share of reviewed shows without violations."),
    ("Number of warnings", "quality_internal", "count", "Number of warnings."),
    ("Number of fines", "quality_internal", "count", "Number of fines."),
    ("Number of show removals", "quality_internal", "count", "Number of removals from shows."),
    ("Number of reviewed OGs", "quality_internal", "count", "Number of reviewed OGs."),
    ("Number of completed OG protocols", "quality_internal", "count", "Number of completed OG protocols."),
]


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


ADD_METRIC_BY_TEXT: Dict[tuple[str, str], str] = {
    ("Сумма возвратов", "По вине театра"): "Returns amount - theater fault",
    ("по вине театра", ""): "Returns amount - theater fault",
    ("Сумма возвратов", "НЕ по вине театра"): "Returns amount - non-theater fault",
    ("не по вине театра", ""): "Returns amount - non-theater fault",
    ("Отменено шоу (не СД)", "Кол-во, где не выкуплены билеты"): "Number of cancelled non-SD shows - no tickets sold",
    ("Кол-во, где не выкуплены билеты", ""): "Number of cancelled non-SD shows - no tickets sold",
    ("Отменено шоу (не СД)", "Кол-во из-за спецпоказов"): "Number of cancelled non-SD shows - special shows",
    ("Кол-во из-за спецпоказов", ""): "Number of cancelled non-SD shows - special shows",
    ("Отменено шоу (не СД)", "Кол-во из-за дефицита актёров/ мастеров"): "Number of cancelled non-SD shows - actor/master shortage",
    ("Кол-во из-за дефицита актёров/ мастеров", ""): "Number of cancelled non-SD shows - actor/master shortage",
    ("Отменено СД", "Кол-во, где не выкуплены билеты"): "Number of cancelled SD shows - no tickets sold",
    ("Отменено СД", "Кол-во из-за спецпоказов"): "Number of cancelled SD shows - special shows",
    ("Отменено СД", "Кол-во из-за дефицита актёров/ мастеров"): "Number of cancelled SD shows - actor/master shortage",
    ("ОТЗЫВЫ", "Кол-во новых на Яндекс-картах (всего)"): "Number of new Yandex Maps reviews",
    ("Кол-во новых на Яндекс-картах", ""): "Number of new Yandex Maps reviews",
    ("ОТЗЫВЫ", "Из них настоящих"): "Number of genuine reviews",
    ("Из них настоящих", ""): "Number of genuine reviews",
    ("ОТЗЫВЫ", "Из них ненастоящих"): "Number of non-genuine reviews",
    ("Из них ненастоящих", ""): "Number of non-genuine reviews",
    ("ОТЗЫВЫ", "Средняя оценка по отзывам за неделю (общая)"): "Average review rating weekly overall",
    ("Средняя оценка по отзывам за неделю (общая)", ""): "Average review rating weekly overall",
    ("ОТЗЫВЫ", "Средняя оценка по отзывам за неделю (по настоящим)"): "Average review rating weekly genuine",
    ("Средняя оценка по отзывам за неделю (по настоящим)", ""): "Average review rating weekly genuine",
    ("ОТЗЫВЫ", "Процент негативных (от посетивших)"): "Share of negative reviews from visitors",
    ("Процент негативных (от посетивших)", ""): "Share of negative reviews from visitors",
    ("ОТЗЫВЫ", "Ликвидировано негативных"): "Number of resolved negative reviews",
    ("Ликвидировано негативных", ""): "Number of resolved negative reviews",
    ("ОТЗЫВЫ", "Средняя оценка за неделю без негативных, если ликвидировали (общая)"): "Average review rating weekly without negatives after resolution",
    ("Средняя оценка за неделю без негативных, если ликвидировали (общая)", ""): "Average review rating weekly without negatives after resolution",
    ("ОТЗЫВЫ", "Средняя общая"): "Average review rating overall",
    ("Средняя общая", ""): "Average review rating overall",
    ("ОКК", "Кол-во отсмотренных спектаклей"): "Number of reviewed shows",
    ("Кол-во отсмотренных спектаклей", ""): "Number of reviewed shows",
    ("ОКК", "Процент без нарушений от отсмотренных"): "Share of reviewed shows without violations",
    ("Процент без нарушений от отсмотренных", ""): "Share of reviewed shows without violations",
    ("ОКК", "Количество предупреждений"): "Number of warnings",
    ("Количество предупреждений", ""): "Number of warnings",
    ("ОКК", "Количество штрафов"): "Number of fines",
    ("Количество штрафов", ""): "Number of fines",
    ("ОКК", "Количество отстранений от спектакля"): "Number of show removals",
    ("Количество отстранений от спектакля", ""): "Number of show removals",
    ("Кол-во отсмотренных ОГ", ""): "Number of reviewed OGs",
    ("Всего заполненных ОГ", ""): "Number of completed OG protocols",
}


def read_plan(path: Path) -> List[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def write_plan(path: Path, rows: Iterable[dict], fieldnames: List[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def normalize_action(raw: str) -> tuple[str, str]:
    raw = (raw or "").strip()
    if raw in {"map_to_metric", "add_metric"}:
        return "map_to_metric", ""
    if raw == "decompose_block":
        return "decompose_block", ""
    if raw == "defer_to_calculated":
        return "defer_to_calculated", ""
    if raw in {"exclude", "Exclude", "Exclude ", "Дата начала периода", "Две даты - можно exclude", "дата начала диапазона"}:
        return "exclude", ""
    if raw == "Change_source_to_ERP":
        return "map_to_metric", "erp"
    if raw in {"Change_source_to_ERP - Defer_to_calculates", "Change_source_to_ERP, defer to calculated"}:
        return "defer_to_calculated", "erp"
    if raw == "blank":
        return "", ""
    return raw, ""


def normalize_target(raw_target: str, row: dict) -> str:
    raw_target = (raw_target or "").strip()
    if raw_target == "Revenue - MscB2c":
        return "Revenue"
    if raw_target == "revenue":
        return "Revenue"
    if raw_target == "Quality - External":
        key = ((row.get("col_a") or "").strip(), (row.get("col_b") or "").strip())
        return ADD_METRIC_BY_TEXT.get(key, raw_target)
    if raw_target == "Quality - Internal":
        key = ((row.get("col_a") or "").strip(), (row.get("col_b") or "").strip())
        return ADD_METRIC_BY_TEXT.get(key, raw_target)
    return raw_target


def transform_rows(rows: List[dict]) -> List[dict]:
    out = []
    for row in rows:
        raw_action = (row.get("ingestion_action") or "").strip()
        raw_target = (row.get("target_metric_or_metrics") or "").strip()
        normalized_action, source_override = normalize_action(raw_action)

        target = raw_target
        if raw_action == "add_metric":
            key = ((row.get("col_a") or "").strip(), (row.get("col_b") or "").strip())
            target = ADD_METRIC_BY_TEXT.get(key, raw_target)
        else:
            target = normalize_target(raw_target, row)

        out.append(
            {
                "row_number": row.get("row_number", "").strip(),
                "col_a": row.get("col_a", "").strip(),
                "col_b": row.get("col_b", "").strip(),
                "ingestion_action_raw": raw_action,
                "ingestion_action": normalized_action,
                "target_metric_or_metrics_raw": raw_target,
                "target_metric_or_metrics": target,
                "source_system_override": source_override,
                "import_as_source": (row.get("import_as_source") or "").strip(),
                "layer": (row.get("layer") or "").strip(),
                "note": (row.get("note") or "").strip(),
            }
        )
    return out


def update_catalog(path: Path) -> None:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys())

    by_name = {r["metric_name"].strip(): r for r in rows}
    for metric_name, family, value_kind, description in NEW_METRICS:
        if metric_name in by_name:
            row = by_name[metric_name]
            row["metric_family"] = family
            row["value_kind"] = value_kind
            row["description"] = description
            row["legacy_mapping_status"] = "added_from_live_weekly_plan"
            row["legacy_notes_summary"] = "Created from add_metric decisions in live weekly ingestion plans."
            continue
        rows.append(
            {
                "metric_key": slugify(metric_name),
                "metric_name": metric_name,
                "metric_family": family,
                "value_kind": value_kind,
                "description": description,
                "legacy_mapping_status": "added_from_live_weekly_plan",
                "legacy_groups_covered": "",
                "legacy_groups_partial": "",
                "legacy_group_count_covered": "0",
                "legacy_group_count_partial": "0",
                "legacy_notes_summary": "Created from add_metric decisions in live weekly ingestion plans.",
            }
        )

    rows.sort(key=lambda r: (r["metric_name"] or "").lower())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    for plan_file in PLAN_FILES:
        rows = read_plan(plan_file)
        transformed = transform_rows(rows)
        out_path = plan_file.with_name(plan_file.stem.replace("_v2", "_v3") + plan_file.suffix)
        fieldnames = [
            "row_number",
            "col_a",
            "col_b",
            "ingestion_action_raw",
            "ingestion_action",
            "target_metric_or_metrics_raw",
            "target_metric_or_metrics",
            "source_system_override",
            "import_as_source",
            "layer",
            "note",
        ]
        write_plan(out_path, transformed, fieldnames)

    for catalog_path in CATALOG_PATHS:
        update_catalog(catalog_path)


if __name__ == "__main__":
    main()
