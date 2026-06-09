# Morpheus Metrics

Минимализированный рабочий репозиторий метрик-warehouse. Активный слой теперь намеренно отделён от `legacy/` и от рабочих артефактов запусков.

## Читать сначала

- [docs/system_overview.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/system_overview.md)
- [docs/project_memory.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/project_memory.md)
- [catalog/metric_catalogue_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/catalog/metric_catalogue_canonical.csv)
- [fact/source_of_truth.csv](/Users/Peter/Documents/Morpheus%20Metrics/fact/source_of_truth.csv)
- [calculated/formula_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/formula_registry.csv)

## Active Structure

- `catalog/`
  Canonical metric identity and P&L structure.
- `fact/`
  Observed source-of-truth rules, access map, and ingestion contour docs.
- `calculated/`
  Derived KPI definitions, dependencies, and recalc policy.
- `serving/`
  Dashboard registry and serving-layer policy.
- `scripts/`
  Active runtime code: orchestrators, registries, importers, serving builders, and utilities.
- `sql/`
  Runtime SQL objects for catalog, fact, calculated, and serving layers.
- `skills/`
  Required change workflows for system and dashboard updates.

## Non-Active Areas

- `legacy/`
  Archive only. Do not read from it for routine modeling or implementation unless an active file explicitly sends you there.
- `artifacts/`
  Run outputs, audits, snapshots, and exports. Useful for evidence, not for source-of-truth modeling.

## Guardrail

Default rule:

1. Read active files first.
2. Change active files first.
3. Enter `legacy/` only for migration, reconciliation, or historical reference.

If a task changes the metrics system, use [skills/change-metrics-system/SKILL.md](/Users/Peter/Documents/Morpheus%20Metrics/skills/change-metrics-system/SKILL.md).
