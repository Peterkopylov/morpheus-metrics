# Calculated Layer Canonical Files

Это compact canonical description layer для `calculated` системы. Как и в `fact`-слое, operational контур отделён от runtime tables.

Main files:

- [`calculated_metric_formula_registry_canonical.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/calculated_metric_formula_registry_canonical.csv)
  - что считаем, на каком grain, в каком scope и по какой формуле
- [`calculated_metric_dependency_matrix.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/calculated_metric_dependency_matrix.csv)
  - от каких observed metrics зависит каждая calculated metric
- [`calculated_metric_formula_registry.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/calculated_metric_formula_registry.md)
  - human-readable operational registry
- [`partner_commission_rate_registry.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/partner_commission_rate_registry.csv)
  - metadata-layer with approved partner commission rates for weekly calculated metrics
- [`calculated_layer_recalc_policy.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/calculated_layer_recalc_policy.md)
  - когда и какие calculated metrics пересчитываются

Design split:

- `calculated_metric_formula_registry_canonical.csv`
  - только formula definitions
- `calculated_metric_dependency_matrix.csv`
  - только dependency / invalidation matrix
- `calculated_metric_formula_registry.md`
  - operational explanation and business meaning
- `partner_commission_rate_registry.csv`
  - auxiliary rule registry for rate-based formulas
- `calculated_layer_recalc_policy.md`
  - orchestration and recalculation rules

Runtime files:

- [`create_calculated_metric_tables.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_calculated_metric_tables.sql)
- [`create_calculated_metric_latest_run_view.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_calculated_metric_latest_run_view.sql)
- [`calculated_metric_registry.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/calculated_metric_registry.py)
- [`run_calculated_metrics.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_calculated_metrics.py)

Policy:

- canonical CSV is the source of truth for the MVP formula registry
- PostgreSQL `calculated_metric_definition` is a synced runtime mirror
- `pending` formulas may exist in canonical files before their automatic computation is implemented
- period-aware recalculation is mandatory: weekly updates recalc weekly formulas only, monthly updates recalc monthly formulas only
