**Monthly Fact Ingestion**
This document describes the currently implemented monthly `P&L / historical` ingestion contour.

Important:
- this is not the monthly mirror of the weekly KPI contour
- this runner is closer to a monthly P&L import + historical backfill pipeline
- keep it active because monthly PlanFact `.xlsx` P&L imports are expected to continue
- build a separate `monthly KPI` contour for the "same logic as weekly, different period" requirement

Main runner:
- [`run_monthly_fact_ingestion.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_monthly_fact_ingestion.py)
- compatibility alias with clearer naming:
  - [`run_monthly_pnl_fact_ingestion.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_monthly_pnl_fact_ingestion.py)

Step registry:
- [`monthly_fact_ingestion_registry.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/monthly_fact_ingestion_registry.py)

Current design:
- one source-specific importer per monthly source
- one monthly orchestrator on top
- one shared run log in Postgres
- one CSV summary report per orchestrated run

This contour is intended for:
- monthly PlanFact observed P&L
- historical monthly economics sources
- narrow monthly backfills

This contour is not intended to replace:
- weekly-style operational KPI ingestion from `manual_table`, `erp`, `amocrm`, `yandex_metrica`, `yandex_direct`

Implemented monthly steps:
- `historical_monthly_economics`
  - [`import_historical_monthly_economics_sheet_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_historical_monthly_economics_sheet_to_fact.py)
- `historical_monthly_economics_prototype_extension`
  - [`import_historical_monthly_economics_prototype_extension_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_historical_monthly_economics_prototype_extension_to_fact.py)
- `planfact_monthly_pnl`
  - [`import_planfact_monthly_pnl_report_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_planfact_monthly_pnl_report_to_fact.py)
- `manual_dividends_total_history`
  - [`import_manual_dividends_total_history_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_manual_dividends_total_history_to_fact.py)
- `historical_pnl_rollup_backfill`
  - [`import_historical_pnl_rollup_backfill_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_historical_pnl_rollup_backfill_to_fact.py)

Run logging:
- table `fact_ingestion_runs`
- table `fact_ingestion_run_steps`

Current run status semantics:
- `success`
- `partial`
- `failed`
- step-level `pending`

Month-range behavior:
- runner accepts `--month-start` and optional `--month-end`
- monthly importers now support bounded reimport for a single month or a month range
- `--month-start` and `--month-end` must both be first day of month values

Example run for one month:

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/run_monthly_fact_ingestion.py \
  --database-url "$DATABASE_URL" \
  --month-start 2026-05-01 \
  --delete-existing
```

Example for a range:

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/run_monthly_fact_ingestion.py \
  --database-url "$DATABASE_URL" \
  --month-start 2026-01-01 \
  --month-end 2026-03-01 \
  --delete-existing
```

Example for a subset of steps:

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/run_monthly_fact_ingestion.py \
  --database-url "$DATABASE_URL" \
  --month-start 2026-05-01 \
  --steps planfact_monthly_pnl,manual_dividends_total_history \
  --delete-existing
```

Operational note:
- unified serving views for monthly P&L are rebuilt by
  [`run_fact_and_calculation_refresh.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_fact_and_calculation_refresh.py)
  after a monthly fact refresh, via
  [`rebuild_monthly_pnl_history_views.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/rebuild_monthly_pnl_history_views.py)
