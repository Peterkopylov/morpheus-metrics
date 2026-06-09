#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from planfact_monthly_pnl_report_mapping import PLANFACT_MONTHLY_PNL_REPORT_METRICS


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
SOURCE_RULES = ROOT / "generated" / "legacy_seed" / "metric_sources_v5.csv"
OUTPUT = ROOT / "generated" / "fact_metric_source_of_truth.csv"

MANUAL_WEEKLY_PRIMARY_METRICS = {
    "Returns amount - theater fault",
    "Returns amount - non-theater fault",
    "Number of cancelled non-SD shows - no tickets sold",
    "Number of cancelled non-SD shows - special shows",
    "Number of cancelled non-SD shows - actor/master shortage",
    "Number of cancelled SD shows - no tickets sold",
    "Number of cancelled SD shows - special shows",
    "Number of cancelled SD shows - actor/master shortage",
    "Number of new Yandex Maps reviews",
    "Number of genuine reviews",
    "Number of non-genuine reviews",
    "Average review rating weekly overall",
    "Average review rating weekly genuine",
    "Share of negative reviews from visitors",
    "Number of resolved negative reviews",
    "Average review rating weekly without negatives after resolution",
    "Average review rating overall",
    "Number of reviewed shows",
    "Share of reviewed shows without violations",
    "Number of warnings",
    "Number of fines",
    "Number of show removals",
    "Number of reviewed OGs",
    "Number of completed OG protocols",
}

AMOCRM_WEEKLY_FLOW_METRICS = {
    "Number of leads",
    "Number of contacts established",
    "Number of qualified leads",
    "Number of concepts sent",
    "Number of creative meetings scheduled",
    "Number of creative meetings",
    "Number of proposals sent",
    "Number of contracts sent",
    "Number of contracts approved",
    "Number of payments received",
    "Number of orders",
    "Number of lost leads",
}


def load_rows() -> list[dict[str, str]]:
    with SOURCE_RULES.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def augment_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    extra: list[dict[str, str]] = []
    for metric in ("Revenue", "Number of tickets", "Number of orders"):
        for bu in ("b2c_moscow", "b2c_spb"):
            for show_scope, partner_scope, channel_scope in (
                ("general", "", ""),
                ("b2c_show_names", "", ""),
                ("", "b2c_partner_names", ""),
            ):
                extra.append(
                    {
                        "metric_name": metric,
                        "business_unit_scope": bu,
                        "show_scope": show_scope,
                        "partner_scope": partner_scope,
                        "channel_scope": channel_scope,
                        "source_system": "yandex_tickets",
                        "source_label": "Yandex Tickets",
                        "minimal_frequency": "week",
                        "availability_status": "decided_primary",
                        "credibility": "",
                        "source_row_ref": "yandex_tickets_fact_layer_decision_2026_05_02",
                    }
                )

    # Actual ERP weekly general variable salary logic is already implemented, even if the
    # original rules still mention `aggregate`.
    for bu in ("b2c_moscow", "b2c_spb"):
        extra.append(
            {
                "metric_name": "Costs - Salary variable",
                "business_unit_scope": bu,
                "show_scope": "general",
                "partner_scope": "",
                "channel_scope": "",
                "source_system": "erp",
                "source_label": "ERP",
                "minimal_frequency": "week",
                "availability_status": "decided_primary",
                "credibility": "",
                "source_row_ref": "erp_salary_variable_logic_2026_05_02",
            }
        )
    return rows + extra


def role_for(row: dict[str, str]) -> str:
    metric = row["metric_name"]
    bu = row["business_unit_scope"]
    show_scope = row["show_scope"]
    partner_scope = row["partner_scope"]
    channel_scope = row["channel_scope"]
    source = row["source_system"]
    freq = row["minimal_frequency"]
    status = row["availability_status"]

    if status == "not_available_yet" or source == "not_available_yet":
        return "pending"
    if status == "unspecified" or not source:
        return "needs_decision"

    if metric in {"Revenue", "Number of tickets", "Number of orders"} and bu in {"b2c_moscow", "b2c_spb"}:
        if source == "yandex_tickets" and channel_scope == "":
            return "primary"
        if source == "manual_table" and channel_scope == "marketing_channel_names":
            return "primary"
        if source == "erp":
            return "secondary"
        if source == "manual_table":
            return "reference"

    if metric == "Marketing costs":
        if source == "yandex_direct":
            return "primary"
        if source == "yandex_metrica":
            return "reference"

    if metric == "Website visits" and source == "yandex_metrica":
        return "primary"

    if metric in {"Number of shows", "Number of show visitors", "Number of shows cancelled"}:
        if source == "erp":
            return "primary"
        if source == "manual_table":
            return "reference"

    if metric == "Costs - Salary variable":
        if bu in {"b2c_moscow", "b2c_spb"} and source == "erp":
            return "primary"
        if source == "aggregate":
            return "reference"
        if source in {"planfact", "airtable"}:
            return "primary"

    if metric in {
        "Number of post-show survey responses",
        "Number of show rating responses",
        "Sum of post-show ratings",
        "Number of source-attribution responses",
        "Number of question 3 responses",
        "Number of question 4 responses",
    } and source == "erp":
        return "primary"

    if metric == "Quality - Internal":
        if source == "erp":
            return "primary"
        if source == "aggregate":
            return "reference"

    if metric == "Quality - External":
        if source == "manual_table":
            return "primary"

    if metric in MANUAL_WEEKLY_PRIMARY_METRICS and source == "manual_table":
        return "primary"

    if metric == "Number of certificates" and source == "manual_table":
        return "primary"

    if metric in AMOCRM_WEEKLY_FLOW_METRICS:
        if source == "amocrm":
            return "primary"
        if source == "manual_table":
            return "primary"

    if metric == "Account balance":
        if freq == "week" and source == "manual_table":
            return "primary"
        if freq == "month" and source == "planfact":
            return "primary"

    if metric.startswith("Cost article -"):
        if source == "planfact":
            return "primary"

    if metric in {"Costs - Salary fixed", "Costs - Other (by articles)"}:
        if source == "planfact":
            return "primary"
        if source == "aggregate":
            return "reference"

    return "primary" if source in {"planfact", "erp", "yandex_metrica", "yandex_direct", "airtable", "amocrm"} else "reference"


