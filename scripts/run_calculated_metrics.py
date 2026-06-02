#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import uuid
import re
from datetime import date, datetime, timedelta, timezone
from dataclasses import dataclass
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

from calculated_metric_registry import (
    ROOT,
    CalculatedMetricDefinition,
    ResolvedDependency,
    load_formula_registry,
    resolve_dependency,
)


DEFAULT_REPORT_PATH = ROOT / "generated" / "calculated_metrics_run_report.csv"
CREATE_SQL_PATH = ROOT / "sql" / "create_calculated_metric_tables.sql"
PARTNER_COMMISSION_RULES_PATH = ROOT / "generated" / "partner_commission_rate_registry.csv"


@dataclass(frozen=True)
class PartnerCommissionRule:
    partner_name: str
    canonical_partner_name: str
    commission_rate: float
    net_multiplier: float
    status: str
    note: str


def clip(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def normalize_scope_for_storage(value: str) -> str | None:
    return None if value == "general" else value


def normalize_partner_rule_key(value: str) -> str:
    lowered = (value or "").strip().lower().replace("ё", "е").replace("э", "е")
    return re.sub(r"[^a-zа-я0-9]+", "", lowered)


def period_end_for(period_granularity: str, period_start: date) -> date:
    if period_granularity == "week":
        return period_start + timedelta(days=6)
    if period_granularity == "month":
        next_month = (period_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return next_month - timedelta(days=1)
    raise ValueError(f"unsupported period_granularity: {period_granularity}")


def ensure_tables(conn) -> None:
    sql = CREATE_SQL_PATH.read_text(encoding="utf-8")
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def insert_run(conn, run_id: str, period_granularity: str, period_start: date, trigger_mode: str, step_keys: list[str]) -> None:
    started_at = datetime.now(timezone.utc)
    payload = Json({"step_keys": step_keys})
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO calculation_runs (
                    run_id, period_granularity, period_start, period_end, status, started_at, trigger_mode, payload
                )
                VALUES (%s, %s, %s, %s, 'running', %s, %s, %s)
                """,
                (run_id, period_granularity, period_start, period_end_for(period_granularity, period_start), started_at, trigger_mode, payload),
            )


def update_run_status(conn, run_id: str, status: str) -> None:
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE calculation_runs
                SET status = %s, finished_at = %s
                WHERE run_id = %s
                """,
                (status, datetime.now(timezone.utc), run_id),
            )


def upsert_definition(conn, definition: CalculatedMetricDefinition) -> int:
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO calculated_metric_definition (
                    calculated_metric_key,
                    calculated_metric_name,
                    period_granularity,
                    business_unit,
                    show_name,
                    partner_name,
                    channel_name,
                    value_kind,
                    formula_type,
                    numerator_metric_key,
                    denominator_metric_key,
                    status,
                    version,
                    notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                    calculated_metric_key,
                    period_granularity,
                    business_unit,
                    show_name_norm,
                    partner_name_norm,
                    channel_name_norm,
                    version
                )
                DO UPDATE SET
                    calculated_metric_name = EXCLUDED.calculated_metric_name,
                    value_kind = EXCLUDED.value_kind,
                    formula_type = EXCLUDED.formula_type,
                    numerator_metric_key = EXCLUDED.numerator_metric_key,
                    denominator_metric_key = EXCLUDED.denominator_metric_key,
                    status = EXCLUDED.status,
                    notes = EXCLUDED.notes,
                    updated_at = NOW()
                RETURNING definition_id
                """,
                (
                    definition.calculated_metric_key,
                    definition.calculated_metric_name,
                    definition.period_granularity,
                    definition.business_unit,
                    normalize_scope_for_storage(definition.show_name),
                    normalize_scope_for_storage(definition.partner_name),
                    normalize_scope_for_storage(definition.channel_name),
                    definition.value_kind,
                    definition.formula_type,
                    definition.numerator_metric_key,
                    definition.denominator_metric_key,
                    definition.status,
                    definition.version,
                    definition.notes,
                ),
            )
            return int(cur.fetchone()[0])


def replace_dependencies(conn, definition_id: int, dependencies: list[ResolvedDependency]) -> None:
    with conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM calculated_metric_dependency WHERE definition_id = %s", (definition_id,))
            for dependency in dependencies:
                cur.execute(
                    """
                    INSERT INTO calculated_metric_dependency (
                        definition_id,
                        dependency_role,
                        dependency_metric_key,
                        dependency_granularity,
                        dependency_source_system,
                        dependency_show_scope,
                        dependency_partner_scope,
                        dependency_channel_scope,
                        notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        definition_id,
                        dependency.dependency_role,
                        dependency.dependency_metric_key,
                        dependency.dependency_granularity,
                        dependency.dependency_source_system,
                        dependency.dependency_show_scope,
                        dependency.dependency_partner_scope,
                        dependency.dependency_channel_scope,
                        dependency.notes,
                    ),
                )


