# Morpheus Metrics

Аналитический проект для DigitalOcean, который собирает в одном PostgreSQL:

- weekly metrics из Google Sheets
- plan-fact / cashflow из Excel-выгрузок PlanFact
- Metabase-дашборды поверх этих данных

Важно по слоям данных:

- `fact_metrics` — legacy weekly staging / reference слой для старых Google Sheets-импортов
- `fact_metric_observation` — основной canonical fact layer для нормализованных метрик
- `calculated_metric_value` — отдельный calculated layer для derived KPI поверх canonical fact layer

Важно по описанию метрик и источников:

- основной список метрик для чтения: [`generated/metric_catalogue_canonical.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/metric_catalogue_canonical.csv)
- основной файл “откуда берём и как считаем”: [`generated/fact_metric_source_of_truth_canonical.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/fact_metric_source_of_truth_canonical.csv)
- operational source map: [`docs/fact_layer_source_access.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/fact_layer_source_access.md)
- основной calculated formula registry: [`generated/calculated_metric_formula_registry_canonical.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/calculated_metric_formula_registry_canonical.csv)
- dependency map calculated-метрик: [`generated/calculated_metric_dependency_matrix.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/calculated_metric_dependency_matrix.csv)

Legacy / transition files:

- [`legacy/generated/legacy_seed/metric_catalogue_v4.csv`](/Users/Peter/Documents/Morpheus%20Metrics/legacy/generated/legacy_seed/metric_catalogue_v4.csv)
- [`legacy/generated/legacy_seed/metric_sources_v5.csv`](/Users/Peter/Documents/Morpheus%20Metrics/legacy/generated/legacy_seed/metric_sources_v5.csv)

Эти versioned transition-файлы не считаем основными для повседневного чтения. Они вынесены в `legacy/` и больше не должны быть точкой входа для активного кода.

Проект состоит из двух больших контуров:

1. `Weekly Metrics`
Загрузка недельных KPI по Москве и Санкт-Петербургу из Google Sheets в legacy-слой `fact_metrics`.

2. `PlanFact / P&L`
Загрузка банковских и управленческих операций из `.xlsx`-выгрузок PlanFact, нормализация статей, построение P&L-слоя и дэшбордов.

Отдельно поверх этих observed данных живёт `Calculated Layer`:

- derived KPI считаются отдельно от `fact_metric_observation`
- weekly formulas пересчитываются в момент weekly fact refresh
- monthly formulas пересчитываются в момент monthly fact refresh
- формулы, зависимости и run-логи хранятся как отдельный operational contour


## Текущая инфраструктура

- Хостинг: DigitalOcean
- База данных: PostgreSQL `analytics`
- BI: Metabase
- Основной рабочий каталог на сервере: `/opt/analytics/parser`

Используемая база:

- database: `analytics`
- user: `admin`
- password: `strongpassword`

Типовой connection string:

```bash
postgresql://admin:strongpassword@localhost:5432/analytics
```


## Структура проекта

Скрипты в репозитории:

- [`scripts/import_planfact_xlsx.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_planfact_xlsx.py)
- [`scripts/seed_planfact_accounting_articles.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/seed_planfact_accounting_articles.py)
- [`scripts/seed_planfact_article_mappings.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/seed_planfact_article_mappings.py)
- [`scripts/rebuild_planfact_pnl_view.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/rebuild_planfact_pnl_view.py)
- [`scripts/create_metabase_planfact_dashboard.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/create_metabase_planfact_dashboard.py)
- [`scripts/rebuild_weekly_metrics_yoy_views.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/rebuild_weekly_metrics_yoy_views.py)
- [`scripts/rebuild_weekly_metrics_trace_view.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/rebuild_weekly_metrics_trace_view.py)
- [`scripts/create_metabase_weekly_metrics_dashboard.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/create_metabase_weekly_metrics_dashboard.py)
- [`scripts/create_metabase_weekly_latest_comparison_dashboard.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/create_metabase_weekly_latest_comparison_dashboard.py)
- [`scripts/calculated_metric_registry.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/calculated_metric_registry.py)
- [`scripts/run_calculated_metrics.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_calculated_metrics.py)
- [`scripts/run_fact_and_calculation_refresh.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_fact_and_calculation_refresh.py)
- [`sql/create_weekly_dashboard_status_view.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_weekly_dashboard_status_view.sql)
- [`sql/create_calculated_metric_tables.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_calculated_metric_tables.sql)
- [`sql/create_calculated_metric_latest_run_view.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_calculated_metric_latest_run_view.sql)