def where_from(row: dict[str, str]) -> str:
    mapping = {
        "yandex_tickets": "Yandex Tickets API",
        "erp": "ERP API",
        "yandex_metrica": "Yandex Metrica API",
        "yandex_direct": "Yandex Direct Reports API",
        "manual_table": "Legacy weekly Google Sheets / fact_metrics",
        "planfact": "PlanFact reference layer",
        "amocrm": "amoCRM API",
        "airtable": "Airtable",
        "aggregate": "Derived aggregate layer",
        "not_available_yet": "Pending source",
        "": "Unspecified source",
    }
    return mapping.get(row["source_system"], row["source_system"])


def how_counted(row: dict[str, str]) -> str:
    metric = row["metric_name"]
    bu = row["business_unit_scope"]
    source = row["source_system"]
    channel_scope = row["channel_scope"]
    show_scope = row["show_scope"]

    if source == "yandex_tickets":
        return "crm.order.list, sold-only: exclude status=0 and is_returned=1; aggregate by order/event/agent; event_id -> crm.report.event"
    if source == "erp" and metric in {"Revenue", "Number of tickets", "Number of orders"}:
        return "POST /tickets/by-sell; positive totals only; joined to shows/get where needed; used as secondary ticket-sales reference"
    if source == "erp" and metric in {"Number of shows", "Number of show visitors", "Number of shows cancelled"}:
        return "POST /shows/get; aggregate by event_title/general using guests, cancelled and show_start"
    if source == "erp" and metric == "Costs - Salary variable":
        return "salaries/period salary_payed by show plus bonuses; unresolved bonus tail goes into general"
    if source == "erp" and metric in {
        "Number of post-show survey responses",
        "Number of show rating responses",
        "Sum of post-show ratings",
        "Number of source-attribution responses",
        "Number of question 3 responses",
        "Number of question 4 responses",
    }:
        return "POST /survey/satisfaction; aggregate answers[1]/[2]/[3]/[4] by seance_name and/or category"
    if source == "erp" and metric == "Quality - Internal":
        return "ERP protocol/survey layer by show from operational quality endpoints and mapped legacy quality logic"
    if source == "yandex_metrica" and metric == "Website visits" and bu == "b2b":
        return "ym:s:visits for https://morpheus-show.ru/corporative by ym:s:lastTrafficSource + ym:s:lastAdvEngine, normalized into canonical channels"
    if source == "yandex_metrica" and metric == "Website visits" and channel_scope == "marketing_channel_names":
        return "ym:s:visits by ym:s:lastTrafficSource + ym:s:lastAdvEngine, normalized into canonical channels"
    if source == "yandex_metrica" and metric == "Website visits" and show_scope == "b2c_show_names":
        return "ym:pv:pageviews filtered by canonical show URL paths via ym:pv:URLPathFull regex"
    if source == "yandex_direct" and metric == "Marketing costs":
        return "Reports API CAMPAIGN_PERFORMANCE_REPORT; weekly sum of Cost with IncludeVAT=YES and IncludeDiscount=NO"
    if source == "manual_table":
        return "Parsed from live weekly Google Sheets via fact_metrics and import_live_weekly_manual_to_fact.py with v3 ingestion plans"
    if source == "planfact" and metric == "Account balance":
        return "Imported from PlanFact cashflow / balance reference layer"
    if source == "planfact" and metric in PLANFACT_MONTHLY_PNL_REPORT_METRICS:
        return "Imported from monthly PlanFact P&L report workbook by row label and month"
    if source == "planfact" and metric.startswith("Cost article -"):
        return "Imported from PlanFact P&L / article catalog by expense article"
    if source == "planfact" and metric in {"Costs - Salary fixed", "Costs - Other (by articles)"}:
        return "Derived from PlanFact monthly P&L / article layer"
    if source == "amocrm" and metric == "Number of leads":
        return "amoCRM v4 leads in the Corporates pipeline; count leads created during the week"
    if source == "amocrm" and metric in AMOCRM_WEEKLY_FLOW_METRICS:
        return "amoCRM v4 events; distinct leads that entered the target pipeline stage during the week"
    if source == "airtable":
        return "Operational Airtable source; aggregate project-level rows into metric scope"
    if source == "aggregate":
        return "Derived aggregate layer built on top of more atomic facts; use only as reference unless no direct source exists"
    if source == "not_available_yet":
        return "Source not implemented yet"
    return ""


