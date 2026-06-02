# Calculated Layer Design

## Goal

Добавить отдельный `calculated` слой поверх `fact_metric_observation`, чтобы:

- считать derived KPI отдельно от наблюдаемых `fact`-метрик;
- пересчитывать только затронутый период в момент апдейта `fact`-слоя;
- не смешивать `source of truth` и formula logic в одной таблице;
- иметь такой же operational contour, как у `fact`-слоя: schema, canonical files, run logs, debug views.


## Scope

В этом слое живут только расчетные метрики:

- средние значения;
- отношения и доли;
- `%`-метрики;
- KPI, которые в legacy weekly / monthly sheets уже существуют как числа, но должны считаться поверх atomic `fact`-метрик.

В этот слой не кладём:

- сырые данные источников;
- наблюдаемые значения из ERP / PlanFact / Yandex Tickets / manual sheets;
- агрегаты, которые already trusted source уже сам поставляет как observed metric.


## Design Principles

1. `observed` и `calculated` живут отдельно.
2. Формула должна быть описана как data, а не только как Python-код.
3. Пересчёт должен быть period-aware:
   - weekly fact update -> пересчитываем только weekly calculated metrics для этой недели
   - monthly fact update -> пересчитываем только monthly calculated metrics для этого месяца
4. Пересчёт должен быть dependency-aware:
   - если обновился один период, не пересчитываем весь history без необходимости
5. Каждый расчет должен быть debuggable:
   - видно run
   - видно шаг
   - видно numerator / denominator / input metrics


## Required Artifacts

### 1. SQL schema

Основной SQL-файл:

- [`sql/create_calculated_metric_tables.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_calculated_metric_tables.sql)

В нём создаются:

- `calculated_metric_definition`
- `calculated_metric_dependency`
- `calculated_metric_value`
- `calculation_runs`
- `calculation_run_steps`

### 2. Canonical files

Основные canonical files:

- [`generated/calculated_metric_formula_registry_canonical.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/calculated_metric_formula_registry_canonical.csv)
- [`generated/calculated_metric_dependency_matrix.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/calculated_metric_dependency_matrix.csv)
- [`docs/calculated_metric_formula_registry.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/calculated_metric_formula_registry.md)
- [`docs/calculated_layer_recalc_policy.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/calculated_layer_recalc_policy.md)

### 3. Registry / runner

- [`scripts/calculated_metric_registry.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/calculated_metric_registry.py)
- [`scripts/run_calculated_metrics.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_calculated_metrics.py)

### 4. Serving / debug views

- [`sql/create_calculated_metric_latest_run_view.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_calculated_metric_latest_run_view.sql)

### 5. Fact-triggered wrapper

