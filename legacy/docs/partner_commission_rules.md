# Partner Commission Rules

Canonical metadata-layer for weekly B2C ticket-sales partner commissions:

- [`partner_commission_rate_registry.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/partner_commission_rate_registry.csv)

Meaning:

- `commission_rate` — доля агентской комиссии от gross partner revenue
- `net_multiplier` — сколько остаётся после вычета комиссии

Approved active rules:

- `кассир` = `10%` commission = `0.90` net multiplier
- `яндекс афиша` = `10%` commission = `0.90` net multiplier
- `тикетленд` = `15%` commission = `0.85` net multiplier
- `афиша ру` = `7%` commission = `0.93` net multiplier

Operational intent:

- эти правила не заменяют monthly accounting article `Cost article - Агентские`
- они нужны для weekly operational / calculated contour
- calculated metric `Partner commission` считается от observed gross `Revenue`
  в grain `business_unit + week + show_name + partner_name`
- weekly dashboard serving views may roll up `Partner commission` as partner-channel
  operating spend, but calculated values are not written back into the fact layer
- fact layer remains observed/imported source data only; reusable derived metrics
  stay in `calculated_metric_value`
