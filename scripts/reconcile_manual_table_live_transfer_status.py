#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


UPD_TARGET_MAP = {
    "UPD: Revenue": ("map_to_metric", "Revenue"),
    "UPD: Defer_to_calculated": ("defer_to_calculated", ""),
    "UPD: number_of_cancelled_sd_shows_no_tickets_sold": (
        "map_to_metric",
        "Number of cancelled SD shows - no tickets sold",
    ),
    "UPD: number_of_cancelled_sd_shows_special_shows": (
        "map_to_metric",
        "Number of cancelled SD shows - special shows",
    ),
    "UPD: number_of_cancelled_sd_shows_actor_master_shortage": (
        "map_to_metric",
        "Number of cancelled SD shows - actor/master shortage",
    ),
}


def read_semicolon_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def read_comma_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalize_reviewed_target(raw_target: str, fallback_reason: str) -> tuple[str, str, str]:
    raw_target = (raw_target or "").strip()
    if raw_target in UPD_TARGET_MAP:
        action, target = UPD_TARGET_MAP[raw_target]
        return raw_target, action, target
    if raw_target:
        return raw_target, "map_to_metric", raw_target
    if fallback_reason == "not_map_to_metric":
        return raw_target, "exclude", ""
    return raw_target, "", ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewed-csv", required=True)
    parser.add_argument("--import-report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    reviewed_rows = read_semicolon_csv(Path(args.reviewed_csv))
    import_rows = read_comma_csv(Path(args.import_report))
    import_by_key = {
        (row["sheet_unit"], row["row_number"]): row
        for row in import_rows
    }

    out_rows: list[dict[str, str]] = []
    final_counter: Counter[str] = Counter()
    reason_counter: Counter[str] = Counter()

    for row in reviewed_rows:
        key = (row["sheet_unit"], row["row_number"])
        import_row = import_by_key.get(key)

        reviewed_target, effective_action, effective_target = normalize_reviewed_target(
            row.get("target_metric_or_metrics", ""),
            row.get("reason", ""),
        )

        latest_status = import_row["status"] if import_row else ""
        latest_reason = import_row["reason"] if import_row else row.get("reason", "")

        if effective_action == "defer_to_calculated":
            final_status = "не переносим в fact layer"
            final_reason = "explicitly_deferred_to_calculated"
        elif latest_status == "inserted":
            final_status = "перенесено"
            final_reason = ""
        else:
            final_status = "не перенесено"
            final_reason = latest_reason or row.get("reason", "")

        final_counter[final_status] += 1
        reason_counter[final_reason or "inserted"] += 1

        out_rows.append(
            {
                "sheet_unit": row["sheet_unit"],
                "row_number": row["row_number"],
                "col_a": row["col_a"],
                "col_b": row["col_b"],
                "value": row["value"],
                "reviewed_target_metric_or_metrics": reviewed_target,
                "effective_ingestion_action": effective_action,
                "effective_target_metric_or_metrics": effective_target,
                "latest_import_status": latest_status,
                "latest_import_reason": latest_reason,
                "final_status": final_status,
                "final_reason": final_reason,
                "source_cell_a1": row["source_cell_a1"],
                "source_cell_url": row["source_cell_url"],
            }
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sheet_unit",
        "row_number",
        "col_a",
        "col_b",
        "value",
        "reviewed_target_metric_or_metrics",
        "effective_ingestion_action",
        "effective_target_metric_or_metrics",
        "latest_import_status",
        "latest_import_reason",
        "final_status",
        "final_reason",
        "source_cell_a1",
        "source_cell_url",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"wrote {out_path}")
    print("final_status", dict(final_counter))
    print("final_reason", dict(reason_counter))


if __name__ == "__main__":
    main()
