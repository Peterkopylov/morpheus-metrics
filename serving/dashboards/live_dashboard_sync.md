# Live Dashboard Sync

Post-refresh sync contour to keep active Metabase dashboards live after fact ingestion and calculated-metric refresh.

## Goal

After fact load and calculation refresh:

- rebuild the serving SQL views that dashboards depend on
- touch active Metabase dashboards and cards so the BI layer re-reads fresh data

## Entry Point

- [sync_active_metabase_dashboards.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/sync_active_metabase_dashboards.py)

## Scope Modes

- `weekly`
  - refreshes slot-attendance snapshot
  - rebuilds slot-attendance dashboard base view
  - rebuilds weekly fact YoY views
  - rebuilds weekly marketing operational view
  - rebuilds show performance base view
  - rebuilds ingestion technical monitor view
  - refreshes active weekly dashboards from registry, including slot dashboards
- `monthly_kpi`
  - refreshes slot-attendance snapshot
  - rebuilds slot-attendance dashboard base view
  - rebuilds monthly marketing operational view
  - rebuilds ingestion technical monitor view
  - refreshes active monthly-KPI-facing dashboards from registry, including slot dashboards
- `monthly_pnl`
  - refreshes slot-attendance snapshot
  - rebuilds slot-attendance dashboard base view
  - rebuilds monthly marketing operational view
  - rebuilds monthly P&L city analytics view
  - rebuilds ingestion technical monitor view
  - refreshes active monthly-P&L-facing dashboards from registry, including slot dashboards
- `all`
  - runs the union of all rebuilds and refreshes all active dashboards from registry

## Slot Dashboards

The slot dashboards are now part of the same sync contour:

- refresh script:
  - [`scripts/refresh_erp_show_slot_attendance_snapshot.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/refresh_erp_show_slot_attendance_snapshot.py)
- serving rebuild:
  - [`scripts/serving/rebuild_show_slot_attendance_dashboard_base.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/rebuild_show_slot_attendance_dashboard_base.py)

So any cron or wrapper that already runs [`sync_active_metabase_dashboards.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/sync_active_metabase_dashboards.py) for `weekly`, `monthly_kpi`, `monthly_pnl`, or `all` will refresh these dashboards too.

## Dashboard Selection

The sync script reads [dashboard_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboard_registry.csv) and refreshes active Metabase dashboards by `dashboard_key`.

This avoids hardcoding the full card catalog in the cron wrapper and keeps the refresh set aligned with the registry.
