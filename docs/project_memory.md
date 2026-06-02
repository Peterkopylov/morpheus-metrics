# Project Memory

Этот файл нужен как короткая постоянная памятка, чтобы не терять ключевые правила устройства проекта между сессиями.

## 1. Canonical First

Активный source of truth проекта:

- [metric_catalogue_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/metric_catalogue_canonical.csv)
- [fact_metric_source_of_truth_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/fact_metric_source_of_truth_canonical.csv)
- [fact_layer_source_access.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/fact_layer_source_access.md)
- [fact_layer_canonical_files.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/fact_layer_canonical_files.md)

Если меняется active logic системы, править нужно сначала их.

## 2. Legacy Is Archive

Папка:

- [legacy](/Users/Peter/Documents/Morpheus%20Metrics/legacy)

это не active layer, а архив / transition / reference.

Правило:

- active scripts не должны читать из `legacy/`
- исключение допустимо только для специальных bridge-артефактов вроде:
  - [legacy_metric_mapping.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/legacy_metric_mapping.csv)

## 3. New Metrics Workflow

Если появляется новая observed-метрика:

1. сначала добавить её в [metric_catalogue_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/metric_catalogue_canonical.csv)
2. потом добавить source / scope / counting logic в [fact_metric_source_of_truth_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/fact_metric_source_of_truth_canonical.csv)
3. только после этого писать или менять importer
4. только после этого загружать в `fact_metric_observation`

Нельзя начинать с legacy seed-файлов, если речь идёт об active контуре.

## 4. Manual Tables Rule

`manual_table` — обязательный полный numeric reference layer.

Это значит:

- все численные значения из live weekly manual tables надо тянуть максимально полно
- даже если primary source для этой же бизнес-метрики находится в другом сервисе
- полноту manual layer сверяем по live Google Sheets
- `fact_metrics` для manual-слоя — только staging / technical snapshot

## 5. Weekly Ticket Sales Rule

Для B2C ticket sales:

- `ERP` = primary
- `Yandex Tickets` = deprecated for weekly fact ingestion
- `manual_table` = reference / reconciliation

Это касается как минимум:

- `Revenue`
- `Number of tickets`
- `Number of orders`

в разрезах `general / show / partner`.

Operational filter:

- в weekly ERP sales `status = 0` означает отмену покупки билета
- в fact ingestion считаем только строки с `status != 0`

## 6. Traffic And Spend Rule

- `Marketing costs` берём из `Yandex Direct`
- `Website visits` и show-page traffic берём из `Yandex Metrica`

## 7. Agent Commission Rule

Для weekly manual B2C sales / partner rows суммы по агентам считаем уже
`net of commission`:

- `кассир` = `gross * 0.90` (комиссия `10%`)
- `яндекс афиша` = `gross * 0.90` (комиссия `10%`)
- `тикетленд` = `gross * 0.85` (комиссия `15%`)
- `афиша ру` = `gross * 0.93` (комиссия `7%`)

Это operational rule для интерпретации и переноса агентских продаж в manual-layer:

- в weekly ручных таблицах агентские суммы должны попадать уже после вычета комиссии;
- если считаем `поступления на счет` / partner revenue по агенту вручную,
  применяем эти коэффициенты;
- если raw source даёт gross-продажи агента, в manual logic сначала переводим их в net.

## 8. Monthly P&L Rule

Если грузим monthly P&L:

- в fact layer кладём observed monthly P&L values
- percentage / margin rows считаем `calculated`, а не raw facts
- не возвращаемся к модели “хранить все финансовые операции” только ради этого слоя
- для monthly PlanFact P&L грузим отдельные workbook’и по business unit
- если PlanFact даёт observed consolidated `total`, он живёт как отдельный observed `business_unit = total`
- если в monthly PlanFact появляются новые P&L-строки или новые P&L-узлы:
  - сначала обновляем `generated/pnl_structure_mapping_canonical.csv`
  - потом обновляем `scripts/planfact_monthly_pnl_report_mapping.py`
  - только после этого переимпортируем PlanFact
- если строка PlanFact, которую importer считал `leaf`, вдруг становится `parent`,
  это should-fail alert:
  - importer должен остановиться с ошибкой;
  - сначала пересматриваем P&L structure и mapping, потом продолжаем импорт.
