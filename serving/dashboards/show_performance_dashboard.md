# Dashboard по спектаклям

Статус на `2026-05-30`.

## Что сделано

Для нового дэшборда собран serving layer:

- [`show_performance_dashboard_base`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_show_performance_dashboard_base.sql)

И scripted Metabase builder:

- [`create_metabase_show_performance_dashboard.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/create_metabase_show_performance_dashboard.py)

Для контроля достоверности добавлена SQL-витрина:

- [`show_performance_dashboard_quality_checks`](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_show_performance_dashboard_quality_checks.sql)

## Доступ

- Metabase collection: `Общедоступные`
- collection id: `9`
- dashboard id: `21`
- card id: `299`
- URL:
  - `https://metabase.134.122.83.160.sslip.io/dashboard/21`

## Фильтры

- период:
  - `Период с`
  - `Период по`
  - важно: выделять строго период с пн по вс
- бизнес-юнит:
  - dropdown по полю `business_unit`
  - пустое значение = оба юнита

## Layout

- строки:
  - метрики
- столбцы:
  - спектакли

## Метрики по спектаклю

- `Количество визитов на сайте`
  - `Website visits` по `show_name`
- `Количество заказов`
  - `Number of orders`
- `Конверсия визит-заказ`
  - `Number of orders / Website visits`
- `Количество билетов`
  - `Number of tickets`
- `Среднее количество билетов в заказе`
  - `Number of tickets / Number of orders`
- `Всего шоу`
  - `Number of shows`
- `Всего зрителей по факту`
  - `Number of show visitors`
- `Средняя загрузка факт`
  - `Number of show visitors / Number of shows`

For ERP-based show metrics, `Number of shows` means non-cancelled shows only; cancelled shows belong to `Number of shows cancelled` and do not enter the denominator of `Средняя загрузка факт`.
- `Средняя оценка по опросам`
  - `Sum of post-show ratings / Number of show rating responses`
- `Выручка от спектакля`
  - `Revenue`
- `Доля ЗП актеров в выручке`
  - `Costs - Salary variable / Revenue`

## Model choices

`calculated`:

- `Конверсия визит-заказ`
- `Среднее количество билетов в заказе`
- `Средняя загрузка факт`
- `Средняя оценка по опросам`

`view`:

- layout reshaping для транспонированной таблицы
- dashboard-serving row `Доля ЗП актеров в выручке`

Для самого дэшборда итоговые ratio по выбранному периоду считаются в serving query поверх сумм numerator/denominator, чтобы фильтр по диапазону давал математически корректный результат, а не среднее из weekly ratios.

## Data notes

- serving view uses primary source filters:
  - `Website visits` from `yandex_metrica`
  - sales, shows, visitors, surveys, and actor salary from `erp`
- исключаем `сертификаты` из show-таблицы;
- `Costs - Salary variable` на show-level может не полностью сходиться с general, потому что часть bonus tail в ERP остаётся только в general scope;
- для новых спектаклей survey/salary история может начинаться позже, чем sales/visits история.

## Quality checks

`show_performance_dashboard_quality_checks` проверяет:

- `source_integrity`
  - предупреждает, если в show-level scope есть non-primary строки, которые могут случайно попасть в дэшборд при будущих правках;
- `weekly_show_vs_general_revenue`
  - проверяет, что show-level revenue за неделю не больше ERP general revenue за ту же неделю;
- `missing_required_metric`
  - предупреждает, если по show-week есть не все ключевые метрики;
- `monthly_4w_vs_planfact_revenue`
  - сверяет четыре полные недели дэшборда с monthly PlanFact `Revenue`.

Для `monthly_4w_vs_planfact_revenue` расхождение не считается ошибкой само по себе: дэшборд показывает show-level ERP revenue без сертификатов, а P&L шире по составу.
