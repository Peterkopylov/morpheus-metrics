**Canonical Files**
This is the compact, canonical description layer for the fact system. Older `v2`/`v4`/working files stay in the project as reference, but these are the files to read first.

Main files:
- [`metric_catalogue_canonical.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/metric_catalogue_canonical.csv)
  - what each metric is
- [`fact_metric_source_of_truth_canonical.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/fact_metric_source_of_truth_canonical.csv)
  - where each metric comes from, in which scope, and how it is counted
- [`pnl_structure_mapping_canonical.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/pnl_structure_mapping_canonical.csv)
  - how P&L hierarchy nodes map to canonical metrics
- [`legacy_metric_mapping.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/legacy_metric_mapping.csv)
  - how legacy weekly groups map into the canonical metric layer
- [`fact_layer_source_access.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/fact_layer_source_access.md)
  - operational source map: access, tokens, cabinets, legacy reference tables, and implementation gaps
- [`project_memory.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/project_memory.md)
  - short persistent working rules for future sessions
- [`monthly_metric_history_assembly.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/monthly_metric_history_assembly.md)
  - how monthly metrics were assembled across historical sheet, PlanFact, observed total, and manual dividends backfill

Design split:
- `metric_catalogue_canonical.csv`
  - only metric identity fields
- `fact_metric_source_of_truth_canonical.csv`
  - only source-of-truth and counting logic
- `pnl_structure_mapping_canonical.csv`
  - only P&L hierarchy metadata and canonical metric linkage
- `legacy_metric_mapping.csv`
  - only migration/reference mapping from the old system
- `fact_layer_source_access.md`
  - operational access and implementation context for the source systems

Generator:
- [`generate_canonical_metric_system_files.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/generate_canonical_metric_system_files.py)

Archived transition references:
- [`metric_catalogue_v4.csv`](/Users/Peter/Documents/Morpheus%20Metrics/legacy/generated/legacy_seed/metric_catalogue_v4.csv)
- [`fact_metric_source_of_truth.csv`](/Users/Peter/Documents/Morpheus%20Metrics/legacy/generated/fact_metric_source_of_truth.csv)

Policy:
- do not delete old files yet
- prefer updating the canonical files for everyday system understanding
- treat older versioned files as reference / transition artifacts
- keep versioned seed files under `legacy/` so they are visibly not the primary reading layer
- treat `fact_layer_source_access.md` as the fourth canonical file, but keep it in `docs/`, not in `generated/`
- treat `manual_table` as a mandatory full numeric reference layer: all numeric values from the weekly manual tables must be ingested even when another source is primary for the same business metric
- for `manual_table`, completeness is checked against live Google Sheets via the canonical service account; `fact_metrics` is only a staging layer and may contain technical gaps