- [`scripts/run_fact_and_calculation_refresh.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_fact_and_calculation_refresh.py)

Этот wrapper нужен, чтобы `calculation` слой обновлялся в тот же operational момент, что и `fact`-слой.


## Data Model

### `calculated_metric_definition`

Хранит одну активную расчетную формулу в конкретном scope.

Ключевые поля:

- `calculated_metric_key`
- `calculated_metric_name`
- `period_granularity`
- `business_unit`
- `show_name`
- `partner_name`
- `channel_name`
- `value_kind`
- `formula_type`
- `version`
- `status`

Важно:

- определение формулы делаем scope-aware;
- одна и та же бизнес-формула может существовать в нескольких scope rows;
- `status = pending` допускается для formula placeholders, у которых ещё нет полного atomic source contour.

### `calculated_metric_dependency`

Явный список зависимостей формулы.

Ключевые поля:

- `definition_id`
- `dependency_role`
- `dependency_metric_key`
- `dependency_granularity`

Для MVP достаточно ролей:

- `numerator`
- `denominator`

Позже можно расширить:

- `input`
- `filter_basis`
- `window_anchor`

### `calculated_metric_value`

Отдельное storage-место для результата расчёта.

Ключевые поля:

- `calculated_metric_key`
- `business_unit`
- `show_name`
- `partner_name`
- `channel_name`
- `period_granularity`
- `period_start`
- `period_end`
- `value_numeric`
- `value_text`
- `version`
- `calculation_run_id`
- `payload`

`payload` нужен для trace:

- numerator value
- denominator value
- formula type
- source metric keys

### `calculation_runs`

Run-level log.

Хранит:

- `run_id`
- `period_granularity`
- `period_start`
- `period_end`
- `trigger_mode`
- `status`
- `payload`

### `calculation_run_steps`

Step-level log.

Хранит:

- `run_id`
- `step_key`
- `calculated_metric_key`
- `status`
- `started_at`
- `finished_at`
- `notes`
- `stdout_excerpt`
- `stderr_excerpt`


## MVP Formula Types

На первом шаге достаточно поддержать:

- `ratio_of_sums`
- `share_of_partition_total`
- `allocate_total_by_partition_share`
- `apply_partner_commission_rate`

Семантика:

- берём сумму numerator metric по заданному scope и периоду
- берём сумму denominator metric по тому же scope и периоду
- считаем `numerator_sum / denominator_sum`

Примеры:

- `Средняя загрузка шоу (выкупленные билеты)` = `Number of tickets / Number of shows`
- `Средняя загрузка шоу (по факту дошедшие зрители)` = `Number of show visitors / Number of shows`
- `доля переменных зп в выручке` = `Costs - Salary variable / Revenue` по каждому `show_name`
- `доля каналов в посещаемости страниц` = `Website visits(channel) / Website visits(all channels)` по каждому `channel_name`
- `Partner commission` = `Revenue(show, partner) * commission_rate(partner)` по каждому `show_name + partner_name`

### Dynamic member scopes

Для части формул target scope задаёт не один aggregate row, а набор member-level rows:

- `show_name = b2c_show_names`
- `channel_name = marketing_channel_names`
- `show_name = b2c_show_names` + `partner_name = b2c_partner_names`

В таких случаях runner должен:

- определить одну dynamic dimension формулы;
- собрать member-level numerator / denominator values;
- записать отдельное `calculated_metric_value` на каждый конкретный `show_name` или `channel_name`.


## Period-Aware Recalculation Policy

### Weekly

После weekly fact update:

- запускаем `run_calculated_metrics.py --period-granularity week --period-start <monday>`
- выбираем только `active` weekly formulas
- пересчитываем только эту неделю

### Monthly

После monthly fact update:

- запускаем `run_calculated_metrics.py --period-granularity month --period-start <month_start>`
- выбираем только `active` monthly formulas
- пересчитываем только этот месяц

### Why not full-history recalculation

Полный пересчёт всего history по умолчанию не нужен, потому что:

- дороже operationally;
- хуже для debugging;
- скрывает, какой именно update изменил KPI;
- не нужен для формул без rolling windows.


## Initial Metric Set

Уже есть явный seed-список:

- [`generated/deferred_to_calculated_layer.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/deferred_to_calculated_layer.csv)

На текущем MVP:

- `Средняя загрузка шоу (выкупленные билеты)` -> `active`
- `Средняя загрузка шоу (по факту дошедшие зрители)` -> `active`
- `доля переменных зп в выручке` -> `active`
- `доля каналов в посещаемости страниц` -> `active`
- `Средняя загрузка СД (выкупленные билеты)` -> `pending`
- `Средняя загрузка СД (по факту дошедшие зрители)` -> `pending`

Причина `pending` для `СД`-метрик:

- в текущем canonical `fact`-контуре уже есть отдельные cancelled SD metrics,
- но ещё нет достаточно явной atomic numerator / denominator пары для стабильного автоматического расчёта средней загрузки именно по `СД`.


## Execution Flow

1. `fact`-слой обновляет период.
2. wrapper определяет соответствующий `period_granularity`.
3. runner загружает active formula definitions из canonical CSV.
4. runner синхронизирует definitions и dependencies в PostgreSQL.
5. runner считает только формулы нужного grain и периода.
6. runner пишет значения в `calculated_metric_value`.
7. runner логирует run и steps.
8. latest-run view показывает, что именно пересчиталось.


## Open Extension Points

Позже можно добавить:

- formula windows: `rolling_4w`, `rolling_3m`
- formulas поверх calculated metrics
- materialized serving views
- backfill mode для диапазона периодов
- DB-seeded formula registry вместо file-seeded registry


## MVP Boundaries

В текущей реализации intentionally не делаем:

- DSL для произвольных формул;
- nested dependency graph execution;
- auto-discovery monthly refresh runner;
- пересчёт `СД`-метрик без явного atomic source contour.

Это осознанное ограничение, чтобы сначала ввести стабильный operational слой, а не сразу строить универсальный formula engine.
