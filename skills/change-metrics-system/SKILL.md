---
name: change-metrics-system
description: Use when the user asks to change the active metrics system itself in broad language, including phrases like "вносим изменения", "меняем систему", "добавляем метрику", "меняем источник", "переносим в calculated", "чиним warehouse-логику", "обновляем контур", "меняем дэшбордную логику", or any request that affects canonical files, ingestion scripts, calculated logic, serving semantics, or database facts.
---

# Change Metrics System

Use this skill when the request is about changing the active warehouse system, not just reading it.

This skill is intentionally broad. It should trigger not only on explicit phrases like:

- `вносим изменения в систему`
- `меняем систему`
- `переделаем`
- `делаем не так`
- `добавляем метрику`
- `меняем метрику`
- `меняем источник`
- `переносим логику в calculated`
- `меняем fact layer`
- `обновляем ingestion`
- `чиним warehouse-логику`
- `меняем дэшбордную логику`
- `делаем backfill`
- `перезаливаем историю`

but also on any request where the real effect is a system change across warehouse artifacts.

## Main Idea

The phrase "change the system" should not mean "edit everything automatically".

It means:

1. always inspect the full active impact surface
2. update the required active artifacts
3. stop and discuss risky changes before applying them

## Default Mode

Default mode is `safe_change`.

In `safe_change`, you may:

- update canonical files
- update runtime scripts and registries
- update documentation and serving metadata
- assess calculated and dashboard impact

In `safe_change`, you do **not** modify existing database facts unless the user explicitly asks for a data repair or confirms it after escalation.

## Required Checks For Every System Change

Always inspect these areas and decide whether they must change:

1. [catalog/metric_catalogue_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/catalog/metric_catalogue_canonical.csv)
2. [fact/source_of_truth.csv](/Users/Peter/Documents/Morpheus%20Metrics/fact/source_of_truth.csv)
3. [fact/source_access.md](/Users/Peter/Documents/Morpheus%20Metrics/fact/source_access.md) when source access or operational source assumptions change
4. the relevant runtime code under [scripts/](/Users/Peter/Documents/Morpheus%20Metrics/scripts)
5. [calculated/formula_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/formula_registry.csv) and [calculated/dependency_matrix.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/dependency_matrix.csv)
6. [serving/dashboard_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboard_registry.csv) and the serving layer when dashboards or views may be affected
7. [docs/project_memory.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/project_memory.md) when the change introduces a new enduring rule

## What Must Be Updated If Touched

### Canonical

Update canonical files when the request changes:

- metric identity
- metric scope
- source of truth
- counting logic
- monthly P&L structure
- calculated formula ownership

### Runtime

Update scripts and registries when the request changes:

- importer behavior
- source-specific mapping
- orchestration steps
- calculated execution logic
- serving rebuild logic

### Calculated Review

Always check whether the request should affect the calculated layer.

Ask:

- is this reusable business logic?
- should this formula exist outside one dashboard?
- does this create or remove a dependency?
- should this move from `fact` to `calculated`, or stay in `fact`?

If yes, update:

- [calculated/formula_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/formula_registry.csv)
- [calculated/dependency_matrix.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/dependency_matrix.csv)
- related runtime code if needed

### Dashboard Review

Always check whether the change can affect dashboards or serving views.

Ask:

- does an existing dashboard read this metric?
- does a serving view depend on this source or formula?
- does the meaning of a published number change?

If yes, update or at least note impact in:

- [serving/dashboard_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboard_registry.csv)
- relevant files under [scripts/serving/](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving)
- relevant docs under [serving/dashboards/](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboards)

## Risk Gates: Stop And Discuss First

Do not silently apply these changes. Pause and surface them to the user first.

### Semantic changes

- changing the meaning of an existing metric
- changing source of truth for an existing metric
- moving logic between `fact` and `calculated`
- changing dashboard semantics for published metrics

### Data changes

- modifying existing facts in the database
- backfilling historical periods
- reimporting historical ranges
- rewriting or deleting previously loaded production data

### Structural changes

- deleting canonical rows
- deprecating existing metrics
- moving active logic into `legacy`
- reactivating legacy logic back into active paths

## Hard Gate: Explicit Approval Required

The following require explicit user confirmation before execution:

- `UPDATE` / `DELETE` against production data
- any backfill or repair affecting existing periods
- recalculation of broad historical ranges
- changes that intentionally alter already-published past numbers

## Classification Step

At the start of the workflow, classify the request into one or more buckets:

- `new_observed_metric`
- `observed_source_logic_change`
- `calculated_logic_change`
- `serving_only_change`
- `dashboard_semantic_change`
- `data_repair_or_backfill`
- `mixed_change`

State the classification briefly in your working notes or user update.

## Execution Order

1. Classify the change.
2. Inspect active canonical files first.
3. Inspect runtime code impact.
4. Inspect calculated impact.
5. Inspect dashboard/serving impact.
6. Decide whether the task remains `safe_change` or requires escalation.
7. If safe, implement the file/code changes.
8. If risky, stop and ask for confirmation on the risky part only.

## Default Assumption

When the user says broad phrases like "вносим изменения" without mentioning backfill or DB rewrite, assume:

- canonical files may change
- scripts may change
- calculated review is required
- dashboard review is required
- database facts are **not** changed yet

## Final Response Checklist

In the final response, summarize:

- whether canonical files changed
- whether scripts changed
- whether calculated layer was checked and changed or not
- whether dashboard impact was checked and changed or not
- whether any DB fact changes were made
- whether any risky changes were intentionally deferred for discussion
