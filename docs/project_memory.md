# Project Memory

Короткие постоянные правила, которые должны переживать сессии и не теряться в коде.

## 1. Active First

Primary reading layer:

- [docs/system_overview.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/system_overview.md)
- [catalog/metric_catalogue_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/catalog/metric_catalogue_canonical.csv)
- [catalog/pnl_structure_mapping_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/catalog/pnl_structure_mapping_canonical.csv)
- [fact/source_of_truth.csv](/Users/Peter/Documents/Morpheus%20Metrics/fact/source_of_truth.csv)
- [fact/source_access.md](/Users/Peter/Documents/Morpheus%20Metrics/fact/source_access.md)
- [calculated/formula_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/formula_registry.csv)
- [calculated/dependency_matrix.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/dependency_matrix.csv)
- [serving/dashboard_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboard_registry.csv)

## 2. Legacy Is Exception-Only

Папка [legacy](/Users/Peter/Documents/Morpheus%20Metrics/legacy) не является active source of truth.

Правило:

- active code не должен зависеть от `legacy/`
- routine changes не должны начинаться с `legacy/`
- идти в `legacy/` можно только для history, bridge-logic, migration, reconciliation

## 3. New Observed Metric Workflow

Если появляется новая observed metric:

1. добавить её в [catalog/metric_catalogue_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/catalog/metric_catalogue_canonical.csv)
2. добавить source/scope/counting rule в [fact/source_of_truth.csv](/Users/Peter/Documents/Morpheus%20Metrics/fact/source_of_truth.csv)
3. обновить access/context в [fact/source_access.md](/Users/Peter/Documents/Morpheus%20Metrics/fact/source_access.md), если меняется operational path
4. только после этого менять importer или registry

## 4. Calculated Workflow

Если появляется новая derived metric:

1. добавить её в [calculated/formula_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/formula_registry.csv)
2. проверить зависимости в [calculated/dependency_matrix.csv](/Users/Peter/Documents/Morpheus%20Metrics/calculated/dependency_matrix.csv)
3. убедиться, что policy в [calculated/recalc_policy.md](/Users/Peter/Documents/Morpheus%20Metrics/calculated/recalc_policy.md) остаётся корректной

## 5. Dashboard Workflow

Если меняется serving/dashboard слой:

- использовать [skills/create-dashboard/SKILL.md](/Users/Peter/Documents/Morpheus%20Metrics/skills/create-dashboard/SKILL.md)
- обновлять [serving/dashboard_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/serving/dashboard_registry.csv)

## 6. Monthly Financial Rollups

Для monthly financial contour materialized rollups inside `fact` допустимы и являются осознанным исключением из общего правила strict observed/calculated split.

Канонические правила:

- leaf-слой собираем только по business units;
- materialized rollup / formula metrics тоже считаем только по business units;
- runtime `Revenue` включает не только unscoped BU revenue, но и валидные show-scoped revenue rows внутри того же BU, включая `show_name = Certificate`;
- runtime monthly P&L схлопывает технический `show_name`-split обратно в обычные BU-level `Revenue` и `Operating profit`; raw fact при этом может сохранять исходный `show_name`;
- canonical `Revenue` и `Revenue - Show date` — это разные observed metrics: первая привязана к дате продажи, вторая должна быть привязана к дате проведения шоу; их нельзя silently подменять друг другом в importer или dashboard semantics;
- `total` всегда строим как сумму business units одного и того же semantic level;
- `general` не равен `total`, но входит в сумму `total` как bucket нераспределённых значений;
- если в конкретном месяце workbook `general` пустой или вообще не выгружен из PlanFact, monthly P&L import можно запускать без него; в таком месяце `general` просто дает нулевой вклад в runtime `total`;
- observed `business_unit = total` можно хранить как reference / trace, но не использовать как основной runtime `total`.
- для ERP-derived метрики `Number of shows` канонический смысл — только неотменённые шоу; отменённые шоу должны идти в `Number of shows cancelled` и не попадать в denominator для витрин вроде `Number of show visitors / Number of shows`.
- для ERP-derived метрики `Number of show visitors` weekly и monthly должны использовать `guests` по неотменённым шоу; поле `visitors` не считается каноническим входом для этого контура.
- для ERP `Costs - Salary variable` weekly и monthly general rows должны считать полный `salary_total + bonus_total`; unallocated bonus tail нельзя оставлять только в payload, если мы хотим semantic parity между week и month.

## 6a. Monthly P&L Reading Path

Для routine monthly P&L задач, особенно dashboard / serving / ad hoc analytics по городам:

- сначала читать active `catalog/` и `fact/`, а не `serving/` и не `legacy/`;
- canonical P&L structure и правила сворачивания статей брать из [catalog/pnl_structure_mapping_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/catalog/pnl_structure_mapping_canonical.csv);
- наличие и scope canonical monthly P&L rows проверять в [fact/source_of_truth.csv](/Users/Peter/Documents/Morpheus%20Metrics/fact/source_of_truth.csv);
- runtime monthly P&L rules проверять в [fact/monthly_pnl_ingestion.md](/Users/Peter/Documents/Morpheus%20Metrics/fact/monthly_pnl_ingestion.md);
- historical / history / legacy views не использовать как первую точку входа для routine monthly P&L work;
- `scripts/serving/rebuild_monthly_pnl_history_views.py` и производные history views использовать только когда задача прямо про history, repair, backfill, reconciliation или нужно понять старую bridge-логику.

Практическое правило: если нужно собрать новый monthly P&L dashboard или ad hoc monthly P&L table, сначала проектируем его от `fact_metric_observation` + active canonical docs, и только потом смотрим, есть ли уже подходящий serving/view слой.

## 7. Monthly P&L Routine

Текущий recurring monthly P&L process:

- import monthly PlanFact Excel
- rebuild accepted monthly P&L rollups

Historical monthly economics loaders and manual dividends backfill:

- не являются частью регулярного monthly process
- живут в `legacy/`
- запускаются только для repair/backfill/history