## Dashboard Workflow

Для задач на создание или существенное изменение dashboard теперь есть отдельный skill:

- repo source: [`skills/create-dashboard/SKILL.md`](/Users/Peter/Documents/Morpheus%20Metrics/skills/create-dashboard/SKILL.md)
- local installed skill: [/Users/Peter/.codex/skills/create-dashboard/SKILL.md](/Users/Peter/.codex/skills/create-dashboard/SKILL.md)

Этот workflow требует:

- явно спросить, кому должен быть доступен dashboard;
- явно принять решение, новая логика живёт в `view` или в `calculated layer`;
- проверить, есть ли в проекте переиспользуемые `view`, SQL-артефакты или dashboard scripts;
- обновить реестр dashboard'ов как обязательную часть работы.

Основные связанные файлы:

- policy: [`docs/dashboard_creation_policy.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/dashboard_creation_policy.md)
- registry guide: [`docs/dashboard_registry.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/dashboard_registry.md)
- registry data: [`generated/dashboard_registry.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/dashboard_registry.csv)

Короткое правило принятия решения:

- `calculated layer` используем для reusable KPI и warehouse-semantic метрик;
- `view` используем для dashboard-specific serving logic, reshaping, comparison columns и presentation layer.


## Контур 1. Weekly Metrics

### Источник

Google Sheets через service account.

Источники:

- Москва: `unit = b2c_moscow`
- Санкт-Петербург: `unit = b2c_spb`

Парсер на сервере:

- `/opt/analytics/parser/parse_sheet.py`
- `/opt/analytics/parser/run_weekly_metrics_ingest.py`

Что он умеет:

- читать Google Sheets через service account
- автоопределять строку дат
- автоопределять строку диапазонов
- поддерживать разные layout листов
- протягивать `metric_group`, если ячейка визуально пустая
- резолвить `metric_key` через alias-слой
- писать unmapped пары в `unmapped_metrics`
- делать upsert в `fact_metrics`


### Основные таблицы weekly metrics

#### `fact_metrics`

Legacy weekly staging / reference таблица.

Это не основной нормализованный fact layer проекта. Таблица хранит технический snapshot старых weekly Google Sheets-импортов и нужна для:

- трассировки того, что было загружено из manual tables
- legacy weekly dashboards
- backfill / bridge в canonical слой

Основной canonical fact layer проекта: `fact_metric_observation`.

`fact_metrics` хранит недельные/дневные/месячные метрики в логике исходной таблицы.

Ключевые поля:

- `source_sheet_id`
- `source_gid`
- `source_tab`
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
- `row_order`
- `col_order`
- `loaded_at`

Смысловая уникальность:

- `(source_sheet_id, source_gid, unit, aggregation_level, period_start, metric_group, metric_name)`

Важно:

- уникальность метрики определяется парой `metric_group + metric_name`
- одинаковые `metric_name` в разных группах считаются разными сущностями


#### `metric_aliases`

Справочник локальных metric aliases.

Ключевые поля:

- `source_sheet_id`
- `source_gid`
- `source_tab`
- `unit`
- `metric_group`
- `alias_name`
- `metric_key`
- `is_active`


#### `unmapped_metrics`

Диагностическая таблица для пар, у которых нет alias.

Ключевые поля:

- `source_sheet_id`
- `source_gid`
- `source_tab`
- `unit`
- `metric_group`
- `raw_metric_name`
- `first_seen_at`
- `last_seen_at`
- `times_seen`

#### `weekly_import_runs`

Лог таблица для weekly-заливок из Google Sheets.

Хранит по каждой загрузке источника:

- `batch_id`
- `unit`
- `source_tab`
- `source_sheet_id`
- `source_gid`
- `triggered_by`
- `status`
- `exit_code`
- `rows_loaded`
- `metric_rows`
- `unmapped_pairs`
- `parser_stdout`
- `parser_stderr`
- `started_at`
- `finished_at`

SQL-скелет:

- [`sql/create_weekly_import_runs.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_weekly_import_runs.sql)

