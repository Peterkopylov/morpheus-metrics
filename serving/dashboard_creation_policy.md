# Dashboard Creation Policy

Новый dashboard не должен становиться местом, где warehouse-логика живёт только в BI.

## Required Checks

Перед созданием или большим изменением dashboard:

1. определить аудиторию и access scope
2. проверить, reusable ли логика
3. решить, это `view`, `calculated`, или переиспользование существующего слоя
4. обновить registry

## Reuse Search

Искать сначала в:

- `sql/`
- `scripts/serving/`
- `serving/dashboards/`
- [serving/dashboard_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboard_registry.csv)

## Registry Rule

Каждый новый dashboard или существенное изменение должны обновлять:

- [serving/dashboard_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboard_registry.csv)

## Modeling Rule

- `calculated` для reusable KPI и устойчивой metric semantics
- `view` для dashboard-specific shaping, joins, comparison columns, helper flags
