# System Overview

## Goal

Этот репозиторий хранит минимальный active контур metrics warehouse:

- какие метрики существуют
- откуда приходят observed values
- какие KPI рассчитываются
- какие dashboards и serving views публикуют данные

## Layers

### `catalog/`

- [metric_catalogue_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/catalog/metric_catalogue_canonical.csv)
- [pnl_structure_mapping_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/catalog/pnl_structure_mapping_canonical.csv)
- [legacy_metric_mapping.csv](/Users/Peter/Documents/Morpheus%20Metrics/catalog/legacy_metric_mapping.csv)

### `fact/`

- [source_of_truth.csv](/Users/Peter/Documents/Morpheus%20Metrics/fact/source_of_truth.csv)
- [source_access.md](/Users/Peter/Documents/Morpheus%20Metrics/fact/source_access.md)
- [weekly_ingestion.md](/Users/Peter/Documents/Morpheus%20Metrics/fact/weekly_ingestion.md)
- [monthly_kpi_ingestion.md](/Users/Peter/Documents/Morpheus%20Metrics/fact/monthly_kpi_ingestion.md)
- [monthly_pnl_ingestion.md](/Users/Peter/Documents/Morpheus%20Metrics/fact/monthly_pnl_ingestion.md)

Current monthly P&L routine is intentionally narrow:

- recurring: PlanFact Excel import + monthly rollup rebuild
- historical monthly backfills: `legacy/` only

### `calculated/`

- [formula_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/formula_registry.csv)
- [dependency_matrix.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/dependency_matrix.csv)
- [recalc_policy.md](/Users/Peter/Documents/Morpheus%20Metrics/calculated/recalc_policy.md)

### `serving/`

- [dashboard_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboard_registry.csv)
- [dashboard_creation_policy.md](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboard_creation_policy.md)

### `scripts/`

Active executable layer:

- `run_*` orchestrators
- `registries/` contour definitions
- `importers/` source-specific loaders
- `serving/` dashboard/view builders
- `tools/` utilities that support active canonical system files

## Reading Order

1. `docs/system_overview.md`
2. `catalog/metric_catalogue_canonical.csv`
3. `fact/source_of_truth.csv`
4. `calculated/formula_registry.csv`
5. `serving/dashboard_registry.csv`

## Guardrail

`legacy/` and `artifacts/` are intentionally out of the main path:

- `legacy/` is for archive, transition, and one-off history
- `artifacts/` is for outputs and evidence

Routine implementation should start from active files only.
