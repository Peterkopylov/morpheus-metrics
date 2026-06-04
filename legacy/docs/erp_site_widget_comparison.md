# ERP Site/Widget vs Manual Weekly Comparison

Сверка `site/widget` между:

- ERP `POST /tickets/by-sell`
- weekly manual Google Sheets / `fact_metrics`

Период:

- `2026-04-20 .. 2026-04-26`

Цель:

- понять, является ли `site/widget` в ручных weekly-таблицах той же сущностью,
  что и основной site-agent в ERP.

## ERP agent mapping used

- Moscow: `agent_id = 39320770`
- SPB: `agent_id = 39801873`

Интерпретация:

- это собственный сайт / виджет;
- эти агенты не должны попадать в partner-split rows;
- они используются только для site/widget comparison и site-side totals.

## Moscow

### Manual weekly

Revenue:

- `билеты -> билеты виджет (сайт)` = `701 664`
- `билеты сд -> билет сд виджет (сайт)` = `238 752`
- total manual site revenue = `940 416`

Orders:

- `САЙТ -> заказов всего (Я.билеты)` = `127`

Tickets:

- `САЙТ -> билетов всего (Я.билеты)` = `243`

### ERP

- `agent_id = 39320770`
- revenue = `1 145 180`
- orders = `123`
- tickets = `233`

### Difference

- revenue: manual lower by `204 764`
- orders: manual higher by `4`
- tickets: manual higher by `10`

## Saint Petersburg

### Manual weekly

Revenue:

- `Поступления на счет -> билеты виджет (сайт)` = `265 200`
- `Поступления на счет -> билет сд виджет (сайт)` = `47 520`
- total manual site revenue = `312 720`

Orders:

- `Сайт -> Количество заказов` = `60`

Tickets:

- `Сайт -> Количество билетов` = `115`

### ERP

- `agent_id = 39801873`
- revenue = `373 250`
- orders = `60`
- tickets = `109`

### Difference

- revenue: manual lower by `60 530`
- orders: exact match
- tickets: manual higher by `6`

## Practical conclusion

- `site/widget` in manual weekly and ERP is very close for `orders`
  and reasonably close for `tickets`.
- `site/widget revenue` in manual weekly is **not** the same as ERP gross
  revenue for the site agent.
- For future ingestion:
  - `Number of orders` and `Number of tickets` can be trusted much more
    than manual site revenue in site/widget comparisons.
  - `Revenue` should be treated as a potentially transformed / netted /
    manually adjusted figure in the weekly sheets.
