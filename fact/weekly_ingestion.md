# Weekly Fact Ingestion

Активный weekly observed contour.

## Entry Points

- runner: [scripts/run_weekly_fact_ingestion.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_weekly_fact_ingestion.py)
- registry: [scripts/registries/weekly_fact_ingestion_registry.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/registries/weekly_fact_ingestion_registry.py)

## Active Weekly Importers

- [scripts/importers/weekly/import_live_weekly_manual_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/weekly/import_live_weekly_manual_to_fact.py)
- [scripts/importers/weekly/import_erp_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/weekly/import_erp_weekly_to_fact.py)
- [scripts/importers/weekly/import_erp_salary_variable_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/weekly/import_erp_salary_variable_weekly_to_fact.py)
- [scripts/importers/weekly/import_erp_survey_satisfaction_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/weekly/import_erp_survey_satisfaction_weekly_to_fact.py)
- [scripts/importers/weekly/import_amocrm_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/weekly/import_amocrm_weekly_to_fact.py)
- [scripts/importers/weekly/import_yandex_metrica_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/weekly/import_yandex_metrica_weekly_to_fact.py)
- [scripts/importers/weekly/import_yandex_metrica_tracked_purchase_visits_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/weekly/import_yandex_metrica_tracked_purchase_visits_weekly_to_fact.py)
- [scripts/importers/weekly/import_yandex_direct_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/importers/weekly/import_yandex_direct_weekly_to_fact.py)

## Reports

Run outputs are written to [artifacts/run_reports](/Users/Peter/Documents/Morpheus%20Metrics/artifacts/run_reports).

## Manual Table Rule

`manual_table` stays a mandatory full numeric reference layer even when another source is primary for the same business metric.

## ERP Revenue Semantics

- canonical `Revenue` in ERP weekly core stays sale-date based via `tickets/by-sell`
- canonical `Revenue - Show date` is part of ERP weekly core and uses `tickets/by-seance`
- active `Revenue - Show date` filter for ERP weekly core: `DeletedAt is null` and `total > 0`
