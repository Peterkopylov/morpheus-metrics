# Fact Ingestion Technical Monitor

Technical dashboard for `ops` to inspect ingestion reliability by actual ingestion date.

## Purpose

- top filter: ingestion date range
- rows: ingestion date
- first dimension: `weekly` / `monthly`
- second dimension: `manual` / `automated`
- source columns: `amo`, `erp`, `yandex`
- values: loaded facts as a share of the typical successful volume for the attempted steps in that source group

## Modeling choice

- layer: `view only`
- canonical warehouse objects used:
  - `fact_ingestion_runs`
  - `fact_ingestion_run_steps`
  - `fact_metric_observation`
- serving view:
  - `fact_ingestion_technical_monitor`

## How the percentage is computed

For each source column, the dashboard:

1. takes the latest attempt of each relevant step for the same ingestion day, cadence, execution mode, and source group
2. counts how many fact rows were actually loaded by those steps
3. estimates the expected volume as the median successful row count for each attempted step, then sums those medians
4. shows `loaded / expected`

This makes the monitor sensitive both to hard failures (`0%`) and to anomalously low fact loads.

## Source grouping

- `amo`: `amocrm`
- `erp`: `erp`
- `yandex`: `yandex_metrica`, `yandex_direct`, `yandex_tickets`

## Build assets

- SQL: [create_fact_ingestion_technical_monitor_view.sql](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_fact_ingestion_technical_monitor_view.sql)
- rebuild script: [rebuild_fact_ingestion_technical_monitor_view.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/rebuild_fact_ingestion_technical_monitor_view.py)
- Metabase builder: [create_metabase_fact_ingestion_technical_dashboard.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/create_metabase_fact_ingestion_technical_dashboard.py)
