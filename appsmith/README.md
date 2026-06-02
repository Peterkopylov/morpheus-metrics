# Appsmith Metric Admin

Минимальный внутренний интерфейс поверх `analytics` для двух задач:

1. ручной ввод метрик
2. поиск метрик по параметрам

База, на которую это рассчитано:

- PostgreSQL `analytics`
- таблица `manual_metric_entries`
- view `app_metric_search`

Они создаются скриптом:

- [`scripts/setup_appsmith_metric_admin.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/setup_appsmith_metric_admin.py)

Запуск:

```bash
python3 scripts/setup_appsmith_metric_admin.py \
  --database-url "postgresql://admin:strongpassword@134.122.83.160:5432/analytics"
```

## Что получится в базе

### `manual_metric_entries`

Таблица для ручного ввода curated-метрик.

Поля:

- `unit`
- `aggregation_level`
- `period_start`
- `period_end`
- `period_label`
- `metric_group`
- `metric_name`
- `metric_key`
- `value`
- `value_raw`
- `value_type`
- `notes`
- `created_by`
- `is_active`
- `created_at`
- `updated_at`

### `app_metric_search`

Единый read-view для поиска.

Включает:

- строки из `fact_metrics`
- строки из `manual_metric_entries`

Ключевые поля:

- `record_source`
- `source_table`
- `record_id`
- `unit`
- `aggregation_level`
- `period_start`
- `period_end`
- `period_label`
- `metric_group`
- `metric_name`
- `metric_key`
- `value`
- `value_raw`
- `value_type`
- `notes`
- `created_by`
- `recorded_at`
- `search_blob`
- `source_sheet_url`

## Структура Appsmith

### Page 1: `Metric Entry`

Поля формы:

- `UnitSelect`
- `AggregationSelect`
- `PeriodStartPicker`
- `PeriodEndPicker`
- `PeriodLabelInput`
- `MetricGroupInput`
- `MetricNameInput`
- `MetricKeyInput`
- `ValueInput`
- `ValueRawInput`
- `ValueTypeSelect`
- `CreatedByInput`
- `NotesInput`
- `SaveButton`

### Page 2: `Metric Search`

Фильтры:

- `SourceSelect`
- `UnitFilter`
- `AggregationFilter`
- `MetricGroupFilter`
- `MetricNameFilter`
- `PeriodStartFilter`
- `PeriodEndFilter`
- `SearchTextInput`

Основной вывод:

- `MetricsTable`

## Data source в Appsmith

Создай PostgreSQL datasource на `analytics`.

Пример:

- Host: `134.122.83.160`
- Port: `5432`
- Database: `analytics`
- Username: `admin`
- Password: `strongpassword`

Если Appsmith будет жить на том же сервере, лучше подключать к Postgres по внутреннему хосту, а не снаружи.

## Queries

SQL-запросы лежат в:

- [`appsmith/queries.md`](/Users/Peter/Documents/Morpheus%20Metrics/appsmith/queries.md)

Рекомендуемый минимальный набор:

- `InsertManualMetric`
- `SearchMetrics`
- `LoadUnits`
- `LoadMetricGroups`
- `LoadMetricNames`

## Базовая логика

### Сохранение

Форма пишет только в `manual_metric_entries`.

Это важно:

- руками не трогаем `fact_metrics`
- сырые и автоматически загруженные метрики остаются immutable
- ручной ввод живёт отдельно и прозрачно

### Поиск

Поиск идёт через `app_metric_search`.

Плюс:

- одно место для чтения
- можно искать и по автоматическим, и по ручным строкам
- можно быстро фильтровать по `unit`, периоду и названию метрики

## Что можно добавить следующим шагом

- Edit / update для `manual_metric_entries`
- soft delete (`is_active = false`)
- отдельную страницу для редактирования `metric_aliases`
- отдельную страницу для `planfact_article_mappings`
- ссылки на `weekly_metrics_trace` / Google Sheet origin
