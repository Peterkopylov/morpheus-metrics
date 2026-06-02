**Weekly Fact Ingestion**
This is the stable weekly collection infrastructure for the fact layer.

Main runner:
- [`run_weekly_fact_ingestion.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_weekly_fact_ingestion.py)

Step registry:
- [`weekly_fact_ingestion_registry.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/weekly_fact_ingestion_registry.py)

Current design:
- one source-specific importer per source or sub-source
- one weekly orchestrator on top
- one run log in Postgres
- one CSV summary report per orchestrated run

Why this structure:
- source systems are operationally different
- a failure in one source should be visible without hiding the rest
- partial reruns should be possible
- source-specific logic should stay local to each importer

Implemented weekly steps:
- `manual_weekly`
  - [`import_live_weekly_manual_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_live_weekly_manual_to_fact.py)
- `erp_weekly_core`
  - [`import_erp_weekly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_erp_weekly_to_fact.py)
- `erp_salary_variable_weekly`
  - [`import_erp_salary_variable_weekly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_erp_salary_variable_weekly_to_fact.py)
- `erp_survey_satisfaction_weekly`
  - [`import_erp_survey_satisfaction_weekly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_erp_survey_satisfaction_weekly_to_fact.py)
- `amocrm_weekly`
  - [`import_amocrm_weekly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_amocrm_weekly_to_fact.py)
- `yandex_metrica_weekly`
  - [`import_yandex_metrica_weekly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_yandex_metrica_weekly_to_fact.py)
- `yandex_metrica_tracked_purchase_visits_weekly`
  - [`import_yandex_metrica_tracked_purchase_visits_weekly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_yandex_metrica_tracked_purchase_visits_weekly_to_fact.py)
  - also loads `Performance marketing revenue` from Metrica (`favoriteGoalsConvertedRUBRevenue`, automatic attribution, `ya_direct + ya_undefined`)
- `yandex_direct_weekly`
  - [`import_yandex_direct_weekly_to_fact.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_yandex_direct_weekly_to_fact.py)
  - loads Direct marketing costs only; performance revenue is not sourced from Direct

## Manual Table Policy

Для weekly `manual_table` держим отдельное жёсткое правило:

- `manual_table` — это обязательный полный numeric reference-layer
- наличие другого `primary` source не отменяет импорт из `manual_table`
- канонический источник полноты для manual-слоя — live Google Sheets
- `fact_metrics` используем как staging / технический snapshot, а не как финальный критерий полноты
- если число есть в live sheet, но его нет в `fact_metrics`, это parser/staging gap
- не импортируем только то, что явно размечено как calculated / deferred-to-calculated
- weekly importer manual-слоя сначала пытается взять значение из `fact_metrics`, но при `missing_staging_row` или кривом `value_type` умеет ходить напрямую в live Google Sheets через service account и брать значение из weekly-колонки по стабильному `row_number`
- если для недели уже есть подготовленный reconciled snapshot CSV, importer тоже может использовать его как явный debug/reference artifact, но это больше не обязательный шаг для каждой новой недели
- live fallback snapshot и сверку при необходимости собираем через:
  - [`reconcile_manual_table_live_transfer_status.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/reconcile_manual_table_live_transfer_status.py)
  - ожидаемый weekly artifact:
    - [`manual_table_live_transfer_status_2026_04_20_reconciled.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/manual_table_live_transfer_status_2026_04_20_reconciled.csv)

Current step order:
1. `manual_weekly`
2. `erp_weekly_core`
3. `erp_salary_variable_weekly`
4. `erp_survey_satisfaction_weekly`
5. `amocrm_weekly`
6. `yandex_metrica_weekly`
7. `yandex_direct_weekly`

Current operational nuance:
- `amoCRM` is now live with local [`.env.amocrm`](/Users/Peter/Documents/Morpheus%20Metrics/.env.amocrm); if the token is later removed or replaced with `replace_me`, the step falls back to `pending` instead of breaking the pipeline
- weekly ticket sales now come from `ERP /tickets/by-sell`, not from `Yandex Tickets`
- in ERP ticket rows `status = 0` means cancellation, `status != 0` means active sale
- weekly ERP sales importer keeps only rows with non-zero `status` and positive `total`

Run logging:
- table `fact_ingestion_runs`
- table `fact_ingestion_run_steps`

Current run status semantics:
- `success`
- `partial`
- `failed`
- step-level `pending`

Example run:

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/run_weekly_fact_ingestion.py \
  --database-url "$DATABASE_URL" \
  --delete-existing
```

Example for a specific week:

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/run_weekly_fact_ingestion.py \
  --database-url "$DATABASE_URL" \
  --week-start 2026-04-20 \
  --delete-existing
```

Example for any subset of steps:

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/run_weekly_fact_ingestion.py \
  --database-url "$DATABASE_URL" \
  --week-start 2026-04-20 \
  --steps erp_weekly_core,yandex_direct_weekly \
  --delete-existing
```

Important current limitation:
- `partial` can still mean a healthy run if some source steps are blocked by credentials rather than code
- use the step log to distinguish real failures from credential-gated pending steps
