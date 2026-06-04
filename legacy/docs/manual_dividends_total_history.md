**Manual Dividends Total History**
Этот контур нужен для точечного дозаполнения historical `Dividends | business_unit = total`, когда:

- observed `planfact total` ещё нет;
- в `monthly_pnl_total_history` по месяцу нет никакой total-информации;
- но есть подтверждённая ручная история выплат дивидендов.

Источник:
- [manual_dividends_total_history.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/manual_dividends_total_history.csv)

Правило:
- импортируем только месяцы, которых **нет** в `monthly_pnl_total_history` для:
  - `metric_name = Dividends`
  - `business_unit = total`
- существующие месяцы из:
  - `planfact total`
  - derived historical total
  не перетираем.

Технически:
- source_system: `manual_dividends_total_history`
- metric: `Dividends`
- business_unit: `total`
- granularity: `month`

Скрипт:
- [import_manual_dividends_total_history_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_manual_dividends_total_history_to_fact.py)
