# Appsmith Queries

Ниже — минимальные SQL-запросы для Appsmith.

## 1. `InsertManualMetric`

```sql
INSERT INTO manual_metric_entries (
  unit,
  aggregation_level,
  period_start,
  period_end,
  period_label,
  metric_group,
  metric_name,
  metric_key,
  value,
  value_raw,
  value_type,
  notes,
  created_by
) VALUES (
  {{ UnitSelect.selectedOptionValue }},
  {{ AggregationSelect.selectedOptionValue }},
  {{ PeriodStartPicker.selectedDate }},
  {{ PeriodEndPicker.selectedDate || null }},
  {{ PeriodLabelInput.text || null }},
  {{ MetricGroupInput.text }},
  {{ MetricNameInput.text }},
  {{ MetricKeyInput.text || null }},
  {{ Number(ValueInput.text) }},
  {{ ValueRawInput.text || null }},
  {{ ValueTypeSelect.selectedOptionValue }},
  {{ NotesInput.text || null }},
  {{ CreatedByInput.text || null }}
)
ON CONFLICT (unit, aggregation_level, period_start, metric_group, metric_name)
DO UPDATE SET
  period_end = EXCLUDED.period_end,
  period_label = EXCLUDED.period_label,
  metric_key = EXCLUDED.metric_key,
  value = EXCLUDED.value,
  value_raw = EXCLUDED.value_raw,
  value_type = EXCLUDED.value_type,
  notes = EXCLUDED.notes,
  created_by = EXCLUDED.created_by,
  updated_at = NOW(),
  is_active = TRUE
RETURNING *;
```

## 2. `SearchMetrics`

```sql
SELECT
  record_source,
  source_table,
  record_id,
  unit,
  aggregation_level,
  period_start,
  period_end,
  period_label,
  metric_group,
  metric_name,
  metric_key,
  value,
  value_raw,
  value_type,
  notes,
  created_by,
  recorded_at,
  source_sheet_url
FROM app_metric_search
WHERE 1 = 1
  AND (
    {{ !SourceSelect.selectedOptionValue }} OR
    record_source = {{ SourceSelect.selectedOptionValue }}
  )
  AND (
    {{ !UnitFilter.selectedOptionValue }} OR
    unit = {{ UnitFilter.selectedOptionValue }}
  )
  AND (
    {{ !AggregationFilter.selectedOptionValue }} OR
    aggregation_level = {{ AggregationFilter.selectedOptionValue }}
  )
  AND (
    {{ !MetricGroupFilter.selectedOptionValue }} OR
    metric_group = {{ MetricGroupFilter.selectedOptionValue }}
  )
  AND (
    {{ !MetricNameFilter.selectedOptionValue }} OR
    metric_name = {{ MetricNameFilter.selectedOptionValue }}
  )
  AND (
    {{ !PeriodStartFilter.selectedDate }} OR
    period_start >= {{ PeriodStartFilter.selectedDate }}
  )
  AND (
    {{ !PeriodEndFilter.selectedDate }} OR
    period_start <= {{ PeriodEndFilter.selectedDate }}
  )
  AND (
    {{ !SearchTextInput.text }} OR
    lower(search_blob) LIKE '%' || lower({{ SearchTextInput.text }}) || '%'
  )
ORDER BY period_start DESC, unit, metric_group, metric_name
LIMIT 500;
```

## 3. `LoadUnits`

```sql
SELECT DISTINCT unit AS label, unit AS value
FROM app_metric_search
ORDER BY unit;
```

## 4. `LoadMetricGroups`

```sql
SELECT DISTINCT metric_group AS label, metric_group AS value
FROM app_metric_search
WHERE (
  {{ !UnitFilter.selectedOptionValue }} OR
  unit = {{ UnitFilter.selectedOptionValue }}
)
ORDER BY metric_group;
```

## 5. `LoadMetricNames`

```sql
SELECT DISTINCT metric_name AS label, metric_name AS value
FROM app_metric_search
WHERE (
  {{ !UnitFilter.selectedOptionValue }} OR
  unit = {{ UnitFilter.selectedOptionValue }}
)
AND (
  {{ !MetricGroupFilter.selectedOptionValue }} OR
  metric_group = {{ MetricGroupFilter.selectedOptionValue }}
)
ORDER BY metric_name;
```

## 6. `LoadSources`

```sql
SELECT DISTINCT record_source AS label, record_source AS value
FROM app_metric_search
ORDER BY record_source;
```

## 7. `LoadAggregationLevels`

```sql
SELECT DISTINCT aggregation_level AS label, aggregation_level AS value
FROM app_metric_search
ORDER BY aggregation_level;
```
