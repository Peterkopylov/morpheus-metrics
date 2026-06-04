# Monthly KPI Fact Ingestion

Monthly mirror of the weekly KPI contour.

## Entry Points

- runner: [scripts/run_monthly_kpi_fact_ingestion.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_monthly_kpi_fact_ingestion.py)
- registry: [scripts/registries/monthly_kpi_fact_ingestion_registry.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/registries/monthly_kpi_fact_ingestion_registry.py)

## Active Monthly KPI Importers

- [scripts/importers/monthly_kpi/import_erp_monthly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/monthly_kpi/import_erp_monthly_to_fact.py)
- [scripts/importers/monthly_kpi/import_erp_salary_variable_monthly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/monthly_kpi/import_erp_salary_variable_monthly_to_fact.py)
- [scripts/importers/monthly_kpi/import_erp_survey_satisfaction_monthly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/monthly_kpi/import_erp_survey_satisfaction_monthly_to_fact.py)
- [scripts/importers/monthly_kpi/import_amocrm_monthly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/monthly_kpi/import_amocrm_monthly_to_fact.py)
- [scripts/importers/monthly_kpi/import_yandex_metrica_monthly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/monthly_kpi/import_yandex_metrica_monthly_to_fact.py)
- [scripts/importers/monthly_kpi/import_yandex_metrica_tracked_purchase_visits_monthly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/monthly_kpi/import_yandex_metrica_tracked_purchase_visits_monthly_to_fact.py)
- [scripts/importers/monthly_kpi/import_yandex_direct_monthly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/monthly_kpi/import_yandex_direct_monthly_to_fact.py)

## Runtime Rules

- for ERP monthly core, `Number of shows` means non-cancelled shows only
- ERP monthly `Number of shows cancelled` must carry cancelled shows separately
- ERP monthly `Number of show visitors` must aggregate `guests` only across non-cancelled shows so that visitor-per-show ratios stay semantically aligned with weekly ERP metrics
- ERP monthly `Costs - Salary variable` general rows must match weekly semantics: `salary_total + full bonus_total`, while keeping allocated and unallocated bonus parts visible in payload
- canonical `Revenue` in ERP monthly KPI stays sale-date based via `tickets/by-sell`
- canonical `Revenue - Show date` is a separate monthly ERP metric for performed-show revenue via `tickets/by-seance`
- active `Revenue - Show date` filter for ERP monthly core: `DeletedAt is null` and `total > 0`

## Reports

Run outputs are written to [artifacts/run_reports](/Users/Peter/Documents/Morpheus%20Metrics/artifacts/run_reports).