def upsert_step_log(
    conn,
    run_id: str,
    step_key: str,
    definition_id: int | None,
    definition: CalculatedMetricDefinition,
    period_start: date,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    exit_code: int | None,
    stdout_excerpt: str,
    stderr_excerpt: str,
    notes: str,
) -> None:
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO calculation_run_steps (
                    run_id,
                    step_key,
                    definition_id,
                    calculated_metric_key,
                    business_unit,
                    period_granularity,
                    period_start,
                    status,
                    started_at,
                    finished_at,
                    exit_code,
                    stdout_excerpt,
                    stderr_excerpt,
                    notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id, step_key)
                DO UPDATE SET
                    definition_id = EXCLUDED.definition_id,
                    status = EXCLUDED.status,
                    finished_at = EXCLUDED.finished_at,
                    exit_code = EXCLUDED.exit_code,
                    stdout_excerpt = EXCLUDED.stdout_excerpt,
                    stderr_excerpt = EXCLUDED.stderr_excerpt,
                    notes = EXCLUDED.notes
                """,
                (
                    run_id,
                    step_key,
                    definition_id,
                    definition.calculated_metric_key,
                    definition.business_unit,
                    definition.period_granularity,
                    period_start,
                    status,
                    started_at,
                    finished_at,
                    exit_code,
                    stdout_excerpt,
                    stderr_excerpt,
                    notes,
                ),
            )


def apply_dependency_scope_filters(where: list[str], params: list[object], dependency: ResolvedDependency) -> None:
    apply_dependency_scope_filters_with_options(where, params, dependency)


def apply_dependency_scope_filters_with_options(
    where: list[str],
    params: list[object],
    dependency: ResolvedDependency,
    *,
    scope_overrides: dict[str, str] | None = None,
    skip_columns: set[str] | None = None,
) -> None:
    if dependency.dependency_source_system:
        where.append("o.source_system = %s")
        params.append(dependency.dependency_source_system)

    overrides = scope_overrides or {}
    skipped = skip_columns or set()
    scope_columns = [
        ("show_name", dependency.dependency_show_scope),
        ("partner_name", dependency.dependency_partner_scope),
        ("channel_name", dependency.dependency_channel_scope),
    ]
    for column, scope_value in scope_columns:
        if column in skipped:
            continue
        if column in overrides:
            where.append(f"o.{column} = %s")
            params.append(overrides[column])
            continue
        if not scope_value:
            continue
        if scope_value == "general":
            where.append(f"COALESCE(o.{column}, 'general') = 'general'")
        else:
            where.append(f"o.{column} IS NOT NULL")


def dependency_sum(
    conn,
    definition: CalculatedMetricDefinition,
    dependency: ResolvedDependency,
    period_start: date,
    *,
    scope_overrides: dict[str, str] | None = None,
) -> float | None:
    if not dependency.dependency_metric_key or not dependency.dependency_source_system:
        return None

    where = [
        "mc.metric_key = %s",
        "o.period_granularity = %s",
        "o.period_start = %s",
        "o.business_unit = %s",
        "o.value_numeric IS NOT NULL",
    ]
    params: list[object] = [
        dependency.dependency_metric_key,
        dependency.dependency_granularity,
        period_start,
        definition.business_unit,
    ]
    apply_dependency_scope_filters_with_options(where, params, dependency, scope_overrides=scope_overrides)

    sql = f"""
        SELECT SUM(o.value_numeric)::float
        FROM fact_metric_observation o
        JOIN metric_catalogue mc
          ON mc.metric_id = o.metric_id
        WHERE {' AND '.join(where)}
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0])