Wrapper-скрипт:

- [`scripts/run_weekly_metrics_ingest.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_weekly_metrics_ingest.py)

Он вызывает существующий `parse_sheet.py` по двум источникам:

- `b2c_moscow` / `weekly_b2c_moscow`
- `b2c_spb` / `weekly_b2c_spb`

и пишет результат каждой загрузки в `weekly_import_runs`.

#### `dashboard_refresh_runs`

Лог таблица пересборки слоя, на котором сидят weekly dashboard'ы.

Хранит:

- `batch_id`
- `job_name`
- `dashboard_scope`
- `triggered_by`
- `status`
- `exit_code`
- `yoy_refresh_ok`
- `trace_refresh_ok`
- `stdout`
- `stderr`
- `started_at`
- `finished_at`

SQL-скелет:

- [`sql/create_dashboard_refresh_runs.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_dashboard_refresh_runs.sql)

Wrapper-скрипт:

- [`scripts/run_weekly_dashboard_refresh.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_weekly_dashboard_refresh.py)

Он пересобирает:

- `weekly_metrics_yoy_series_6w`
- `weekly_metrics_yoy_latest_week`
- `weekly_metrics_latest_comparison`
- `weekly_metrics_trace`

Для карточки “последнее обновление” поверх weekly dashboards используется view:

- `weekly_dashboard_status`

Он отдаёт по `b2c_moscow` и `b2c_spb`:

- `last_import_finished_at`
- `last_rows_loaded`
- `latest_week_start`
- `last_dashboard_refresh_at`

Важно:

- это refresh слоя, на котором читают данные московский и петербургский weekly dashboards
- сами Metabase-объекты при этом не создаются заново, поэтому не плодятся дубликаты карточек и дэшбордов

### Автозапуск weekly metrics

На сервере DigitalOcean настроен cron:

- файл: `/etc/cron.d/weekly_metrics_ingest`
- расписание: каждый вторник в `08:00` по `Europe/Moscow`
- в cron это зафиксировано как `05:00 UTC`, чтобы не зависеть от `CRON_TZ`

Команда:

```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 5 * * 2 root /usr/bin/python3 /opt/analytics/parser/run_weekly_metrics_ingest.py --triggered-by cron >> /var/log/weekly_metrics_ingest.log 2>&1
```

После успешной загрузки weekly-таблиц wrapper дополнительно запускает:

- dashboard refresh job

То есть pipeline теперь такой:

1. загружаем `b2c_moscow`
2. загружаем `b2c_spb`
3. если обе загрузки успешны, пересобираем `weekly_metrics_yoy_*` и `weekly_metrics_trace`


### Weekly YoY слой

Для weekly metrics поверх `fact_metrics` сделаны view:

- `weekly_metrics_yoy_series_6w`
- `weekly_metrics_yoy_latest_week`
- `weekly_metrics_latest_comparison`

Они дают:

- последние 6 недель
- сравнение с теми же неделями год назад
- срез по `unit`, `metric_key`, `metric_group`, `metric_name`
- latest-week таблицу с:
  - результатом последней недели
  - динамикой неделя к неделе
  - динамикой к среднему за предыдущие 4 недели
  - динамикой год к году


### Metabase dashboard для weekly metrics

Создан дэшборд:

- `Weekly Metrics YoY`

Он содержит:

- latest week comparison для Москвы
- latest week comparison для СПб
- 6-week matrix для Москвы
- 6-week matrix для СПб
- 6-week trend для Москвы
- 6-week trend для СПб

Скрипт сборки:

- [`scripts/create_metabase_weekly_metrics_dashboard.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/create_metabase_weekly_metrics_dashboard.py)

