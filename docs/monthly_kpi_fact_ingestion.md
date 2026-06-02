**Monthly KPI Fact Ingestion**
This is the target contour for the monthly mirror of the weekly KPI pipeline.

Goal:
- same source families as weekly ingestion
- same canonical KPI logic
- `period_granularity = 'month'`
- expected volume should be comparable to the weekly contour, not to the monthly P&L contour

Source families expected here:
- `erp`
- `erp_salary_variable`
- `erp_survey_satisfaction`
- `amocrm`
- `yandex_metrica`
- `yandex_metrica_tracked_purchase_visits`
  - also loads `Performance marketing revenue` from Metrica (`favoriteGoalsConvertedRUBRevenue`, automatic attribution, `ya_direct + ya_undefined`)
- `yandex_direct`
  - loads Direct marketing costs only; performance revenue is not sourced from Direct

Current runner:
- [`run_monthly_kpi_fact_ingestion.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_monthly_kpi_fact_ingestion.py)

Current registry:
- [`monthly_kpi_fact_ingestion_registry.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/monthly_kpi_fact_ingestion_registry.py)

Currently implemented steps:
- `erp_monthly_core`
  - [`import_erp_monthly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_erp_monthly_to_fact.py)
- `erp_salary_variable_monthly`
  - [`import_erp_salary_variable_monthly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_erp_salary_variable_monthly_to_fact.py)
- `erp_survey_satisfaction_monthly`
  - [`import_erp_survey_satisfaction_monthly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_erp_survey_satisfaction_monthly_to_fact.py)
- `amocrm_monthly`
  - [`import_amocrm_monthly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_amocrm_monthly_to_fact.py)
- `yandex_metrica_monthly`
  - [`import_yandex_metrica_monthly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_yandex_metrica_monthly_to_fact.py)
- `yandex_metrica_tracked_purchase_visits_monthly`
  - [`import_yandex_metrica_tracked_purchase_visits_monthly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_yandex_metrica_tracked_purchase_visits_monthly_to_fact.py)
  - also loads `Performance marketing revenue` from Metrica (`favoriteGoalsConvertedRUBRevenue`, automatic attribution, `ya_direct + ya_undefined`)
- `yandex_direct_monthly`
  - [`import_yandex_direct_monthly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_yandex_direct_monthly_to_fact.py)
  - loads Direct marketing costs only; performance revenue is not sourced from Direct

Important split:
- monthly `P&L / historical` ingestion stays active for PlanFact `.xlsx` imports
- monthly `KPI` ingestion should be implemented as a separate runner/registry, not by extending the P&L runner
- weekly `manual_table` is intentionally excluded from the first monthly KPI contour:
  - it is weekly-only and should not be naively aggregated into monthly facts

Current status:
- architecture decision confirmed
- first operational monthly KPI contour is implemented for non-manual raw sources

Example run:

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/run_monthly_kpi_fact_ingestion.py \
  --database-url "$DATABASE_URL" \
  --month-start 2026-01-01 \
  --delete-existing
```
