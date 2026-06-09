#!/usr/bin/env python3
import argparse
import csv
import calendar
from pathlib import Path
from datetime import date

import psycopg2
from psycopg2.extras import Json, execute_batch


EXACT_METRIC_MAPPING = {
    "Проведено шоу": {
        "catalog_metric_name": "Number of shows",
        "currency_code": None,
    },
    "Гостей": {
        "catalog_metric_name": "Number of show visitors",
        "currency_code": None,
    },
    "Возвраты": {
        "catalog_metric_name": "Returns amount",
        "currency_code": "RUB",
    },
    "Выручка_сертификаты": {
        "catalog_metric_name": "Revenue",
        "currency_code": "RUB",
        "show_name": "сертификаты",
    },
    "Реализация_шоу": {
        "catalog_metric_name": "Revenue",
        "currency_code": "RUB",
    },
    "Реализация шоу": {
        "catalog_metric_name": "Revenue",
        "currency_code": "RUB",
    },
    "Франшиза": {
        "catalog_metric_name": "Revenue",
        "currency_code": "RUB",
        "force_business_unit": "franchise",
    },
    "Аренда помещения": {
        "catalog_metric_name": "Cost article - Аренда и коммуналка",
        "currency_code": "RUB",
    },
    "Аренда помещения и коммуналка": {
        "catalog_metric_name": "Cost article - Аренда и коммуналка",
        "currency_code": "RUB",
    },
    "Банковское обслуживание": {
        "catalog_metric_name": "Cost article - КОМИССИИ БАНКОВ",
        "currency_code": "RUB",
    },
    "Комиссии платежных систем": {
        "catalog_metric_name": "Cost article - Комиссия",
        "currency_code": "RUB",
    },
    "Комиссии платежных систем (агрегаторы)": {
        "catalog_metric_name": "Cost article - Комиссия",
        "currency_code": "RUB",
    },
    "Комиссии платежных систем (агрегаторы_МДТЗК)": {
        "catalog_metric_name": "Cost article - Комиссия",
        "currency_code": "RUB",
    },
    "Комиссии платежных систем (агрегаторы_ДТЗК)": {
        "catalog_metric_name": "Cost article - Комиссия",
        "currency_code": "RUB",
    },
    "Налог страховые взносы": {
        "catalog_metric_name": "Cost article - Страховые взносы",
        "currency_code": "RUB",
    },
    "Прочие расходы": {
        "catalog_metric_name": "Cost article - Другое",
        "currency_code": "RUB",
    },
    "Реквизит для проведения спектаклей": {
        "catalog_metric_name": "Cost article - Реквизит/костюмы",
        "currency_code": "RUB",
    },
    "Уборка помещения": {
        "catalog_metric_name": "Cost article - Уборка",
        "currency_code": "RUB",
    },
    "Контекстная реклама_бюджет_ритейл": {
        "catalog_metric_name": "Marketing costs",
        "currency_code": "RUB",
        "channel_name": "direct",
    },
    "Контекст_бюджет_ритейл": {
        "catalog_metric_name": "Marketing costs",
        "currency_code": "RUB",
        "channel_name": "direct",
    },
    "Таргетированная реклама_бюджет": {
        "catalog_metric_name": "Marketing costs",
        "currency_code": "RUB",
        "channel_name": "social",
    },
    "Youtube_бюджет": {
        "catalog_metric_name": "Marketing costs",
        "currency_code": "RUB",
        "channel_name": "social",
    },
    "Размещение у блогеров, афишах, дзене, паблики_бюджет": {
        "catalog_metric_name": "Marketing costs",
        "currency_code": "RUB",
        "channel_name": "partners",
    },
    "Размещение у блогеров, афишах, дзене, паблики": {
        "catalog_metric_name": "Marketing costs",
        "currency_code": "RUB",
        "channel_name": "partners",
    },
    "Сложность составления расписания (1 min-5max)": {
        "catalog_metric_name": "Scheduling complexity",
        "currency_code": None,
    },
    "Приход с депозита": {
        "catalog_metric_name": "Revenue - Financial operations",
        "currency_code": "RUB",
    },
    "Спецпоказы (продажи) юкасса\\по счету": {
        "catalog_metric_name": "Revenue - Other",
        "currency_code": "RUB",
    },
    "Другое юкасса": {
        "catalog_metric_name": "Revenue - Other",
        "currency_code": "RUB",
    },
}