- если total сами считаем как сумму по business units для historical continuity, это делаем как derived monthly view, а не как новый raw source
- `Revenue` остаётся одной canonical metric; revenue detail rows не размножаем в новые metric names
- P&L hierarchy живёт отдельным metadata-layer, а не внутри calculated
- для этого слоя используем:
  - [pnl_structure_mapping_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/pnl_structure_mapping_canonical.csv)
  - [pnl_structure_mapping.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/pnl_structure_mapping.md)
- c `2026-05-25` в P&L structure:
  - `Сервисы и их настройка` = отдельная статья в `Постоянных`
  - `КОМИССИИ БАНКОВ` = отдельная статья в `Переменных`
  - `Отсмотр видео` = отдельная статья в `Переменных`
- история monthly-метрик собрана по кускам и должна читаться через unified monthly assembly:
  - [monthly_metric_history_assembly.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/monthly_metric_history_assembly.md)
- активные monthly sources сейчас такие:
  - `google_sheets_monthly_economics_historical`
  - `planfact`
  - `manual_dividends_total_history`
- основной `google_sheets_monthly_economics_historical` теперь хранит
  leaf-only historical fact-layer, а не старую mixed subtotal/history версию
- approved additive manual corrections тоже пишем в этот же source через
  `source_record_key` с префиксом `manual_historical_adjustment:`
- `general` не равен `total`
- observed `total` из PlanFact живёт как raw fact с `business_unit = total`
- derived historical `total` для continuity живёт во views, не как synthetic raw source
- в основном historical sheet строка `210` `Общая прибыль` должна оставаться `exclude`
- в основном historical sheet строка `219` `Прибыль для основателей` должна жить как `Net profit` с `business_unit = total`
- в основном historical sheet строки `248`, `250`, `254` (`Театр Москва`, `Театр Петербург`, `Корпоратив`) должны оставаться `exclude`, потому что это процентные helper-строки
- в основном historical sheet строка `79` `Итого переменные расходы` должна жить как `Variable costs` с `business_unit = total`, не `general`
- в основном historical sheet строка `119` `Итого постоянные расходы` должна жить как `Fixed costs` с `business_unit = total`, не `general`
- для historical monthly marketing subtotal строка `Итого расходы на маркетинг` хранится как observed `Marketing costs` с `channel = total`
- для historical total bridge по ручному правилу пользователя сейчас используем:
  - `Net profit total = Revenue - Fixed costs - Variable costs - Marketing costs(channel=total)`
- важный historical nuance:
  - для периода `2020-11 .. 2021-12` live-проверка показала, что historical total лучше всего сходится без отдельного вычитания `Tax`;
  - рабочая формула на этом участке:
    - `Net profit = Revenue - Variable costs - Fixed costs - Marketing costs(channel=total) - Investment costs - Cost article - Директорский процент + Other income`
  - с `2022-01` начинается другой historical regime, который требует отдельного разбора.
- для historical BU-level gaps synthetic source `historical_leaf_rollup_backfill`
  материализует `Variable costs` и `Fixed costs` в `fact_metric_observation`
  по canonical P&L hierarchy.
- `historical_leaf_rollup_backfill` строится поверх leaf-only historical facts;
- старый `canonical_rollup_backfill` удалён из active fact-layer.
- active leaf-only views читают уже основной
  `google_sheets_monthly_economics_historical`;
- одноразовые артефакты leaf-migration и transfer-status cleanup вынесены в
  [historical_leaf_migration_2026_05.md](/Users/Peter/Documents/Morpheus%20Metrics/legacy/docs/historical_leaf_migration_2026_05.md)
  и соответствующий архивный generated-контур, чтобы не мешать рабочему слою.
- для альтернативного monthly leaf-only contour:
  - historical Google Sheets lower-level статьи читаются из основного
    `google_sheets_monthly_economics_historical`
  - `monthly_pnl_leaf_only_history` также включает фильтрованный PlanFact lower-level
    contour как `planfact_leaf_only`
  - начиная с `2026-05-24` основной monthly PlanFact importer тоже переведён в тот же
    leaf-only режим:
    - raw `planfact` facts содержат только lower-level статьи и верхнюю строку `Выручка`
    - subtotal/result rows больше не импортируются в fact
  - в этом PlanFact contour берём только named BU (`b2c_moscow`, `b2c_spb`, `b2b`, `franchise`)
    и `general`; исключаем subtotal/result rows; `Revenue` берём только из строки `Выручка`
  - для leaf-only monthly total:
    - `total = general + named BU`
    - то есть derived `total` в leaf-only контуре не должен терять `general`
  - поверх него строится `monthly_pnl_leaf_only_rollup_history_with_total`
    по canonical P&L hierarchy.
  - в самой P&L structure с `2026-05-24` появился explicit formula-node:
    - `Прибыль` = canonical `Operating profit`
    - формула: `Revenue - Variable costs - Fixed costs`
  - этот узел нельзя считать обычным parent-child rollup;
    для него есть отдельный derived monthly contour внутри
    `monthly_pnl_leaf_only_rollup_history_with_total`.
  - в recursive leaf-only rollup `channel_name` не должен подниматься в parent-ряды:
    channel остаётся только на leaf-метриках, а `Variable costs` / `Fixed costs`
    и более высокие rollup-метрики собираются без channel attribution.

