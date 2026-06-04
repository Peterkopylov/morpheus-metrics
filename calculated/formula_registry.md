# Calculated Formula Registry

Human-readable companion to the canonical calculated files.

## Canonical Files

- [formula_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/formula_registry.csv)
- [dependency_matrix.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/dependency_matrix.csv)
- [recalc_policy.md](/Users/Peter/Documents/Morpheus%20Metrics/calculated/recalc_policy.md)

## Runtime

- [scripts/registries/calculated_metric_registry.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/registries/calculated_metric_registry.py)
- [scripts/run_calculated_metrics.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_calculated_metrics.py)
- [sql/create_calculated_metric_tables.sql](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_calculated_metric_tables.sql)

## Main Rule

Observed values and calculated values stay separate by default.

Accepted exception:

- monthly financial rollups may be materialized back into `fact` where the project explicitly treats that contour as operationally correct.
