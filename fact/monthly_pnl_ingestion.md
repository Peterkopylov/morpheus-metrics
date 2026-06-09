# Monthly P&L Fact Ingestion

Active monthly financial contour for the current recurring PlanFact Excel import plus accepted monthly rollup materialization back into `fact`.

## Entry Points

- runner: [scripts/run_monthly_fact_ingestion.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_monthly_fact_ingestion.py)
- alias runner: [scripts/run_monthly_pnl_fact_ingestion.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_monthly_pnl_fact_ingestion.py)
- registry: [scripts/registries/monthly_fact_ingestion_registry.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/registries/monthly_fact_ingestion_registry.py)

## Active Monthly P&L Importers

- [scripts/importers/monthly_pnl/import_planfact_monthly_pnl_report_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/monthly_pnl/import_planfact_monthly_pnl_report_to_fact.py)
- [scripts/importers/monthly_pnl/import_monthly_pnl_calculated_rollups_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/monthly_pnl/import_monthly_pnl_calculated_rollups_to_fact.py)

## Runtime Rules

For recurring monthly P&L data, the runtime layer must follow these rules:

- monthly PlanFact import writes observed rows only at the business-unit level
- materialized rollup / formula metrics are also calculated only at the business-unit level
- runtime `Revenue` must include both the unscoped BU revenue row and any valid show-scoped revenue rows that are part of the same BU revenue model
- specifically, certificate revenue stored as `Revenue` with `show_name = Certificate` is part of runtime revenue and must not be dropped from totals
- runtime serving collapses technical `show_name` splits back into ordinary BU-level `Revenue` and `Operating profit`; raw fact rows may keep the original `show_name`, but runtime monthly P&L reads these metrics without show scope
- runtime `total` is always built as the sum of business units of the same semantic layer
- `general` is not equal to `total`, but it must be included in the runtime `total` sum as the bucket of unallocated values
- if the monthly `general` workbook is empty or not exported for a specific month, the import may run without `general`; in that case runtime `total` is still derived from the business units that do have observed rows, and `general` contributes zero for that month
- observed `business_unit = total` may be stored for reference / reconciliation, but it must not be used as the primary runtime `total`

## Historical Foundation

Historical monthly economics loaders and manual dividends backfill are no longer part of the recurring monthly process.

They live in:

- [legacy/scripts/monthly_pnl_history/import_historical_monthly_economics_sheet_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/legacy/scripts/monthly_pnl_history/import_historical_monthly_economics_sheet_to_fact.py)
- [legacy/scripts/monthly_pnl_history/import_historical_monthly_economics_prototype_extension_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/legacy/scripts/monthly_pnl_history/import_historical_monthly_economics_prototype_extension_to_fact.py)
- [legacy/scripts/monthly_pnl_history/import_manual_dividends_total_history_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/legacy/scripts/monthly_pnl_history/import_manual_dividends_total_history_to_fact.py)

Use them only for history repair or one-time re-backfill.

## Serving Rebuild

After monthly P&L refresh, the wrapper may rebuild:

- [scripts/serving/rebuild_monthly_pnl_history_views.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/rebuild_monthly_pnl_history_views.py)

## Reports

Run outputs are written to [artifacts/run_reports](/Users/Peter/Documents/Morpheus%20Metrics/artifacts/run_reports).
