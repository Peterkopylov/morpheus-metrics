#!/usr/bin/env python3
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
FORMULA_REGISTRY_PATH = ROOT / "generated" / "calculated_metric_formula_registry_canonical.csv"
FACT_SOURCE_OF_TRUTH_PATH = ROOT / "generated" / "fact_metric_source_of_truth_canonical.csv"


@dataclass(frozen=True)
class CalculatedMetricDefinition:
    calculated_metric_key: str
    calculated_metric_name: str
    period_granularity: str
    business_unit: str
    show_name: str
    partner_name: str
    channel_name: str
    value_kind: str
    formula_type: str
    numerator_metric_key: str | None
    denominator_metric_key: str | None
    status: str
    version: str
    notes: str

    @property
    def definition_key(self) -> tuple[str, str, str, str, str, str, str]:
        return (
            self.calculated_metric_key,
            self.period_granularity,
            self.business_unit,
            self.show_name,
            self.partner_name,
            self.channel_name,
            self.version,
        )


@dataclass(frozen=True)
class ResolvedDependency:
    dependency_role: str
    dependency_metric_key: str | None
    dependency_granularity: str
    dependency_source_system: str | None
    dependency_show_scope: str | None
    dependency_partner_scope: str | None
    dependency_channel_scope: str | None
    notes: str


def normalize_scope(value: str | None) -> str:
    raw = (value or "").strip()
    return raw or "general"


def load_formula_registry(path: Path = FORMULA_REGISTRY_PATH) -> list[CalculatedMetricDefinition]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [
            CalculatedMetricDefinition(
                calculated_metric_key=(row.get("calculated_metric_key") or "").strip(),
                calculated_metric_name=(row.get("calculated_metric_name") or "").strip(),
                period_granularity=(row.get("period_granularity") or "").strip(),
                business_unit=(row.get("business_unit") or "").strip(),
                show_name=normalize_scope(row.get("show_name")),
                partner_name=normalize_scope(row.get("partner_name")),
                channel_name=normalize_scope(row.get("channel_name")),
                value_kind=(row.get("value_kind") or "").strip(),
                formula_type=(row.get("formula_type") or "").strip(),
                numerator_metric_key=((row.get("numerator_metric_key") or "").strip() or None),
                denominator_metric_key=((row.get("denominator_metric_key") or "").strip() or None),
                status=(row.get("status") or "").strip(),
                version=(row.get("version") or "").strip(),
                notes=(row.get("notes") or "").strip(),
            )
            for row in reader
        ]


def select_formula_definitions(
    period_granularity: str,
    statuses: Iterable[str] = ("active",),
    path: Path = FORMULA_REGISTRY_PATH,
) -> list[CalculatedMetricDefinition]:
    allowed_statuses = set(statuses)
    return [
        definition
        for definition in load_formula_registry(path)
        if definition.period_granularity == period_granularity and definition.status in allowed_statuses
    ]


def _scope_matches(candidate_scope: str, target_scope: str) -> bool:
    # A general fact row can back a more specific calculated scope when the
    # formula needs a partition total (for example allocate total website orders
    # across channel members).
    return candidate_scope == target_scope or candidate_scope == "general" or target_scope == "general"


def _scope_specificity(source_row: dict[str, str]) -> int:
    scopes = [
        source_row.get("show_scope", ""),
        source_row.get("partner_scope", ""),
        source_row.get("channel_scope", ""),
    ]
    return sum(1 for scope in scopes if scope and scope != "general")


def _load_fact_source_rows(path: Path = FACT_SOURCE_OF_TRUTH_PATH) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def resolve_dependency(
    dependency_role: str,
    dependency_metric_key: str | None,
    definition: CalculatedMetricDefinition,
    fact_source_rows: list[dict[str, str]] | None = None,
) -> ResolvedDependency:
    if not dependency_metric_key:
        return ResolvedDependency(
            dependency_role=dependency_role,
            dependency_metric_key=None,
            dependency_granularity=definition.period_granularity,
            dependency_source_system=None,
            dependency_show_scope=None,
            dependency_partner_scope=None,
            dependency_channel_scope=None,
            notes="Dependency metric is not configured yet.",
        )

    rows = fact_source_rows if fact_source_rows is not None else _load_fact_source_rows()
    candidates = []
    for row in rows:
        if (row.get("metric_key") or "").strip() != dependency_metric_key:
            continue
        if (row.get("business_unit") or "").strip() != definition.business_unit:
            continue
        if (row.get("frequency") or "").strip() != definition.period_granularity:
            continue
        if (row.get("source_role") or "").strip() != "primary":
            continue
        candidates.append(row)

    if not candidates:
        return ResolvedDependency(
            dependency_role=dependency_role,
            dependency_metric_key=dependency_metric_key,
            dependency_granularity=definition.period_granularity,
            dependency_source_system=None,
            dependency_show_scope=None,
            dependency_partner_scope=None,
            dependency_channel_scope=None,
            notes="No primary source-of-truth row found for dependency.",
        )

    target_show = definition.show_name
    target_partner = definition.partner_name
    target_channel = definition.channel_name

    exact = [
        row
        for row in candidates
        if normalize_scope(row.get("show_scope")) == target_show
        and normalize_scope(row.get("partner_scope")) == target_partner
        and normalize_scope(row.get("channel_scope")) == target_channel
    ]
    if exact:
        chosen = sorted(exact, key=_scope_specificity)[0]
    else:
        fallback = [
            row
            for row in candidates
            if _scope_matches(normalize_scope(row.get("show_scope")), target_show)
            and _scope_matches(normalize_scope(row.get("partner_scope")), target_partner)
            and _scope_matches(normalize_scope(row.get("channel_scope")), target_channel)
        ]
        if not fallback:
            return ResolvedDependency(
                dependency_role=dependency_role,
                dependency_metric_key=dependency_metric_key,
                dependency_granularity=definition.period_granularity,
                dependency_source_system=None,
                dependency_show_scope=None,
                dependency_partner_scope=None,
                dependency_channel_scope=None,
                notes="No compatible source-of-truth row found for dependency scope.",
            )
        chosen = sorted(fallback, key=_scope_specificity)[0]

    return ResolvedDependency(
        dependency_role=dependency_role,
        dependency_metric_key=dependency_metric_key,
        dependency_granularity=definition.period_granularity,
        dependency_source_system=(chosen.get("source_system") or "").strip() or None,
        dependency_show_scope=normalize_scope(chosen.get("show_scope")),
        dependency_partner_scope=normalize_scope(chosen.get("partner_scope")),
        dependency_channel_scope=normalize_scope(chosen.get("channel_scope")),
        notes="Resolved from fact_metric_source_of_truth_canonical.csv primary source row.",
    )