Отдельно создан дэшборд:

- `Weekly Metrics Latest Comparison`

Он содержит две таблицы:

- `Moscow Weekly Latest Comparison`
- `SPB Weekly Latest Comparison`

Скрипт сборки:

- [`scripts/create_metabase_weekly_latest_comparison_dashboard.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/create_metabase_weekly_latest_comparison_dashboard.py)


## Контур 2. PlanFact / Cashflow / P&L

### Источник

Excel-выгрузки PlanFact формата `.xlsx`.

Загруженные тестовые файлы:

- `Выписка (4).xlsx`
- `Выписка (5).xlsx`
- `Выписка (6).xlsx`

Основная бизнес-особенность:

- строки типа `Часть` являются разбиением одной операции на несколько строк


### Двухслойная модель

#### Сырой слой

`planfact_cashflow_entries`

Это импорт из источника почти без интерпретации.

Хранит:

- обычные строки
- `split_parent`
- `split_part`
- raw-поля Excel
- effective-поля с наследованием от parent


#### Аналитический слой

`planfact_cashflow_analytic`

Это view для аналитики.

Особенности:

- включает только `entry` и `split_part`
- исключает `split_parent`, чтобы не было double count
- уже содержит business unit mapping


### Основные таблицы PlanFact

#### `dim_business_units`

Справочник бизнес-юнитов.

Ключевые поля:

- `business_unit_code`
- `business_unit_name`
- `analytics_unit_code`
- `analytics_unit_name`
- `source_system`
- `is_active`

Используемые маппинги:

- `Москва` -> `b2c_moscow`
- `Санкт-Петербург` -> `b2c_spb`
- `Корпоративы` -> `b2b`


#### `planfact_cashflow_entries`

Сырой импорт PlanFact.

Ключевые группы полей:

- source metadata:
  - `source_file_name`
  - `source_sheet_name`
  - `source_row_number`
- связь строк:
  - `root_source_row_number`
  - `parent_source_row_number`
- тип:
  - `row_type`
  - `entry_role`
  - `has_split_children`
- effective business fields:
  - даты
  - контрагент
  - статья
  - проект
  - сумма
  - валюта
- raw fields:
  - `raw_*`


#### `dim_planfact_accounting_articles`

Зашитый справочник учетных статей PlanFact.

Хранит:

- дерево статей через `parent_article_id`
- `tab_code`, `tab_name`
- `path`
- `depth`
- `sort_order`
- `is_group`
- `is_locked`

Примеры веток:

- `Доходы -> Франшиза -> Паушалка`
- `Доходы -> Продажа билетов B2C`
- `Доходы -> Нераспределенный доход`
- `Расходы -> ФОТ -> IT ФОТ`
- `Расходы -> ПЕРЕЕЗД -> Техника`
- `Расходы -> ПРЕМИИ 2025 -> Премии актёры`
- `Расходы -> Нераспределенный расход`


#### `planfact_article_mappings`

Таблица маппинга сырой статьи в зашитую структуру.

Ключевые поля:

- `source_system`
- `raw_parent_articles`
- `raw_article`
- `accounting_article_id`
- `mapping_method`
- `mapping_confidence`
- `is_active`

Текущий статус:

- бизнес-статьи автоматически закрыты
- unmapped остаются только технические:
  - `[Зачисление]`
  - `[Списание]`


### P&L слой

Текущий view:

- `planfact_pnl_test`

Строится поверх:

- `planfact_cashflow_analytic`
- `planfact_article_mappings`
- `dim_planfact_accounting_articles`

Что делает:

- нормализует строки в P&L-секции
- собирает `Выручка`, `Основные расходы`, `Прочие доходы`, `Налог на прибыль`, `Дивиденды`
- сохраняет порядок строк отчета
- позволяет строить табличные P&L-матрицы в Metabase

Важно:

- это рабочий аналитический слой, но не полный клон внутренней логики PlanFact
- в спорных кейсах периодизация может зависеть от бизнес-правил самого PlanFact


### Metabase dashboard для PlanFact

Создан дэшборд:

- `PlanFact P&L Test`

Скрипт:

- [`scripts/create_metabase_planfact_dashboard.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/create_metabase_planfact_dashboard.py)

