#!/usr/bin/env python3
from __future__ import annotations

import csv
from itertools import product
from pathlib import Path


OUTPUT_PATH = Path("/Users/Peter/Documents/Morpheus Metrics/generated/metric_sources_matrix.csv")


METRICS = [
    "Marketing costs",
    "Website visits",
    "Number of leads",
    "Number of creative meetings",
    "Number of orders",
    "Number of tickets",
    "Number of certificates",
    "Revenue",
    "Number of shows",
    "Number of shows cancelled",
    "Number of show visitors",
    "Costs - Salary variable",
    "Costs - Salary fixed",
    "Costs - Other (by articles)",
    "Quality - External",
    "Quality - Internal",
    "Source share",
    "Account balance",
]


BUSINESS_UNITS = [
    "b2c Moscow",
    "b2c SPB",
    "b2b",
    "franchise",
    "general",
]


SHOWS = [
    "b2b shows names",
    "b2c shows names",
    "general",
]


AGENTS = [
    "b2b agents names",
    "b2c agents names",
]


CHANNELS = [
    "marketing channels names",
]


def is_consistent_combination(business_unit: str, show: str, agent: str) -> bool:
    if business_unit == "b2b":
        return show in {"b2b shows names", "general"} and agent in {"b2b agents names", ""}
    if business_unit in {"b2c Moscow", "b2c SPB"}:
        return show in {"b2c shows names", "general"} and agent in {"b2c agents names", ""}
    if business_unit in {"franchise", "general"}:
        return show == "general" and agent == ""
    return False


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    header = [
        "Metric name",
        "Value",
        "Period start",
        "Period end",
        "Business unit",
        "Show",
        "Agent",
        "Channel",
        "Source",
        "Credibility",
    ]

    rows = []
    for metric, business_unit, show, agent, channel in product(
        METRICS,
        BUSINESS_UNITS,
        SHOWS,
        AGENTS,
        CHANNELS,
    ):
        if not is_consistent_combination(business_unit, show, agent):
            continue
        rows.append(
            [
                metric,
                "number",
                "",
                "",
                business_unit,
                show,
                agent,
                channel,
                "",
                "",
            ]
        )

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