SUPPORTED_UNITS = {"b2c_moscow", "b2c_spb"}


SELECT_SQL = """
SELECT
    l.id,
    l.source_file_name,
    l.source_row_number,
    l.source_column_number,
    l.business_unit_raw,
    l.business_unit_key,
    l.metric_name,
    l.period_start,
    l.period_label,
    l.value_raw,
    l.value_numeric,
    l.value_type
FROM legacy_monthly_pnl_reference l
WHERE l.source_file_name = %(source_file_name)s
ORDER BY l.id
"""


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
    'legacy_monthly_pnl_csv',
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
    currency_code = EXCLUDED.currency_code,
    payload = EXCLUDED.payload,
    loaded_at = NOW()
"""

DELETE_SQL = """
DELETE FROM fact_metric_observation
WHERE source_system = 'legacy_monthly_pnl_csv'
  AND source_run_id = %(source_file_name)s
"""


def write_report(path: Path, loaded_rows, skipped_rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "status",
                "business_unit_raw",
                "business_unit_key",
                "legacy_metric_name",
                "catalog_metric_name",
                "reason",
                "row_count",
            ],
        )
        writer.writeheader()
        for row in loaded_rows:
            writer.writerow(row)
        for row in skipped_rows:
            writer.writerow(row)


def month_end(period_start: date) -> date:
    return period_start.replace(day=calendar.monthrange(period_start.year, period_start.month)[1])


def resolve_mapping(legacy_metric_name: str, business_unit_key: str):
    mapping = EXACT_METRIC_MAPPING.get(legacy_metric_name)
    if not mapping:
        return None

    resolved = dict(mapping)
    if resolved.get("catalog_metric_name") == "Revenue" and business_unit_key not in {"b2c_moscow", "b2c_spb", "franchise"}:
        return None
    if resolved.get("catalog_metric_name") == "Marketing costs" and business_unit_key not in {"b2c_moscow", "b2c_spb", "b2b"}:
        return None
    return resolved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source-file-name", required=True)
    parser.add_argument(
        "--report-path",
        default="/Users/Peter/Documents/Morpheus Metrics/generated/legacy_monthly_pnl_to_fact_import_report.csv",
    )
    parser.add_argument("--delete-existing", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(args.database_url)
    try:
        with conn, conn.cursor() as cur:
            if args.delete_existing:
                cur.execute(DELETE_SQL, {"source_file_name": args.source_file_name})
                print(f"deleted_existing_rows={cur.rowcount}")

            cur.execute("SELECT metric_id, metric_name FROM metric_catalogue")
            metric_ids = {name: metric_id for metric_id, name in cur.fetchall()}

            cur.execute(SELECT_SQL, {"source_file_name": args.source_file_name})
            source_rows = cur.fetchall()

            to_insert = []
            loaded_counts = {}
            skipped_counts = {}

            for (
                legacy_id,
                source_file_name,
                source_row_number,
                source_column_number,
                business_unit_raw,
                business_unit_key,
                legacy_metric_name,
                period_start,
                period_label,
                value_raw,
                value_numeric,
                value_type,
            ) in source_rows:
                mapping = resolve_mapping(legacy_metric_name, business_unit_key)
                if not mapping:
                    skipped_counts[(business_unit_raw, business_unit_key, legacy_metric_name, "", "no_catalog_mapping")] = (
                        skipped_counts.get((business_unit_raw, business_unit_key, legacy_metric_name, "", "no_catalog_mapping"), 0)
                        + 1
                    )
                    continue

                target_business_unit = mapping.get("force_business_unit", business_unit_key)

                if target_business_unit not in SUPPORTED_UNITS and target_business_unit not in {"franchise", "general", "b2b"}:
                    skipped_counts[(business_unit_raw, business_unit_key, legacy_metric_name, mapping["catalog_metric_name"], "unsupported_business_unit")] = (
                        skipped_counts.get((business_unit_raw, business_unit_key, legacy_metric_name, mapping["catalog_metric_name"], "unsupported_business_unit"), 0)
                        + 1
                    )
                    continue

                if value_numeric is None:
                    skipped_counts[(business_unit_raw, business_unit_key, legacy_metric_name, mapping["catalog_metric_name"], "non_numeric_value")] = (
                        skipped_counts.get((business_unit_raw, business_unit_key, legacy_metric_name, mapping["catalog_metric_name"], "non_numeric_value"), 0)
                        + 1
                    )
                    continue

                metric_id = metric_ids.get(mapping["catalog_metric_name"])
                if not metric_id:
                    skipped_counts[(business_unit_raw, business_unit_key, legacy_metric_name, mapping["catalog_metric_name"], "catalog_metric_missing_in_db")] = (
                        skipped_counts.get((business_unit_raw, business_unit_key, legacy_metric_name, mapping["catalog_metric_name"], "catalog_metric_missing_in_db"), 0)
                        + 1
                    )
                    continue

                to_insert.append(
                    {
                        "metric_id": metric_id,
                        "source_record_key": f"legacy_monthly_pnl_reference:{legacy_id}",
                        "source_run_id": source_file_name,
                        "business_unit": target_business_unit,
                        "period_start": period_start,
                        "period_end": month_end(period_start),
                        "value_numeric": value_numeric,
                        "value_raw": value_raw,
                        "currency_code": mapping["currency_code"],
                        "show_name": mapping.get("show_name"),
                        "partner_name": mapping.get("partner_name"),
                        "channel_name": mapping.get("channel_name"),
                        "payload": Json(
                            {
                                "legacy_source_table": "legacy_monthly_pnl_reference",
                                "legacy_id": legacy_id,
                                "legacy_metric_name": legacy_metric_name,
                                "business_unit_raw": business_unit_raw,
                                "period_label": period_label,
                                "source_file_name": source_file_name,
                                "source_row_number": source_row_number,
                                "source_column_number": source_column_number,
                                "legacy_value_type": value_type,
                                "target_business_unit": target_business_unit,
                                "target_show_name": mapping.get("show_name"),
                                "target_partner_name": mapping.get("partner_name"),
                                "target_channel_name": mapping.get("channel_name"),
                            }
                        ),
                    }
                )
                loaded_counts[(business_unit_raw, business_unit_key, legacy_metric_name, mapping["catalog_metric_name"], "loaded")] = (
                    loaded_counts.get((business_unit_raw, business_unit_key, legacy_metric_name, mapping["catalog_metric_name"], "loaded"), 0)
                    + 1
                )

            execute_batch(cur, INSERT_SQL, to_insert, page_size=500)

        loaded_rows = [
            {
                "status": status,
                "business_unit_raw": bu_raw or "",
                "business_unit_key": bu_key or "",
                "legacy_metric_name": legacy_metric_name,
                "catalog_metric_name": catalog_metric_name,
                "reason": "",
                "row_count": count,
            }
            for (bu_raw, bu_key, legacy_metric_name, catalog_metric_name, status), count in sorted(loaded_counts.items())
        ]
        skipped_rows = [
            {
                "status": "skipped",
                "business_unit_raw": bu_raw or "",
                "business_unit_key": bu_key or "",
                "legacy_metric_name": legacy_metric_name,
                "catalog_metric_name": catalog_metric_name,
                "reason": reason,
                "row_count": count,
            }
            for (bu_raw, bu_key, legacy_metric_name, catalog_metric_name, reason), count in sorted(skipped_counts.items())
        ]
        write_report(Path(args.report_path), loaded_rows, skipped_rows)
        print(f"inserted_rows={len(to_insert)} report_path={args.report_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