Что умеет:

- пересоздавать / обновлять карточки через Metabase API
- переключать диапазон месяцев
- обновлять существующий dashboard


## Контур 3. Calculated Layer

`Calculated Layer` живёт поверх `fact_metric_observation` и хранит только derived KPI:

- средние значения
- отношения и доли
- `%`-метрики
- member-level calculated metrics по `show_name` или `channel_name`

Главный принцип:

- observed facts и calculated values не смешиваются
- observed значения лежат в `fact_metric_observation`
- рассчитанные значения лежат в `calculated_metric_value`

### Основные runtime tables

- `calculated_metric_definition`
  - runtime mirror формул из canonical CSV
- `calculated_metric_dependency`
  - resolved dependencies для каждой формулы
- `calculated_metric_value`
  - рассчитанные значения по периоду и scope
- `calculation_runs`
  - run-level лог расчётов
- `calculation_run_steps`
  - step-level лог по каждой formula row

SQL-схема:

- [`sql/create_calculated_metric_tables.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_calculated_metric_tables.sql)
- [`sql/create_calculated_metric_latest_run_view.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_calculated_metric_latest_run_view.sql)

### Основные canonical artifacts

- [`generated/calculated_metric_formula_registry_canonical.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/calculated_metric_formula_registry_canonical.csv)
  - что считаем, на каком grain и в каком scope
- [`generated/calculated_metric_dependency_matrix.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/calculated_metric_dependency_matrix.csv)
  - от каких observed metrics зависит каждая calculated metric
- [`generated/deferred_to_calculated_layer.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/deferred_to_calculated_layer.csv)
  - backlog и candidate list для calculated слоя

Подробные design docs:

- [`docs/calculated_layer_design.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/calculated_layer_design.md)
- [`docs/calculated_metric_formula_registry.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/calculated_metric_formula_registry.md)
- [`docs/calculated_layer_recalc_policy.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/calculated_layer_recalc_policy.md)
- [`docs/calculated_layer_canonical_files.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/calculated_layer_canonical_files.md)

### Поддерживаемые formula types

- `ratio_of_sums`
  - `sum(numerator_metric) / sum(denominator_metric)` в рамках периода и scope
- `share_of_partition_total`
  - `member_value / total_value` внутри одного dynamic scope, например доля канала в общем трафике

### Текущие active calculated metrics

- `average_show_load_sold_tickets`
  - `Number of tickets / Number of shows`
- `average_show_load_visitors`
  - `Number of show visitors / Number of shows`
- `variable_salary_share_of_revenue`
  - `Costs - Salary variable / Revenue` по каждому спектаклю
- `channel_share_of_website_visits`
  - `Website visits(channel) / Website visits(all channels)` по каждому каналу

### Как считается

Registry loader:

- [`scripts/calculated_metric_registry.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/calculated_metric_registry.py)

Основной runner:

- [`scripts/run_calculated_metrics.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_calculated_metrics.py)

Wrapper для запуска вместе с fact refresh:

- [`scripts/run_fact_and_calculation_refresh.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_fact_and_calculation_refresh.py)

Operational правила:

- weekly fact update -> пересчитываем только weekly calculated metrics для этой недели
- monthly fact update -> пересчитываем только monthly calculated metrics для этого месяца
- по умолчанию не пересчитываем весь history

### Что важно про scope

Calculated formulas могут быть:

- aggregate-level
  - например unit-level average show load
- member-level
  - например `show_name = b2c_show_names`
  - например `channel_name = marketing_channel_names`

В member-level формулах runner пишет отдельную строку в `calculated_metric_value` на каждый конкретный `show_name` или `channel_name`, найденный в fact layer.


## Как запускать

