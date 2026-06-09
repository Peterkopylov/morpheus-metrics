#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
GENERATED = ROOT / "generated"
LEGACY = ROOT / "legacy"

SOURCE_CATALOGUE = GENERATED / "metric_catalogue_canonical.csv"
SOURCE_OF_TRUTH = GENERATED / "fact_metric_source_of_truth_canonical.csv"
LEGACY_MAPPING_SOURCE = LEGACY / "generated" / "legacy_seed" / "metric_catalogue_v4.csv"

OUTPUT_CATALOGUE = GENERATED / "metric_catalogue_canonical.csv"
OUTPUT_SOURCE_OF_TRUTH = GENERATED / "fact_metric_source_of_truth_canonical.csv"
OUTPUT_LEGACY_MAPPING = GENERATED / "legacy_metric_mapping.csv"

EXCLUDED_CANONICAL_METRICS = {
    "Source share",
    "Quality - Internal",
}


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_metric_catalogue_canonical(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output = []
    for row in rows:
        if row["metric_name"] in EXCLUDED_CANONICAL_METRICS:
            continue
        output.append(
            {
                "metric_key": row["metric_key"],
                "metric_name": row["metric_name"],
                "metric_family": row["metric_family"],
                "value_kind": row["value_kind"],
                "description": row["description"],
            }
        )
    output.sort(key=lambda r: (r["metric_family"], r["metric_name"]))
    return output


def split_legacy_groups(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(";") if part.strip()]


def build_legacy_metric_mapping(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in rows:
        if "legacy_groups_covered" not in row:
            continue
        if row["metric_name"] in EXCLUDED_CANONICAL_METRICS:
            continue
        for legacy_group in split_legacy_groups(row["legacy_groups_covered"]):
            output.append(
                {
                    "metric_key": row["metric_key"],
                    "metric_name": row["metric_name"],
                    "legacy_group": legacy_group,
                    "mapping_type": "covered",
                    "legacy_mapping_status": row["legacy_mapping_status"],
                    "notes": row["legacy_notes_summary"],
                }
            )
        for legacy_group in split_legacy_groups(row["legacy_groups_partial"]):
            output.append(
                {
                    "metric_key": row["metric_key"],
                    "metric_name": row["metric_name"],
                    "legacy_group": legacy_group,
                    "mapping_type": "partial",
                    "legacy_mapping_status": row["legacy_mapping_status"],
                    "notes": row["legacy_notes_summary"],
                }
            )
    output.sort(key=lambda r: (r["legacy_group"], r["metric_name"], r["mapping_type"]))
    return output


def build_source_of_truth_canonical(
    source_of_truth_rows: list[dict[str, str]], catalogue_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    metric_key_by_name = {row["metric_name"]: row["metric_key"] for row in catalogue_rows}
    output = []
    for row in source_of_truth_rows:
        metric_name = row["metric_name"]
        if metric_name in EXCLUDED_CANONICAL_METRICS:
            continue
        metric_key = row.get("metric_key") or metric_key_by_name.get(metric_name, "")
        status_note = row.get("status_note", "")
        if row.get("source_system") == "manual_table":
            status_note = (
                "Mandatory full numeric reference layer: ingest all numeric values from manual tables even when "
                "the primary source for the metric is another system."
            )
        output.append(
            {
                "metric_key": metric_key,
                "metric_name": metric_name,
                "business_unit": row["business_unit"],
                "show_scope": row["show_scope"],
                "partner_scope": row["partner_scope"],
                "channel_scope": row["channel_scope"],
                "frequency": row["frequency"],
                "source_role": row["source_role"],
                "source_system": row["source_system"],
                "how_counted": row.get("how_counted", ""),
                "reference_doc": row.get("reference_doc", ""),
                "status_note": status_note,
                "source_row_ref": row.get("source_row_ref", ""),
            }
        )
    output.sort(
        key=lambda r: (
            r["metric_name"],
            r["business_unit"],
            r["show_scope"],
            r["partner_scope"],
            r["channel_scope"],
            {"primary": 0, "secondary": 1, "reference": 2, "pending": 3, "needs_decision": 4}.get(
                r["source_role"], 9
            ),
            r["source_system"],
        )
    )
    return output


def main() -> None:
    catalogue_rows = load_csv(SOURCE_CATALOGUE)
    source_of_truth_rows = load_csv(SOURCE_OF_TRUTH)
    legacy_mapping_rows = load_csv(LEGACY_MAPPING_SOURCE) if LEGACY_MAPPING_SOURCE.exists() else []

    write_csv(
        OUTPUT_CATALOGUE,
        build_metric_catalogue_canonical(catalogue_rows),
        ["metric_key", "metric_name", "metric_family", "value_kind", "description"],
    )
    write_csv(
        OUTPUT_SOURCE_OF_TRUTH,
        build_source_of_truth_canonical(source_of_truth_rows, catalogue_rows),
        [
            "metric_key",
            "metric_name",
            "business_unit",
            "show_scope",
            "partner_scope",
            "channel_scope",
            "frequency",
            "source_role",
            "source_system",
            "how_counted",
            "reference_doc",
            "status_note",
            "source_row_ref",
        ],
    )
    write_csv(
        OUTPUT_LEGACY_MAPPING,
        build_legacy_metric_mapping(legacy_mapping_rows),
        ["metric_key", "metric_name", "legacy_group", "mapping_type", "legacy_mapping_status", "notes"],
    )

    print(f"wrote {OUTPUT_CATALOGUE}")
    print(f"wrote {OUTPUT_SOURCE_OF_TRUTH}")
    print(f"wrote {OUTPUT_LEGACY_MAPPING}")


if __name__ == "__main__":
    main()