## 9. Before Big Changes

Перед изменением архитектуры или source logic нужно проверить:

- [README.md](/Users/Peter/Documents/Morpheus%20Metrics/README.md)
- [fact_layer_canonical_files.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/fact_layer_canonical_files.md)
- [project_memory.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/project_memory.md)

Если код противоречит этим правилам, код надо приводить к ним, а не наоборот.

## 10. Calculated Layer

У проекта есть отдельный `calculated` слой поверх `fact_metric_observation`.

Главные артефакты:

- [calculated_metric_formula_registry_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/calculated_metric_formula_registry_canonical.csv)
- [calculated_metric_dependency_matrix.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/calculated_metric_dependency_matrix.csv)
- [calculated_metric_formula_registry.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/calculated_metric_formula_registry.md)
- [calculated_layer_canonical_files.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/calculated_layer_canonical_files.md)
- [calculated_layer_recalc_policy.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/calculated_layer_recalc_policy.md)
- [calculated_layer_design.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/calculated_layer_design.md)

Runtime / SQL:

- [calculated_metric_registry.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/calculated_metric_registry.py)
- [run_calculated_metrics.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/run_calculated_metrics.py)
- [create_calculated_metric_tables.sql](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_calculated_metric_tables.sql)
- [create_calculated_metric_latest_run_view.sql](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_calculated_metric_latest_run_view.sql)

Ключевая модель:

- `observed` и `calculated` живут отдельно
- canonical CSV-реестр — source of truth для formulas
- PostgreSQL таблицы `calculated_metric_definition`, `calculated_metric_dependency`, `calculated_metric_value`, `calculation_runs` — runtime mirror и execution layer

Что сейчас реально поддержано runner'ом:

- `ratio_of_sums`
- `share_of_partition_total`
- `allocate_total_by_partition_share`
- `apply_partner_commission_rate`

Что важно помнить:

- многие calculated-метрики уже зафиксированы в registry, но часть из них ещё `pending` или `manual_definition_pending`
- P&L hierarchy — это не calculated layer сам по себе;
  исключение: отдельные formula-nodes внутри P&L вроде `Прибыль = Revenue - Variable costs - Fixed costs`
  можно материализовать отдельным derived SQL-контуром
- percentage / margin rows из PlanFact не кладём в raw fact, а относим к calculated-логике
- для weekly B2C partner commissions:
  - commission rates живут в [partner_commission_rate_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/partner_commission_rate_registry.csv)
  - `Partner commission` живёт как calculated metric
  - monthly `Cost article - Агентские` остаётся отдельным accounting metric из PlanFact

## 11. Weekly Metabase Dashboards

- legacy weekly Metabase dashboards `4` / `5` / `3` / `7` всё ещё живут на старом weekly reference layer:
  - `fact_metrics`
  - `weekly_metrics_yoy_series_6w`
  - `weekly_metrics_yoy_latest_week`
  - `weekly_metrics_latest_comparison`
- fact-based weekly аналоги теперь тоже созданы:
  - `16` — `Weekly Metrics YoY (fact)`
  - `17` — `Moscow Weekly Metrics Charts (fact)`
  - `18` — `SPB Weekly Metrics Charts (fact)`
- для максимально близкого воспроизведения старых Moscow/SPB chart dashboards из `fact`
  используем weekly reference rows, уже загруженные в `fact_metric_observation` как:
  - `source_system = manual_table`
  - `payload.fact_metrics_metric_group`
  - `payload.fact_metrics_metric_name`
  - `payload.fact_metrics_value_type`
  - `source_record_key` row-number как стабильный weekly row identity
- fact-based weekly chart contour живёт в views:
  - `weekly_fact_metrics_dashboard_base`
  - `weekly_fact_metrics_yoy_series_6w`
  - `weekly_fact_metrics_yoy_latest_week`
  - `weekly_fact_metrics_latest_comparison`
