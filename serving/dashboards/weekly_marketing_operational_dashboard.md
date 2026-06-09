# Weekly Marketing Operational Dashboard

## Purpose

Еженедельный operational dashboard по маркетинговым каналам для широкой компании.

Базовый формат:

- пользователь выбирает диапазон недель через dashboard-фильтры `Период с` и `Период по`;
- если фильтры не выбраны, показывается вся доступная история недель;
- период отчета отдельной карточкой сверху;
- Москва и СПб в одной общей таблице;
- город и каналы строками;
- ключевые показатели агрегируются за выбранный период по каждому каналу;
- итоговая строка `Общее` по каждому городу.

## Audience and Access

- audience: all company
- access scope: common/public folder in Metabase

## Modeling Decision

- `ДРР` вынесен в `calculated layer` как reusable KPI:
  - weekly general scope
  - weekly channel scope
  - monthly general scope
- dashboard-specific wide reshape остаётся во `view`:
  - [`sql/create_weekly_marketing_operational_view.sql`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_weekly_marketing_operational_view.sql)

## Reuse

- existing pattern reused:
  - `scripts/run_calculated_metrics.py`
  - `calculated/formula_registry.csv`
- Metabase builder scripts family `scripts/serving/create_metabase_*dashboard.py`
- dashboard-specific serving layer with weekly history:
  - `weekly_marketing_operational_latest`

## Current Columns

- `Город`
- `Канал`
- `Расходы`
- `Визиты`
- `Metrica tracked orders`
- `Estimated channel orders`
- `Заказы`
- `Билеты`
- `Revenue`
- `Revenue method`
- `ДРР`
- `Доля канала по опросам`

## Current Channel Buckets

- `Перформанс маркетинг`
- `Органика`
- `SMM`
- `Агрегаторы / партнеры`
- `PR`
- `От друзей`
- `Ссылки на других сайтах`
- `Email`
- `Прочее`

## Current Limitation

Для текущей версии dashboard:

- `Metrica tracked orders` = purchase-converted visits из Яндекс.Метрики по каналам
- `Estimated channel orders` = аллокация общего `Website orders` по миксу `Metrica tracked orders`
- `Доля канала по опросам` считается из `Number of source-attribution responses` через dashboard-level mapping survey categories -> channel buckets and rolls up over the selected period
- `Заказы` в этом dashboard трактуются как `Website orders`, а не как общий all-sales `Number of orders`
- `Website orders` теперь живет в canonical fact layer как отдельная observed metric из ERP owned site/widget agent
- `Revenue` в этом dashboard является composite attribution metric, а не единой financial revenue:
  - `Перформанс маркетинг` = `Performance marketing revenue` from Yandex Metrica (`favoriteGoalsConvertedRUBRevenue`, automatic attribution, `Yandex Direct` + `Yandex Direct: Undetermined`)
  - `Агрегаторы / партнеры` = ERP partner-total revenue (`partner_name IS NOT NULL`, `show_name IS NULL`) to avoid double-counting show+partner detail rows
  - `Общее` = ERP total revenue
  - остальные каналы = ERP total revenue * survey source share
- `Revenue method` показывает, какое правило использовано в строке
- `Расходы` для `Агрегаторы / партнеры` = weekly rollup of calculated `partner_commission`
- partner commission is read from the calculated layer by the serving view and is not written back into fact
- полностью пустые channel rows скрываются из dashboard table
- dashboard table hides zero values for sparse tracked/estimated channel-order metrics to reduce visual noise
- `Расходы` and `Revenue` are displayed as formatted money strings with thousands separators and `р.`
- `Metrica tracked orders`, `Website orders`, and `Estimated channel orders` are backfilled from the 2025-12-29 weekly period through the latest full week available on 2026-05-31

Также в текущем normalized weekly fact-слое channel-level source contour для hard commerce totals по всем каналам не подтверждён, поэтому:

- `Заказы`
- `Билеты`
- canonical ERP `Revenue`

сейчас надёжно доступны только для строки `Общее`, а не для каждого канала отдельно.

Отдельный нюанс:

- dashboard `ДРР` считается от composite `Revenue`
- это удобно для operational marketing attribution, но не должно использоваться как financial P&L DRR без явной оговорки

## Build Path

1. Run weekly fact ingestion for the updated week.
2. Run calculated metrics for the same weekly period:
   - `marketing_costs_share_of_revenue`
   - `estimated_channel_orders_from_metrica_mix`
   - `partner_commission`
3. Rebuild view:
   - [`scripts/serving/rebuild_weekly_marketing_operational_view.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/rebuild_weekly_marketing_operational_view.py)
4. Publish dashboard:
   - [`scripts/serving/create_metabase_weekly_marketing_operational_dashboard.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/create_metabase_weekly_marketing_operational_dashboard.py)
   - existing dashboard can be updated with `--update-existing-dashboard-id`
