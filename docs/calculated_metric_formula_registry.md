# Calculated Metric Formula Registry

Единый реестр вида:

- `что считаем`
- `на каком grain`
- `в каком scope`
- `из каких observed metrics`
- `по какому formula type`

Главный artifact:

- [`generated/calculated_metric_formula_registry_canonical.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/calculated_metric_formula_registry_canonical.csv)

Dependency matrix:

- [`generated/calculated_metric_dependency_matrix.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/calculated_metric_dependency_matrix.csv)

## Current formula types

- `ratio_of_sums`
  - `sum(numerator_metric) / sum(denominator_metric)` в рамках заданного периода и scope
- `share_of_partition_total`
  - `member_value / total_value` внутри одного dynamic scope, например `channel -> share of all channels`
- `allocate_total_by_partition_share`
  - `member_value / sum(all members) * total_metric` внутри одного dynamic scope
- `apply_partner_commission_rate`
  - `gross revenue * commission_rate(partner)` в weekly partner/show contour

## Current statuses

- `active`
  - formula fully supported by the current runner
- `pending`
  - metric belongs to calculated layer, but automatic computation is intentionally not enabled yet

## Current MVP formulas

- `average_show_load_sold_tickets`
  - `Number of tickets / Number of shows`
- `average_show_load_visitors`
  - `Number of show visitors / Number of shows`
- `variable_salary_share_of_revenue`
  - `Costs - Salary variable / Revenue` по каждому спектаклю
- `channel_share_of_website_visits`
  - `Website visits(channel) / Website visits(all channels)` по каждому каналу
- `marketing_costs_share_of_revenue`
  - `Marketing costs / Revenue` как ДРР для weekly/monthly reusable marketing reporting
- `estimated_channel_orders_from_metrica_mix`
  - `tracked_purchase_visits(channel) / tracked_purchase_visits(all channels) * total Number of orders`
- `partner_commission`
  - `Revenue(show, partner) * partner commission rate`
- monthly PlanFact P&L margins
  - `Операционная рентабельность = Operating profit / Revenue`
  - `Рентабельность по EBITDA = EBITDA / Revenue`
  - `Рентабельность по EBIT = EBIT / Revenue`
  - `Рентабельность по EBT = EBT / Revenue`
  - `Рентабельность чистой прибыли = Net profit / Revenue`

## Pending formulas

- `average_sd_load_sold_tickets`
- `average_sd_load_visitors`

Они уже зафиксированы в calculated layer, но не считаются автоматически, пока не зафиксирован достаточный atomic source contour именно для `СД`.
