#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_batch


def load_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def prepare_metric_catalogue_rows(rows):
    prepared = []
    for row in rows:
        prepared.append(
            {
                "metric_key": row["metric_key"],
                "metric_name": row["metric_name"],
                "metric_family": row["metric_family"],
                "value_kind": row["value_kind"],
                "description": row.get("description", "") or "",
                "legacy_mapping_status": row.get("legacy_mapping_status", "") or "",
                "legacy_groups_covered": row.get("legacy_groups_covered", "") or "",
                "legacy_groups_partial": row.get("legacy_groups_partial", "") or "",
                "legacy_group_count_covered": row.get("legacy_group_count_covered", "") or "0",
                "legacy_group_count_partial": row.get("legacy_group_count_partial", "") or "0",
                "legacy_notes_summary": row.get("legacy_notes_summary", "") or "",
            }
        )
    return prepared


def seed_metric_catalogue(cur, rows):
    sql = """
    INSERT INTO metric_catalogue (
        metric_key,
        metric_name,
        metric_family,
        value_kind,
        description,
        legacy_mapping_status,
        legacy_groups_covered,
        legacy_groups_partial,
        legacy_group_count_covered,
        legacy_group_count_partial,
        legacy_notes_summary
    )
    VALUES (
        %(metric_key)s,
        %(metric_name)s,
        %(metric_family)s,
        %(value_kind)s,
        %(description)s,
        %(legacy_mapping_status)s,
        %(legacy_groups_covered)s,
        %(legacy_groups_partial)s,
        %(legacy_group_count_covered)s,
        %(legacy_group_count_partial)s,
        %(legacy_notes_summary)s
    )
    ON CONFLICT (metric_key)
    DO UPDATE SET
        metric_name = EXCLUDED.metric_name,
        metric_family = EXCLUDED.metric_family,
        value_kind = EXCLUDED.value_kind,
        description = EXCLUDED.description,
        legacy_mapping_status = EXCLUDED.legacy_mapping_status,
        legacy_groups_covered = EXCLUDED.legacy_groups_covered,
        legacy_groups_partial = EXCLUDED.legacy_groups_partial,
        legacy_group_count_covered = EXCLUDED.legacy_group_count_covered,
        legacy_group_count_partial = EXCLUDED.legacy_group_count_partial,
        legacy_notes_summary = EXCLUDED.legacy_notes_summary,
        updated_at = NOW()
    """
    execute_batch(cur, sql, rows, page_size=200)


def seed_scope_dictionaries(cur, rows):
    dict_rows = []
    seen = set()
    for row in rows:
        key = row["dictionary_key"]
        group = row["dictionary_group"]
        if key in seen:
            continue
        seen.add(key)
        dict_rows.append(
            {
                "dictionary_group": group,
                "dictionary_key": key,
                "description": row.get("note") or "",
            }
        )

    sql_dict = """
    INSERT INTO metric_scope_dictionary (
        dictionary_group,
        dictionary_key,
        description
    )
    VALUES (
        %(dictionary_group)s,
        %(dictionary_key)s,
        %(description)s
    )
    ON CONFLICT (dictionary_key)
    DO UPDATE SET
        dictionary_group = EXCLUDED.dictionary_group,
        description = EXCLUDED.description,
        updated_at = NOW()
    """
    execute_batch(cur, sql_dict, dict_rows, page_size=100)

    cur.execute("SELECT dictionary_id, dictionary_key FROM metric_scope_dictionary")
    dictionary_ids = {key: dictionary_id for dictionary_id, key in cur.fetchall()}

    value_rows = []
    for idx, row in enumerate(rows, start=1):
        value_rows.append(
            {
                "dictionary_id": dictionary_ids[row["dictionary_key"]],
                "value_key": row["value_key"],
                "value_label": row["value_label"],
                "sort_order": idx,
                "note": row.get("note") or "",
            }
        )

    sql_value = """
    INSERT INTO metric_scope_dictionary_value (
        dictionary_id,
        value_key,
        value_label,
        sort_order,
        note
    )
    VALUES (
        %(dictionary_id)s,
        %(value_key)s,
        %(value_label)s,
        %(sort_order)s,
        %(note)s
    )
    ON CONFLICT (dictionary_id, value_key)
    DO UPDATE SET
        value_label = EXCLUDED.value_label,
        sort_order = EXCLUDED.sort_order,
        note = EXCLUDED.note,
        updated_at = NOW()
    """
    execute_batch(cur, sql_value, value_rows, page_size=500)


