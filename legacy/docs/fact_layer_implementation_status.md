# Fact Layer Implementation Status

Статус на `2026-05-01`.

## Целевая структура

Мы идём к такой модели:

1. одна база данных на сервере:
   - `analytics`
2. структура метрик:
   - определяется каталогом метрик и collection rules
3. факт-слой:
   - отдельная таблица наблюдений, куда weekly и monthly ingestion складывает реальные значения
4. источники:
   - все описаны в [fact_layer_source_access.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/fact_layer_source_access.md)
5. расписание:
   - weekly и monthly ingestion должны по cron обновлять факт-слой из всех нужных источников

## Что уже реализовано

### 1. Одна база на сервере

Реально используется одна PostgreSQL база:

- `analytics`
- host: `134.122.83.160`
- port: `5432`

### 2. Структура нового слоя уже создана в базе

В `analytics` уже созданы таблицы нового каталожного слоя:

- `metric_catalogue`
- `metric_scope_dictionary`
- `metric_scope_dictionary_value`
- `metric_collection_rule`
- `fact_metric_observation`
- `metric_legacy_mapping`

Текущее наполнение:

- `metric_catalogue` = `32`
- `metric_scope_dictionary` = `11`
- `metric_scope_dictionary_value` = `32`
- `metric_collection_rule` = `114`
- `fact_metric_observation` = `0`
- `metric_legacy_mapping` = `0`

### 3. Каталог и правила уже засеяны

Source files:

- [metric_catalogue_v4.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/legacy_seed/metric_catalogue_v4.csv)
- [metric_sources_v5.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/legacy_seed/metric_sources_v5.csv)
- [metric_dimension_dictionaries_v2.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/legacy_seed/metric_dimension_dictionaries_v2.csv)

Seed script:

- [seed_metric_catalog_layer.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/seed_metric_catalog_layer.py)

SQL schema file:

- [create_metric_catalog_tables.sql](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_metric_catalog_tables.sql)

### 4. Legacy reference layers уже сохранены

В базе уже есть reference-слои:

- `fact_metrics`
- `raw_weekly_metrics`
- `metric_aliases`
- `unmapped_metrics`
- `manual_metric_entries`
- `app_metric_search`
- `planfact_cashflow_entries`
- `planfact_cashflow_analytic`
- `planfact_pnl_test`
- `legacy_monthly_pnl_reference`

Это значит, что старые weekly / monthly контуры уже не потеряются и могут
использоваться для:

- backfill
- sanity checks
- legacy-to-canonical mapping

## Что ещё не реализовано

### 1. Единый ingestion в `fact_metric_observation`

Пока `fact_metric_observation` пустая.

Это значит:

- структура уже есть;
- но скрипт, который будет реально складывать туда weekly/monthly значения из всех источников, ещё не собран.

### 2. Полный source ingestion по всем системам

Пока не реализован единый pipeline, который на регулярной основе пишет в
`fact_metric_observation` из:

- ERP
- Yandex Metrica
- Yandex Direct
- amoCRM
- Airtable
- PlanFact
- legacy weekly sheets (только где это нужно как bridge/backfill)

### 3. Cron orchestration для нового факт-слоя

Сейчас в системе уже есть cron для:

- weekly legacy ingest
- hourly ERP prototype refresh

Но ещё нет нового cron-контура, который:

- weekly обновляет weekly fact metrics
- monthly обновляет monthly fact metrics
- пишет результаты именно в `fact_metric_observation`

## Честный итог

Если очень коротко:

- **одна база данных на сервере** — уже да
- **структура метрик как в каталоге** — уже да, и она уже в базе
- **единый регулярный ingestion из всех источников в новый факт-слой** — ещё нет, это следующий implementation step

То есть архитектура уже не просто “на бумаге”, но и не полностью operational.

## Следующий правильный шаг

Следующим шагом нужно сделать один новый контур:

1. ingestion script для `fact_metric_observation`
2. сначала минимально:
   - ERP
   - Yandex Metrica
   - Yandex Direct
   - legacy reference bridge
3. потом расширить:
   - amoCRM
   - Airtable
   - PlanFact
4. после этого повесить weekly/monthly cron

После этого можно будет честно сказать, что целевая структура реализована end-to-end.