def reference_doc(row: dict[str, str]) -> str:
    source = row["source_system"]
    metric = row["metric_name"]

    if source == "yandex_tickets":
        return "/Users/Peter/Documents/Morpheus Metrics/docs/yandex_tickets_fact_layer_decision.md"
    if source == "erp" and metric == "Costs - Salary variable":
        return "/Users/Peter/Documents/Morpheus Metrics/docs/erp_salary_variable_logic.md"
    if source == "erp" and metric in {
        "Number of post-show survey responses",
        "Number of show rating responses",
        "Sum of post-show ratings",
        "Number of source-attribution responses",
        "Number of question 3 responses",
        "Number of question 4 responses",
    }:
        return "/Users/Peter/Documents/Morpheus Metrics/docs/erp_survey_satisfaction_logic.md"
    if source == "erp":
        return "/Users/Peter/Documents/Morpheus Metrics/docs/erp_weekly_fact_ingestion.md"
    if source == "yandex_metrica":
        return "/Users/Peter/Documents/Morpheus Metrics/docs/yandex_metrica_weekly_fact_ingestion.md"
    if source == "yandex_direct":
        return "/Users/Peter/Documents/Morpheus Metrics/docs/external_apis/yandex_direct.md"
    if source == "manual_table":
        return "/Users/Peter/Documents/Morpheus Metrics/scripts/import_live_weekly_manual_to_fact.py"
    if source == "planfact":
        if metric in PLANFACT_MONTHLY_PNL_REPORT_METRICS:
            return "/Users/Peter/Documents/Morpheus Metrics/docs/planfact_monthly_pnl_fact_ingestion.md"
        return "/Users/Peter/Documents/Morpheus Metrics/docs/fact_layer_source_access.md"
    if source == "amocrm":
        return "/Users/Peter/Documents/Morpheus Metrics/docs/external_apis/amocrm.md"
    if source == "airtable":
        return "/Users/Peter/Documents/Morpheus Metrics/docs/fact_layer_source_access.md"
    if source == "aggregate":
        return "/Users/Peter/Documents/Morpheus Metrics/docs/fact_layer_source_access.md"
    return ""


def status_note(row: dict[str, str], role: str) -> str:
    metric = row["metric_name"]
    source = row["source_system"]
    bu = row["business_unit_scope"]
    if source == "yandex_tickets" and bu == "b2c_spb":
        return "Architectural primary source for SPB ticket sales; operational hookup still needs final cabinet rollout."
    if metric == "Marketing costs" and source == "yandex_metrica":
        return "Keep as analytical/reference slice only, not source of truth for fact-layer spend."
    if source == "erp" and metric in {"Revenue", "Number of tickets", "Number of orders"}:
        return "Reference/fallback only after Yandex Tickets ticket-sales decision."
    if role == "pending":
        return "Source planned but not implemented yet."
    if role == "needs_decision":
        return "Rule exists but source choice still needs explicit decision."
    return ""


def render() -> None:
    rows = augment_rows(load_rows())
    output_rows = []
    for row in rows:
        role = role_for(row)
        output_rows.append(
            {
                "metric_name": row["metric_name"],
                "business_unit": row["business_unit_scope"] or "general",
                "show_scope": row["show_scope"] or "general",
                "partner_scope": row["partner_scope"] or "general",
                "channel_scope": row["channel_scope"] or "general",
                "frequency": row["minimal_frequency"] or "",
                "source_role": role,
                "source_system": row["source_system"] or "",
                "where_from": where_from(row),
                "how_counted": how_counted(row),
                "reference_doc": reference_doc(row),
                "status_note": status_note(row, role),
                "source_row_ref": row["source_row_ref"],
            }
        )

    output_rows.sort(
        key=lambda r: (
            r["metric_name"],
            r["business_unit"],
            r["show_scope"],
            r["partner_scope"],
            r["channel_scope"],
            {"primary": 0, "secondary": 1, "reference": 2, "pending": 3, "needs_decision": 4}.get(r["source_role"], 9),
            r["source_system"],
        )
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "metric_name",
                "business_unit",
                "show_scope",
                "partner_scope",
                "channel_scope",
                "frequency",
                "source_role",
                "source_system",
                "where_from",
                "how_counted",
                "reference_doc",
                "status_note",
                "source_row_ref",
            ],
        )
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"wrote {len(output_rows)} rows to {OUTPUT}")


if __name__ == "__main__":
    render()