def seed_collection_rules(cur, rows):
    cur.execute("SELECT metric_id, metric_name FROM metric_catalogue")
    metric_ids = {name: metric_id for metric_id, name in cur.fetchall()}

    sql = """
    INSERT INTO metric_collection_rule (
        metric_id,
        business_unit_scope,
        show_scope,
        partner_scope,
        channel_scope,
        source_system,
        source_label,
        minimal_frequency,
        availability_status,
        credibility,
        source_row_ref
    )
    VALUES (
        %(metric_id)s,
        %(business_unit_scope)s,
        NULLIF(%(show_scope)s, ''),
        NULLIF(%(partner_scope)s, ''),
        NULLIF(%(channel_scope)s, ''),
        NULLIF(%(source_system)s, ''),
        NULLIF(%(source_label)s, ''),
        NULLIF(%(minimal_frequency)s, ''),
        %(availability_status)s,
        NULLIF(%(credibility)s, ''),
        %(source_row_ref)s
    )
    ON CONFLICT (
        metric_id,
        business_unit_scope,
        show_scope_norm,
        partner_scope_norm,
        channel_scope_norm,
        source_system_norm
    )
    DO UPDATE SET
        source_label = EXCLUDED.source_label,
        minimal_frequency = EXCLUDED.minimal_frequency,
        availability_status = EXCLUDED.availability_status,
        credibility = EXCLUDED.credibility,
        source_row_ref = EXCLUDED.source_row_ref,
        updated_at = NOW()
    """

    prepared = []
    for row in rows:
        metric_id = metric_ids.get(row["metric_name"])
        if not metric_id:
            continue
        prepared.append(
            {
                **row,
                "metric_id": metric_id,
            }
        )
    execute_batch(cur, sql, prepared, page_size=500)


def prepare_collection_rules(rows):
    if not rows:
        return rows
    if "business_unit_scope" in rows[0]:
        return rows

    source_label_map = {
        "planfact": "PlanFact",
        "manual_table": "Таблица",
        "erp": "ERP",
        "yandex_tickets": "Yandex Tickets",
        "yandex_metrica": "Yandex.Metrica",
        "yandex_direct": "Yandex.Direct",
        "amocrm": "amoCRM",
        "airtable": "Airtable",
        "aggregate": "Агрегат",
        "": "",
    }
    availability_map = {
        "primary": "available",
        "secondary": "available",
        "reference": "available",
        "pending": "not_available_yet",
        "needs_decision": "unspecified",
    }

    prepared = []
    for row in rows:
        source_system = row.get("source_system", "") or ""
        source_role = row.get("source_role", "") or ""
        prepared.append(
            {
                "metric_name": row["metric_name"],
                "business_unit_scope": row["business_unit"],
                "show_scope": row["show_scope"],
                "partner_scope": row["partner_scope"],
                "channel_scope": row["channel_scope"],
                "source_system": source_system,
                "source_label": source_label_map.get(source_system, source_system),
                "minimal_frequency": row["frequency"],
                "availability_status": availability_map.get(source_role, "available"),
                "credibility": "",
                "source_row_ref": row.get("source_row_ref", "") or "",
            }
        )
    return prepared


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument(
        "--metric-catalogue-csv",
        default="/Users/Peter/Documents/Morpheus Metrics/catalog/metric_catalogue_canonical.csv",
    )
    parser.add_argument(
        "--metric-sources-csv",
        default="/Users/Peter/Documents/Morpheus Metrics/fact/source_of_truth.csv",
    )
    parser.add_argument(
        "--dictionaries-csv",
        default="/Users/Peter/Documents/Morpheus Metrics/artifacts/snapshots/metric_scope_dictionary_canonical.csv",
    )
    args = parser.parse_args()

    metric_catalogue_rows = prepare_metric_catalogue_rows(load_csv(Path(args.metric_catalogue_csv)))
    metric_sources_rows = prepare_collection_rules(load_csv(Path(args.metric_sources_csv)))
    dictionary_rows = load_csv(Path(args.dictionaries_csv))

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                seed_metric_catalogue(cur, metric_catalogue_rows)
                seed_scope_dictionaries(cur, dictionary_rows)
                seed_collection_rules(cur, metric_sources_rows)
        print(
            f"seeded metric_catalogue={len(metric_catalogue_rows)} "
            f"scope_values={len(dictionary_rows)} collection_rules={len(metric_sources_rows)}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
