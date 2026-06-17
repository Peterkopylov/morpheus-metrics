# Monthly P&L Analytics by City

## Purpose

Admin-only monthly P&L analytics dashboard for Moscow and SPB.

It shows:

- top P&L rollups of levels 1 and 2 from the active canonical structure;
- margin as `Operating profit / Revenue`;
- shares of variable costs, fixed costs, marketing costs, and actor payroll in revenue;
- comparison columns for latest month, previous month, and average across the latest 6 months.

## Metabase

- Dashboard: `Monthly P&L Analytics by City`
- Dashboard id: `24`
- Audience: `admins`
- Access: `restricted`
- Collection: `Общедоступные/Tech`
- Collection id: `12`
- URL: `https://metabase.134.122.83.160.sslip.io/dashboard/24`
- Cards:
  - `324` — period card
  - `325` — Moscow table
  - `326` — SPB table

## Serving Layer

- View: `monthly_pnl_city_analytics_base`
- SQL: [create_monthly_pnl_city_analytics_view.sql](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_monthly_pnl_city_analytics_view.sql)
- Rebuild script: [rebuild_monthly_pnl_city_analytics_view.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/rebuild_monthly_pnl_city_analytics_view.py)
- Dashboard builder: [create_metabase_monthly_pnl_city_dashboard.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/create_metabase_monthly_pnl_city_dashboard.py)

## Modeling Decisions

- Dashboard logic stays in a serving view because the request is primarily presentation-specific reshaping over already canonical monthly P&L facts.
- Source of truth is active monthly P&L in `fact_metric_observation`, not history views.
- Row semantics come from the active canonical P&L structure in [pnl_structure_mapping_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/catalog/pnl_structure_mapping_canonical.csv).
- Metric availability and monthly P&L source semantics are anchored in [source_of_truth.csv](/Users/Peter/Documents/Morpheus%20Metrics/fact/source_of_truth.csv) and [monthly_pnl_ingestion.md](/Users/Peter/Documents/Morpheus%20Metrics/fact/monthly_pnl_ingestion.md).
- Dashboard lives directly in `Tech` because access is intentionally limited to admins.
