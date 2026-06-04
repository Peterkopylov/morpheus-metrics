#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
SOURCE_MAPPING_PATH = ROOT / "generated/historical_sheet_canonical_metric_mapping.csv"
STRUCTURE_PATH = ROOT / "generated/pnl_structure_mapping_canonical.csv"
OUTPUT_MAPPING_PATH = ROOT / "generated/historical_leaf_pnl_metric_mapping.csv"
OUTPUT_REVIEW_PATH = ROOT / "generated/historical_leaf_pnl_metric_mapping_review.csv"


EXCLUDED_OPERATIONAL_METRICS = {
    "Number of shows",
    "Number of show visitors",
}

DIRECT_PNL_METRICS = {
    "Revenue",
    "Net profit",
    "Actor upsell sales",
    "Other income - Deposit interest",
    "Dividends",
    "Cost article - Директорский процент",
}

ROLLUP_LIKE_METRICS = {
    "Variable costs",
    "Fixed costs",
    "Investment costs",
    "Marketing costs",
    "Other expenses",
    "Venue and office costs",
    "Services and setup costs",
    "Team expenses",
    "Variable logistics costs",
    "Business travel costs",
    "Show production costs",
    "Costs - Salary variable",
    "Costs - Salary fixed",
    "Returns amount",
    "Annual bonuses",
    "Relocation costs",
}

GENERIC_ROLLUP_LABELS = {
    "переменные расходы",
    "постоянные расходы",
    "итого переменные расходы",
    "итого постоянные расходы",
    "маркетинг",
    "маркетинг и реклама",
    "итого расходы на маркетинг",
    "логистика",
    "прочие расходы",
    "инвестии в петербург",
    "итого, расходы инвестиции москва",
}

APPROVED_ROLLUP_ROWS = {
    59,
    65,
    76,
    77,
    107,
    108,
    111,
    112,
    118,
    136,
    138,
    170,
    169,
    188,
    192,
    198,
}


def normalize(value: str) -> str:
    return " ".join((value or "").replace("\xa0", " ").split()).strip()


def load_leaf_metrics() -> set[str]:
    with STRUCTURE_PATH.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return {
            normalize(row["canonical_metric"])
            for row in reader
            if normalize(row.get("node_role", "")) == "leaf" and normalize(row.get("canonical_metric", ""))
        }


def has_specific_dimension(row: dict[str, str]) -> bool:
    return any(normalize(row.get(key, "")).lower() not in {"", "general"} for key in ("show", "channel", "agent"))


def is_generic_rollup_label(label: str) -> bool:
    normalized = normalize(label).lower()
    if not normalized:
        return False
    if normalized in GENERIC_ROLLUP_LABELS:
        return True
    if normalized.startswith("итого"):
        return True
    return False


def classify_row(row: dict[str, str], leaf_metrics: set[str]) -> tuple[str, str]:
    layer = normalize(row.get("layer", "")).lower()
    metric = normalize(row.get("canonical_metric", ""))
    business_unit = normalize(row.get("business_unit", "")).lower()
    source_label = normalize(row.get("source_label", ""))
    row_number = int(row.get("row_number") or 0)

    if layer != "fact":
        return "exclude", "not_fact_layer"
    if metric == "Cost article - Директорский процент" and business_unit == "total":
        return "include", "special_total_leaf_metric"
    if row_number == 111 and metric == "Cost article - IT ФОТ":
        return "include", "approved_general_leaf_row"
    if business_unit in {"", "general", "total"}:
        return "exclude", "general_or_total_scope"
    if not metric:
        return "exclude", "missing_metric"
    if metric in EXCLUDED_OPERATIONAL_METRICS:
        return "exclude", "operational_metric"
    if row_number in APPROVED_ROLLUP_ROWS:
        return "include", "approved_lower_level_rollup_like_row"
    if is_generic_rollup_label(source_label):
        return "exclude", "generic_rollup_label"
    if metric in leaf_metrics:
        return "include", "canonical_leaf_metric"
    if has_specific_dimension(row):
        return "include", "fact_row_with_specific_dimension"
    if metric in DIRECT_PNL_METRICS:
        return "include", "direct_pnl_metric"
    if metric in ROLLUP_LIKE_METRICS:
        return "review", "rollup_like_metric_without_specific_dimension"
    return "review", "non_leaf_pnl_metric_needs_decision"


def main() -> None:
    leaf_metrics = load_leaf_metrics()
    included_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []

    with SOURCE_MAPPING_PATH.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        decision, reason = classify_row(row, leaf_metrics)
        if decision == "include":
            included_rows.append(row)
        elif decision == "review":
            review_rows.append(
                {
                    "row_number": row["row_number"],
                    "source_business_unit": row["source_business_unit"],
                    "source_label": row["source_label"],
                    "canonical_metric": row["canonical_metric"],
                    "business_unit": row["business_unit"],
                    "show": row["show"],
                    "channel": row["channel"],
                    "agent": row["agent"],
                    "review_reason": reason,
                    "mapping_note": row["mapping_note"],
                }
            )

    OUTPUT_MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_MAPPING_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(included_rows)

    with OUTPUT_REVIEW_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "row_number",
                "source_business_unit",
                "source_label",
                "canonical_metric",
                "business_unit",
                "show",
                "channel",
                "agent",
                "review_reason",
                "mapping_note",
            ],
        )
        writer.writeheader()
        writer.writerows(review_rows)

    print(
        f"Wrote {len(included_rows)} included rows to {OUTPUT_MAPPING_PATH} "
        f"and {len(review_rows)} review rows to {OUTPUT_REVIEW_PATH}"
    )


if __name__ == "__main__":
    main()
