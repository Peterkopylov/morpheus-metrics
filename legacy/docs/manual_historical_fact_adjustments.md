# Manual Historical Fact Adjustments

This file documents manual monthly additions written directly into the official
historical fact source `google_sheets_monthly_economics_historical`.

Why this exists:
- these are approved additive adjustments for the historical period;
- they should behave like part of the main historical fact layer;
- they must be visible both to historical rollup backfill and to the leaf-only
  rollup views.

Current adjustments:
- `Costs - Salary fixed`
  - `2025-07` .. `2025-12`
  - monthly total `250000`
  - allocation:
    - `b2c_moscow` = `125000` (50%)
    - `b2c_spb` = `75000` (30%)
    - `b2b` = `50000` (20%)
- `Other expenses`
  - `2025-07`
  - `business_unit = general`
  - `810000`

Storage policy:
- `source_system = google_sheets_monthly_economics_historical`
- `source_record_key` prefix:
  - `manual_historical_adjustment:`
- importer is idempotent and clears only rows with that prefix before rewrite.