def dynamic_scope_dimensions(definition: CalculatedMetricDefinition) -> list[str]:
    dimensions = []
    for column, scope_value in [
        ("show_name", definition.show_name),
        ("partner_name", definition.partner_name),
        ("channel_name", definition.channel_name),
    ]:
        if scope_value != "general" and scope_value.endswith("_names"):
            dimensions.append(column)
    return dimensions


def dependency_member_sums(
    conn,
    definition: CalculatedMetricDefinition,
    dependency: ResolvedDependency,
    period_start: date,
    member_dimension: str,
) -> dict[str, float]:
    if not dependency.dependency_metric_key or not dependency.dependency_source_system:
        return {}

    where = [
        "mc.metric_key = %s",
        "o.period_granularity = %s",
        "o.period_start = %s",
        "o.business_unit = %s",
        "o.value_numeric IS NOT NULL",
        f"o.{member_dimension} IS NOT NULL",
    ]
    params: list[object] = [
        dependency.dependency_metric_key,
        dependency.dependency_granularity,
        period_start,
        definition.business_unit,
    ]
    apply_dependency_scope_filters_with_options(where, params, dependency, skip_columns={member_dimension})

    sql = f"""
        SELECT o.{member_dimension}, SUM(o.value_numeric)::float
        FROM fact_metric_observation o
        JOIN metric_catalogue mc
          ON mc.metric_id = o.metric_id
        WHERE {' AND '.join(where)}
        GROUP BY o.{member_dimension}
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return {str(member_name): float(value) for member_name, value in rows if member_name and value is not None}


def dependency_member_combo_sums(
    conn,
    definition: CalculatedMetricDefinition,
    dependency: ResolvedDependency,
    period_start: date,
    member_dimensions: list[str],
) -> dict[tuple[str, ...], float]:
    if not dependency.dependency_metric_key or not dependency.dependency_source_system or not member_dimensions:
        return {}

    where = [
        "mc.metric_key = %s",
        "o.period_granularity = %s",
        "o.period_start = %s",
        "o.business_unit = %s",
        "o.value_numeric IS NOT NULL",
    ]
    params: list[object] = [
        dependency.dependency_metric_key,
        dependency.dependency_granularity,
        period_start,
        definition.business_unit,
    ]
    for member_dimension in member_dimensions:
        where.append(f"o.{member_dimension} IS NOT NULL")
    apply_dependency_scope_filters_with_options(where, params, dependency, skip_columns=set(member_dimensions))

    select_dimensions = ", ".join(f"o.{member_dimension}" for member_dimension in member_dimensions)
    group_by_dimensions = ", ".join(f"o.{member_dimension}" for member_dimension in member_dimensions)
    sql = f"""
        SELECT {select_dimensions}, SUM(o.value_numeric)::float
        FROM fact_metric_observation o
        JOIN metric_catalogue mc
          ON mc.metric_id = o.metric_id
        WHERE {' AND '.join(where)}
        GROUP BY {group_by_dimensions}
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    output: dict[tuple[str, ...], float] = {}
    for row in rows:
        *member_values, value = row
        if value is None or any(member_value is None for member_value in member_values):
            continue
        output[tuple(str(member_value) for member_value in member_values)] = float(value)
    return output


def build_member_overrides_multi(member_dimensions: list[str], member_values: tuple[str, ...]) -> dict[str, str]:
    return {dimension: value for dimension, value in zip(member_dimensions, member_values)}


