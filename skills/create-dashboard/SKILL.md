---
name: create-dashboard
description: Use when the user asks to create, redesign, extend, or operationalize a dashboard in this metrics warehouse. This skill gathers dashboard access requirements, forces an explicit decision about whether dashboard logic belongs in the calculated layer or a dashboard view, searches the repo for reusable views and dashboard scripts, and updates the dashboard registry after the work.
---

# Create Dashboard

Use this skill for new dashboards and substantial dashboard changes. The goal is to avoid one-off Metabase work, reuse existing serving layers when possible, and leave a durable project record of what was built and why.

## Required Questions

Before building or changing a dashboard, ask the user the following if the answer is not already explicit:

- Who should have access to this dashboard.
- Whether access is broad or restricted:
  `founder-only`, `ops`, `finance`, `marketing`, `sales`, `all company`, or another named audience.
- Whether the metrics or business logic introduced by the dashboard should stay dashboard-specific or be promoted into the warehouse:
  `view only`, `calculated layer`, or `undecided, investigate first`.

If the user has not decided on `view` vs `calculated`, do not guess immediately. First inspect whether the requested KPI already exists in `fact_metric_observation`, `calculated_metric_value`, or an existing serving view.

## Decision Rule: `calculated` vs `view`

Use `calculated layer` when the logic defines a reusable KPI or business metric that should exist independently of one dashboard.

Use `view` when the logic is mainly serving or presentation logic for one dashboard:

- joins for dashboard shaping
- latest vs previous / YoY comparison columns
- labels, sort order, wide-table reshaping
- dashboard-specific filters or helper flags

Use the stronger warehouse artifact when one of these is true:

- the KPI is likely to be reused in more than one dashboard
- the KPI needs formula ownership and debug trace
- the KPI should participate in period-aware recalculation
- the same logic would otherwise be duplicated across multiple cards or dashboards

If still ambiguous, prefer this escalation order:

1. Reuse existing `view` if it already serves the need.
2. Add a new dashboard view if the logic is dashboard-specific.
3. Add to `calculated layer` if the logic is warehouse-semantic and reusable.

For this repo, read [`serving/dashboard_creation_policy.md`](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboard_creation_policy.md) when you need the fuller policy.

## Reuse Search Workflow

Before proposing a new view or script, search for reusable assets in this repo.

Check at minimum:

- `sql/` for serving views
- `scripts/serving/create_metabase_*dashboard*.py` for existing dashboard builders
- `scripts/serving/rebuild_*view*.py` for view assembly scripts
- `serving/dashboards/` for dashboard operational notes
- `serving/dashboard_registry.csv` for already-registered dashboards

Useful search patterns:

- `rg -n "CREATE VIEW|MATERIALIZED VIEW" sql scripts`
- `rg -n "create_dashboard|put_dashboard_cards|update_existing_dashboard_id" scripts`
- `rg -n "dashboard|Metabase" docs README.md`
- `rg -n "weekly_fact_metrics_dashboard_base|latest_comparison|yoy" scripts sql`

When you find a reusable asset, state clearly:

- what it is
- whether it is directly reusable or only a pattern
- what gap remains

## Registry Update Is Required

Every dashboard creation or substantial dashboard update must update the project dashboard registry.

Use these project files:

- registry rules: [`serving/dashboard_creation_policy.md`](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboard_creation_policy.md)
- registry data: [`serving/dashboard_registry.csv`](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboard_registry.csv)

Add or update a row with:

- dashboard key and name
- tool and dashboard id if known
- status
- intended audience and access scope
- owner if known
- serving layer and reusable views/scripts involved
- whether new metrics were added to `calculated` or only to a `view`
- notes explaining important modeling choices

If the dashboard is only planned and not yet built, still add a row with status `planned`.

## Build Workflow

1. Clarify dashboard purpose and audience.
2. Ask the required access and modeling questions.
3. Search for reusable warehouse views, existing dashboard scripts, and similar dashboards.
4. Decide whether the request needs:
   - no new warehouse object
   - a new or updated serving `view`
   - a new or updated `calculated` metric
5. Implement the needed SQL, scripts, or Metabase changes.
6. Update the dashboard registry.
7. In the final response, summarize:
   - access assumption or confirmed audience
   - `calculated` vs `view` decision and why
   - reuse findings
   - registry update location

## Project Notes

This repository already contains reusable dashboard infrastructure. Especially relevant examples:

- `scripts/serving/rebuild_weekly_fact_metrics_yoy_views.py`
- `scripts/serving/create_metabase_weekly_metrics_dashboard.py`
- `scripts/serving/create_metabase_weekly_latest_comparison_dashboard.py`
- `scripts/serving/create_metabase_planfact_dashboard.py`
- `docs/external_apis/metabase.md`

Treat Metabase as a publishing layer, not as source of truth for metric semantics.

## References

Read [references/workflow-checklist.md](/Users/Peter/Documents/Morpheus%20Metrics/skills/create-dashboard/references/workflow-checklist.md) when you need a compact execution checklist during implementation.