### 1. Импорт новой выписки PlanFact

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/import_planfact_xlsx.py \
  --xlsx-path "/Users/Peter/Downloads/Выписка (N).xlsx" \
  --database-url "postgresql://admin:strongpassword@134.122.83.160:5432/analytics"
```


### 2. Обновить справочник статей

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/seed_planfact_accounting_articles.py \
  --database-url "postgresql://admin:strongpassword@134.122.83.160:5432/analytics"
```


### 3. Обновить маппинг статей

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/seed_planfact_article_mappings.py \
  --database-url "postgresql://admin:strongpassword@134.122.83.160:5432/analytics"
```


### 4. Пересобрать P&L view

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/rebuild_planfact_pnl_view.py \
  --database-url "postgresql://admin:strongpassword@134.122.83.160:5432/analytics"
```


### 5. Пересобрать weekly metrics YoY views

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/rebuild_weekly_metrics_yoy_views.py \
  --database-url "postgresql://admin:strongpassword@134.122.83.160:5432/analytics"
```


### 6. Обновить Metabase P&L dashboard

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/create_metabase_planfact_dashboard.py \
  --metabase-url "http://134.122.83.160:3001" \
  --metabase-api-key "YOUR_API_KEY" \
  --database-url "postgresql://admin:strongpassword@134.122.83.160:5432/analytics" \
  --metabase-database-id 2 \
  --month-start 2026-01 \
  --month-end 2026-03 \
  --update-existing-dashboard-id 2 \
  --update-existing-matrix-card-id 40 \
  --update-existing-monthly-card-id 41 \
  --update-existing-business-unit-card-id 42
```


### 7. Создать weekly metrics YoY dashboard

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/create_metabase_weekly_metrics_dashboard.py \
  --metabase-url "http://134.122.83.160:3001" \
  --metabase-api-key "YOUR_API_KEY" \
  --metabase-database-id 2
```


### 8. Прогнать calculated metrics для недели

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/run_calculated_metrics.py \
  --database-url "postgresql://admin:strongpassword@134.122.83.160:5432/analytics" \
  --period-granularity week \
  --period-start 2026-05-11
```


### 9. Прогнать calculated metrics для месяца

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/run_calculated_metrics.py \
  --database-url "postgresql://admin:strongpassword@134.122.83.160:5432/analytics" \
  --period-granularity month \
  --period-start 2026-05-01
```


## Рекомендуемый порядок обновления данных

Для PlanFact:

1. импорт новой `.xlsx`
2. обновление `dim_planfact_accounting_articles` при необходимости
3. обновление `planfact_article_mappings`
4. пересборка `planfact_pnl_test`
5. обновление Metabase dashboard

Важно:

- импортёр PlanFact теперь удаляет логические дубли после каждой загрузки
- приоритет остаётся за более свежей выпиской по `source_period_end`
- это защищает от перекрывающихся выгрузок, когда один и тот же хвост периода попадает в несколько `.xlsx`

Для weekly metrics:

1. прогон `parse_sheet.py` по нужным Google Sheets
2. при появлении новых метрик обновление `metric_aliases`
3. пересборка weekly YoY views
4. обновление / пересоздание дэшбордов

Для calculated layer:

1. обновление `fact_metric_observation` за нужный период
2. прогон `run_calculated_metrics.py` для того же `period_granularity`
3. проверка `calculation_runs` / `calculation_run_steps`
4. при необходимости проверка latest-run view для рассчитанных значений


## Известные ограничения

- Metabase не даёт нативный `expand/collapse` как в PlanFact
- P&L `test` слой не гарантирует 100% совпадение с внутренней логикой PlanFact во всех спорных кейсах периода
- некоторые отличия на `1` рубль возникают из-за округления
- технические строки `[Зачисление]` и `[Списание]` не маппятся в бизнес-структуру


## Следующие возможные шаги

- сделать production-версию P&L view вместо `planfact_pnl_test`
- добавить filter-driven dashboards в Metabase
- сделать dashboards по metric groups для weekly metrics
- настроить регулярный cron для загрузки weekly metrics
- вынести README в более формальную техдокументацию по окружениям и доступам