def load_partner_commission_rules(path: Path = PARTNER_COMMISSION_RULES_PATH) -> dict[str, PartnerCommissionRule]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    output: dict[str, PartnerCommissionRule] = {}
    for row in rows:
        status = (row.get("status") or "").strip()
        if status != "active":
            continue
        rule = PartnerCommissionRule(
            partner_name=(row.get("partner_name") or "").strip(),
            canonical_partner_name=(row.get("canonical_partner_name") or "").strip(),
            commission_rate=float((row.get("commission_rate") or "0").strip()),
            net_multiplier=float((row.get("net_multiplier") or "0").strip()),
            status=status,
            note=(row.get("note") or "").strip(),
        )
        output[normalize_partner_rule_key(rule.partner_name)] = rule
    return output


def upsert_calculated_value(
    conn,
    definition_id: int,
    definition: CalculatedMetricDefinition,
    run_id: str,
    step_key: str,
    period_start: date,
    value_numeric: float,
    numerator_value: float,
    denominator_value: float,
    *,
    actual_show_name: str | None = None,
    actual_partner_name: str | None = None,
    actual_channel_name: str | None = None,
) -> None:
    payload = Json(
        {
            "formula_type": definition.formula_type,
            "numerator_metric_key": definition.numerator_metric_key,
            "denominator_metric_key": definition.denominator_metric_key,
            "numerator_value": numerator_value,
            "denominator_value": denominator_value,
            "actual_show_name": actual_show_name,
            "actual_partner_name": actual_partner_name,
            "actual_channel_name": actual_channel_name,
        }
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO calculated_metric_value (
                    definition_id,
                    calculation_run_id,
                    calculation_step_key,
                    calculated_metric_key,
                    calculated_metric_name,
                    business_unit,
                    show_name,
                    partner_name,
                    channel_name,
                    period_granularity,
                    period_start,
                    period_end,
                    value_numeric,
                    version,
                    calculated_at,
                    loaded_at,
                    payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                    calculated_metric_key,
                    business_unit,
                    show_name_norm,
                    partner_name_norm,
                    channel_name_norm,
                    period_granularity,
                    period_start,
                    period_end,
                    version
                )
                DO UPDATE SET
                    definition_id = EXCLUDED.definition_id,
                    calculation_run_id = EXCLUDED.calculation_run_id,
                    calculation_step_key = EXCLUDED.calculation_step_key,
                    calculated_metric_name = EXCLUDED.calculated_metric_name,
                    value_numeric = EXCLUDED.value_numeric,
                    calculated_at = EXCLUDED.calculated_at,
                    loaded_at = EXCLUDED.loaded_at,
                    payload = EXCLUDED.payload
                """,
                (
                    definition_id,
                    run_id,
                    step_key,
                    definition.calculated_metric_key,
                    definition.calculated_metric_name,
                    definition.business_unit,
                    actual_show_name if actual_show_name is not None else normalize_scope_for_storage(definition.show_name),
                    actual_partner_name if actual_partner_name is not None else normalize_scope_for_storage(definition.partner_name),
                    actual_channel_name if actual_channel_name is not None else normalize_scope_for_storage(definition.channel_name),
                    definition.period_granularity,
                    period_start,
                    period_end_for(definition.period_granularity, period_start),
                    value_numeric,
                    definition.version,
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                    payload,
                ),
            )


def build_step_key(definition: CalculatedMetricDefinition) -> str:
    return f"{definition.calculated_metric_key}__{definition.business_unit}__{definition.period_granularity}"


def build_member_overrides(member_dimension: str, member_name: str) -> dict[str, str]:
    return {member_dimension: member_name}


def dependencies_ready(
    definition: CalculatedMetricDefinition,
    numerator_dependency: ResolvedDependency,
    denominator_dependency: ResolvedDependency,
) -> bool:
    if definition.formula_type == "apply_partner_commission_rate":
        return bool(numerator_dependency.dependency_source_system)
    return bool(numerator_dependency.dependency_source_system and denominator_dependency.dependency_source_system)


def delete_existing_calculated_values(
    conn,
    definition: CalculatedMetricDefinition,
    period_start: date,
) -> None:
    period_end = period_end_for(definition.period_granularity, period_start)

    def append_scope_clause(where: list[str], params: list[object], column: str, scope_value: str) -> None:
        if scope_value == "general":
            where.append(f"{column} IS NULL")
        elif scope_value.endswith("_names"):
            where.append(f"{column} IS NOT NULL")
        else:
            where.append(f"{column} = %s")
            params.append(scope_value)

    where = [
        "calculated_metric_key = %s",
        "business_unit = %s",
        "period_granularity = %s",
        "period_start = %s",
        "period_end = %s",
        "version = %s",
    ]
    params: list[object] = [
        definition.calculated_metric_key,
        definition.business_unit,
        definition.period_granularity,
        period_start,
        period_end,
        definition.version,
    ]
    append_scope_clause(where, params, "show_name", definition.show_name)
    append_scope_clause(where, params, "partner_name", definition.partner_name)
    append_scope_clause(where, params, "channel_name", definition.channel_name)

    with conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM calculated_metric_value WHERE {' AND '.join(where)}", params)


def apply_formula(
    conn,
    definition_id: int,
    definition: CalculatedMetricDefinition,
    run_id: str,
    step_key: str,
    period_start: date,
    numerator_dependency: ResolvedDependency,
    denominator_dependency: ResolvedDependency,
) -> tuple[str, str]:
    member_dimensions = dynamic_scope_dimensions(definition)
    if len(member_dimensions) > 1 and definition.formula_type != "apply_partner_commission_rate":
        return "pending", "Current runner supports at most one dynamic member dimension per formula."

    if definition.formula_type == "ratio_of_sums":
        if not member_dimensions:
            numerator_value = dependency_sum(conn, definition, numerator_dependency, period_start)
            denominator_value = dependency_sum(conn, definition, denominator_dependency, period_start)
            if numerator_value is None or denominator_value is None:
                return "pending", "Missing numerator or denominator values in fact_metric_observation."
            if denominator_value == 0:
                return "pending", "Denominator is zero; calculated value was not written."
            value_numeric = numerator_value / denominator_value
            upsert_calculated_value(
                conn,
                definition_id,
                definition,
                run_id,
                step_key,
                period_start,
                value_numeric,
                numerator_value,
                denominator_value,
            )
            return "success", f"Calculated ratio_of_sums from {numerator_value:.6f} / {denominator_value:.6f}."

        member_dimension = member_dimensions[0]
        numerator_members = dependency_member_sums(conn, definition, numerator_dependency, period_start, member_dimension)
        denominator_members = dependency_member_sums(conn, definition, denominator_dependency, period_start, member_dimension)
        member_names = sorted(set(numerator_members) | set(denominator_members))
        if not member_names:
            return "pending", f"No member-level values found for dynamic dimension {member_dimension}."

        success_count = 0
        skipped_zero = 0
        skipped_missing = 0
        for member_name in member_names:
            numerator_value = numerator_members.get(member_name)
            denominator_value = denominator_members.get(member_name)
            if numerator_value is None or denominator_value is None:
                skipped_missing += 1
                continue
            if denominator_value == 0:
                skipped_zero += 1
                continue
            value_numeric = numerator_value / denominator_value
            overrides = build_member_overrides(member_dimension, member_name)
            upsert_calculated_value(
                conn,
                definition_id,
                definition,
                run_id,
                step_key,
                period_start,
                value_numeric,
                numerator_value,
                denominator_value,
                actual_show_name=overrides.get("show_name"),
                actual_partner_name=overrides.get("partner_name"),
                actual_channel_name=overrides.get("channel_name"),
            )
            success_count += 1

        if success_count == 0:
            return "pending", f"No member-level values were written for {member_dimension}; missing={skipped_missing}, zero_denominator={skipped_zero}."
        return "success", f"Calculated ratio_of_sums for {success_count} {member_dimension} members; missing={skipped_missing}, zero_denominator={skipped_zero}."

    if definition.formula_type == "share_of_partition_total":
        if len(member_dimensions) != 1:
            return "pending", "share_of_partition_total requires exactly one dynamic member dimension."

        member_dimension = member_dimensions[0]
        numerator_members = dependency_member_sums(conn, definition, numerator_dependency, period_start, member_dimension)
        denominator_value = dependency_sum(conn, definition, denominator_dependency, period_start)
        if not numerator_members:
            return "pending", f"No member-level numerator values found for dynamic dimension {member_dimension}."
        if denominator_value is None:
            return "pending", "Missing denominator values in fact_metric_observation."
        if denominator_value == 0:
            return "pending", "Denominator is zero; calculated values were not written."

        success_count = 0
        for member_name, numerator_value in sorted(numerator_members.items()):
            value_numeric = numerator_value / denominator_value
            overrides = build_member_overrides(member_dimension, member_name)
            upsert_calculated_value(
                conn,
                definition_id,
                definition,
                run_id,
                step_key,
                period_start,
                value_numeric,
                numerator_value,
                denominator_value,
                actual_show_name=overrides.get("show_name"),
                actual_partner_name=overrides.get("partner_name"),
                actual_channel_name=overrides.get("channel_name"),
            )
            success_count += 1

        return "success", f"Calculated share_of_partition_total for {success_count} {member_dimension} members from denominator {denominator_value:.6f}."

    if definition.formula_type == "allocate_total_by_partition_share":
        if len(member_dimensions) != 1:
            return "pending", "allocate_total_by_partition_share requires exactly one dynamic member dimension."

        member_dimension = member_dimensions[0]
        numerator_members = dependency_member_sums(conn, definition, numerator_dependency, period_start, member_dimension)
        allocated_total = dependency_sum(conn, definition, denominator_dependency, period_start)
        if not numerator_members:
            return "pending", f"No member-level numerator values found for dynamic dimension {member_dimension}."
        if allocated_total is None:
            return "pending", "Missing allocated total metric value in fact_metric_observation."

        numerator_total = sum(numerator_members.values())
        if numerator_total == 0:
            return "pending", "Sum of member-level numerator values is zero; allocated values were not written."

        success_count = 0
        for member_name, numerator_value in sorted(numerator_members.items()):
            value_numeric = (numerator_value / numerator_total) * allocated_total
            overrides = build_member_overrides(member_dimension, member_name)
            upsert_calculated_value(
                conn,
                definition_id,
                definition,
                run_id,
                step_key,
                period_start,
                value_numeric,
                numerator_value,
                allocated_total,
                actual_show_name=overrides.get("show_name"),
                actual_partner_name=overrides.get("partner_name"),
                actual_channel_name=overrides.get("channel_name"),
            )
            success_count += 1

        return "success", f"Allocated total {allocated_total:.6f} across {success_count} {member_dimension} members from numerator total {numerator_total:.6f}."

    if definition.formula_type == "apply_partner_commission_rate":
        if "partner_name" not in member_dimensions:
            return "pending", "apply_partner_commission_rate requires a dynamic partner dimension."
        if len(member_dimensions) > 2:
            return "pending", "apply_partner_commission_rate currently supports up to two dynamic dimensions."

        numerator_members = dependency_member_combo_sums(conn, definition, numerator_dependency, period_start, member_dimensions)
        if not numerator_members:
            return "pending", "No member-level revenue values found for the configured dynamic dimensions."

        partner_index = member_dimensions.index("partner_name")
        partner_rules = load_partner_commission_rules()
        success_count = 0
        skipped_missing_rate = 0
        for member_values, numerator_value in sorted(numerator_members.items()):
            partner_name = member_values[partner_index]
            partner_rule = partner_rules.get(normalize_partner_rule_key(partner_name))
            if not partner_rule:
                skipped_missing_rate += 1
                continue

            value_numeric = numerator_value * partner_rule.commission_rate
            overrides = build_member_overrides_multi(member_dimensions, member_values)
            upsert_calculated_value(
                conn,
                definition_id,
                definition,
                run_id,
                step_key,
                period_start,
                value_numeric,
                numerator_value,
                partner_rule.commission_rate,
                actual_show_name=overrides.get("show_name"),
                actual_partner_name=overrides.get("partner_name"),
                actual_channel_name=overrides.get("channel_name"),
            )
            success_count += 1

        if success_count == 0:
            return "pending", f"No commission rows were written; missing_rate={skipped_missing_rate}."
        return "success", f"Calculated partner commission for {success_count} member rows; missing_rate={skipped_missing_rate}."

    return "failed", f"Unsupported formula_type: {definition.formula_type}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run calculated metrics for a specific period.")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--period-granularity", required=True, choices=["week", "month"])
    parser.add_argument("--period-start", required=True, help="YYYY-MM-DD start of the period")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--include-pending", action="store_true", help="Sync pending formulas to the registry mirror as well")
    parser.add_argument("--trigger-mode", default="manual_cli")
    args = parser.parse_args()

    period_start = date.fromisoformat(args.period_start)
    definitions = [
        definition
        for definition in load_formula_registry()
        if definition.period_granularity == args.period_granularity
        and (args.include_pending or definition.status == "active")
    ]

    run_id = f"calculated_metrics_{args.period_granularity}_{period_start.isoformat()}_{uuid.uuid4().hex[:8]}"
    conn = psycopg2.connect(args.database_url)
    ensure_tables(conn)
    insert_run(conn, run_id, args.period_granularity, period_start, args.trigger_mode, [build_step_key(d) for d in definitions])

    fact_source_rows = None
    overall_status = "success"
    report_rows: list[dict[str, str]] = []

    for definition in definitions:
        started_at = datetime.now(timezone.utc)
        step_key = build_step_key(definition)
        stdout_excerpt = ""
        stderr_excerpt = ""
        definition_id: int | None = None
        try:
            definition_id = upsert_definition(conn, definition)
            numerator_dependency = resolve_dependency("numerator", definition.numerator_metric_key, definition, fact_source_rows)
            denominator_dependency = resolve_dependency("denominator", definition.denominator_metric_key, definition, fact_source_rows)
            replace_dependencies(conn, definition_id, [numerator_dependency, denominator_dependency])
            delete_existing_calculated_values(conn, definition, period_start)

            if definition.status != "active":
                status = "pending"
                notes = "Formula exists in registry but is not active."
            elif not dependencies_ready(definition, numerator_dependency, denominator_dependency):
                status = "pending"
                notes = "At least one dependency could not be resolved to a primary fact source."
            else:
                status, notes = apply_formula(
                    conn,
                    definition_id,
                    definition,
                    run_id,
                    step_key,
                    period_start,
                    numerator_dependency,
                    denominator_dependency,
                )
        except Exception as exc:  # noqa: BLE001
            status = "failed"
            notes = str(exc)
            stderr_excerpt = clip(repr(exc))

        finished_at = datetime.now(timezone.utc)
        upsert_step_log(
            conn,
            run_id,
            step_key,
            definition_id,
            definition,
            period_start,
            status,
            started_at,
            finished_at,
            0 if status in {"success", "pending"} else 1,
            stdout_excerpt,
            stderr_excerpt,
            notes,
        )
        report_rows.append(
            {
                "run_id": run_id,
                "period_granularity": args.period_granularity,
                "period_start": period_start.isoformat(),
                "step_key": step_key,
                "calculated_metric_key": definition.calculated_metric_key,
                "business_unit": definition.business_unit,
                "status": status,
                "notes": notes,
            }
        )
        if status == "failed":
            overall_status = "failed"
        elif status == "pending" and overall_status == "success":
            overall_status = "partial"

    if overall_status == "success" and any(row["status"] == "pending" for row in report_rows):
        overall_status = "partial"
    update_run_status(conn, run_id, overall_status)
    conn.close()

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "run_id",
                "period_granularity",
                "period_start",
                "step_key",
                "calculated_metric_key",
                "business_unit",
                "status",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(report_rows)

    print(
        json.dumps(
            {
                "run_id": run_id,
                "period_granularity": args.period_granularity,
                "period_start": period_start.isoformat(),
                "overall_status": overall_status,
                "steps_total": len(report_rows),
                "steps_success": sum(1 for row in report_rows if row["status"] == "success"),
                "steps_pending": sum(1 for row in report_rows if row["status"] == "pending"),
                "steps_failed": sum(1 for row in report_rows if row["status"] == "failed"),
                "report_path": str(report_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if overall_status in {"success", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
