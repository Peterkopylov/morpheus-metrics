# Historical Leaf Migration Archive

This archive holds one-off artifacts from the May 2026 migration of historical
monthly Google Sheets P&L into the leaf-first fact workflow.

Why this archive exists:
- the migration produced many intermediate reports and transfer-status files;
- they are useful for audit/debug;
- they should not stay mixed with the current operational generated layer.

What stays active in the main project layer:
- `generated/historical_leaf_pnl_metric_mapping.csv`
- `scripts/build_historical_leaf_pnl_mapping.py`
- `scripts/import_historical_monthly_economics_sheet_to_fact.py`
- `scripts/import_historical_monthly_economics_prototype_extension_to_fact.py`
- `scripts/import_historical_pnl_rollup_backfill_to_fact.py`
- `scripts/rebuild_monthly_pnl_history_views.py`

What was archived:
- one-off transfer status CSVs
- migration-time import reports
- temporary review artifacts from the leaf migration

Archive scope:
- historical Google Sheets -> leaf-only fact migration
- prototype bridge migration checks
- temporary transfer-status reconciliation outputs
