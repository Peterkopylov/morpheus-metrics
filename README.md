# Morpheus Metrics

Аналитический проект для DigitalOcean, который собирает в одном PostgreSQL:

- weekly metrics из Google Sheets
- plan-fact / cashflow из Excel-выгрузок PlanFact
- Metabase-дашборды поверх этих данных

Проект состоит из двух больших контуров:

1. `Weekly Metrics`
Загрузка недельных KPI по Москве и Санкт-Петербургу из Google Sheets в `fact_metrics`.

2. `PlanFact / P&L`
Загрузка банковских и управленческих операций из `.xlsx`-выгрузок PlanFact, нормализация статей, построение P&L-слоя и дэшбордов.


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
- [`sql/create_weekly_dashboard_status_view.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_weekly_dashboard_status_view.sql)


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

Фактовая таблица недельных/дневных/месячных метрик.

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


## Временные ERP dashboards

### TEMP ERP Sales KPI Prototype

Dashboard:

- `TEMP ERP Sales KPI Prototype`
- Metabase dashboard id: `8`

Источник:

- временная таблица `tmp_erp_sales_kpi_snapshot`

Скрипты:

- [`scripts/refresh_tmp_erp_sales_kpi_snapshot.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/refresh_tmp_erp_sales_kpi_snapshot.py)
- [`scripts/create_metabase_tmp_erp_sales_kpi_dashboard.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/create_metabase_tmp_erp_sales_kpi_dashboard.py)

Автообновление:

- hourly cron на сервере
- файл: `/etc/cron.d/tmp_erp_sales_kpi_refresh`
- лог: `/var/log/tmp_erp_sales_kpi_refresh.log`
- расписание:

```cron
12 * * * * root /usr/bin/python3 /opt/analytics/parser/refresh_tmp_erp_sales_kpi_snapshot.py >> /var/log/tmp_erp_sales_kpi_refresh.log 2>&1
```

### TEMP ERP Sellout Next 30 Days

Dashboard:

- `TEMP ERP Sellout Next 30 Days`
- Metabase dashboard id: `9`

Источник:

- временная таблица `tmp_erp_sellout_next_30d_snapshot`

Что показывает:

- ближайшие `30` дней по Москве и СПб
- строки = даты
- колонки = аббревиатуры спектаклей
- для каждого спектакля:
  - число сеансов
  - `%` выкупленности

Как считается sold count:

- будущие сеансы берутся из `ERP /shows/get`
- реальные проданные билеты считаются из `ERP /tickets/by-sell`
- match:
  - `tickets.by_sell.seance_id = shows.get.show_id`
- sold count:
  - количество ticket rows с `total > 0`

Как считается `%`:

- `sold_tickets / sum(tickets_count)` по дате и спектаклю

Скрипты:

- [`scripts/refresh_tmp_erp_sellout_next_30d_snapshot.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/refresh_tmp_erp_sellout_next_30d_snapshot.py)
- [`scripts/create_metabase_tmp_erp_sellout_next_30d_dashboard.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/create_metabase_tmp_erp_sellout_next_30d_dashboard.py)

Автообновление:

- hourly cron на сервере
- файл: `/etc/cron.d/tmp_erp_sellout_next_30d_refresh`
- лог: `/var/log/tmp_erp_sellout_next_30d_refresh.log`
- расписание:

```cron
22 * * * * root /usr/bin/python3 /opt/analytics/parser/refresh_tmp_erp_sellout_next_30d_snapshot.py >> /var/log/tmp_erp_sellout_next_30d_refresh.log 2>&1
```


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
