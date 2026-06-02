# Monthly Marketing Operational Dashboard

## Purpose

Monthly public marketing monitor for Moscow and SPB. It mirrors the weekly operational marketing dashboard, but uses monthly sources so that P&L marketing spend rows missing from weekly ingestion are visible by channel.

## Metabase

- Dashboard: `Monthly Marketing Operational Monitor`
- Dashboard id: `22`
- Collection: `Общедоступные`
- Audience: `all company`
- Access: `public`
- Dashboard card:
  - `319` — Moscow/SPB table, stored in `Tech.`

Historical implementation artifact:

- `318` — old period card, removed from the dashboard layout and stored in `Tech.`

## Serving Layer

- View: `monthly_marketing_operational_latest`
- SQL: [create_monthly_marketing_operational_view.sql](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_monthly_marketing_operational_view.sql)
- Rebuild script: [rebuild_monthly_marketing_operational_view.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/rebuild_monthly_marketing_operational_view.py)
- Dashboard builder: [create_metabase_monthly_marketing_operational_dashboard.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/create_metabase_monthly_marketing_operational_dashboard.py)

## Modeling Decisions

- Dashboard logic stays in a serving view. It reshapes monthly facts into a table and applies dashboard-specific attribution labels.
- Monthly `Marketing costs` by channel prefer channelized PlanFact/P&L rows.
- If PlanFact only has a monthly marketing total without channel breakdown, the view keeps the total complete by subtracting already observed channel costs and placing the remaining amount into `general` / `Общие маркетинг расходы`.
- `direct` PlanFact channel is normalized to the canonical dashboard row `perfomance`.
- Revenue attribution follows the weekly dashboard pattern:
  - `total`: ERP/PlanFact total revenue
  - `perfomance`: Performance marketing revenue from Yandex Metrica (`favoriteGoalsConvertedRUBRevenue`, automatic attribution, `Yandex Direct` + `Yandex Direct: Undetermined`)
  - `partners`: ERP partner revenue when available
  - other channels: survey-share allocation from ERP source-attribution responses
  - `general`: unallocated/general marketing cost bucket, no attributed revenue

## April 2026 Refresh

After publishing, the April monthly KPI contour was refreshed for:

- `erp_monthly_core`
- `erp_survey_satisfaction_monthly`
- `yandex_metrica_monthly`
- `yandex_metrica_tracked_purchase_visits_monthly`
- `yandex_direct_monthly`

Run id: `monthly_kpi_fact_ingestion_2026-04-01_1687e38a`.
