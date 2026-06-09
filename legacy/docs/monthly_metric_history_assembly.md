# Monthly Metric History Assembly

Этот файл фиксирует, как мы по кускам собрали monthly-слой и как его теперь правильно читать.

## Цель

Нам нужен один сквозной monthly P&L/history layer, хотя данные приехали не из одного источника, а из нескольких:

- historical Google Sheet;
- observed PlanFact workbook'и по business unit;
- observed PlanFact workbook `total`;
- ручной backfill дивидендов для missing total-months.

Главная идея:

- observed monthly values живут в `fact_metric_observation`;
- selected calculated P&L rollups / formula nodes тоже можно materialize обратно в `fact_metric_observation`, но только с явной маркировкой `value_origin = calculated_rollup`;
- сквозная monthly history собирается через views;
- derived `total` для continuity не пишем как новый raw source;
- operational `total` должен строиться только как сумма business units одного и того же semantic level.

## Canonical Rules

Это основной набор правил для monthly P&L runtime layer:

- leaf-слой собираем только по business units:
  - `general`
  - `b2c_moscow`
  - `b2c_spb`
  - `b2b`
  - `franchise`
- rollup / formula metrics materialize-им тоже только по business units;
- `total` не считаем отдельным leaf- или rollup-source внутри этого контура;
- `total` всегда строим как сумму business units;
- `general` — это не `total`, но это полноценный bucket нераспределённых значений, и он обязательно входит в сумму `total`;
- observed `business_unit = total` из внешнего источника можно хранить как reference / trace, но не использовать как основной runtime `total`, если цель слоя — единая согласованная сумма BU.

## Активные monthly sources

Сейчас активными monthly P&L sources считаем только:

- `google_sheets_monthly_economics_historical`
- `planfact`
- `manual_dividends_total_history`
- `monthly_pnl_calculated_rollup`

Legacy monthly CSV больше не участвует в active monthly history.

## Что даёт каждый источник

### 1. Historical Google Sheet

Источник:

- Google Sheet `ЭКОНОМИКА (P&L) - для базы`
- `sheet_id = 19Ssy4Esp0vG_7yIHA8mNpfuzjvko12TdQEklEPFxfC0`
- `gid = 582113259`
- supplemental bridge from the same spreadsheet:
  - sheet `ЭКОНОМИКА (P&L) - Новый прототип`
  - `gid = 277036993`
  - currently used only to backfill missing historical months `2025-04 .. 2025-06`

Роль:

- базовая длинная historical monthly history;
- observed monthly facts по business units и отдельным historical rows;
- trace до исходных ячеек хранится в payload.

Текущее active-state решение:

- основной `source_system = google_sheets_monthly_economics_historical` уже заменён
  на leaf-only historical import;
- то есть в основном historical fact-layer теперь лежат lower-level строки,
  а не старая mixed subtotal/history схема;
- approved additive manual corrections тоже пишем прямо в
  `google_sheets_monthly_economics_historical` через
  `source_record_key = manual_historical_adjustment:*`, чтобы historical
  leaf-layer оставался единым;
- старый audit-source `google_sheets_monthly_economics_historical_leaf_only`
  больше не нужен в raw facts и удаляется из рабочего контура.

Ключевые правила:

- mapping-файл допускает неуникальные source rows;
- если несколько source rows маппятся в один canonical bucket, действует `merge_rule = sum`;
- `general` в этом источнике не равен `total`, это отдельный observed bucket;
- `Прибыль для основателей` маппится как observed `Net profit` c `business_unit = total`;
- строка `210` `Общая прибыль` в основном historical sheet принудительно `exclude`;
- строки `248`, `250`, `254` (`Театр Москва`, `Театр Петербург`, `Корпоратив`) в основном historical sheet принудительно `exclude`, потому что это процентные helper-строки, а не `Net profit`;
- строка `79` `Итого переменные расходы` в основном historical sheet хранится как observed `Variable costs` c `business_unit = total`, не `general`;
- строка `119` `Итого постоянные расходы` в основном historical sheet хранится как observed `Fixed costs` c `business_unit = total`, не `general`;
- `Вывод для ПСН (депозитный счет)` в historical mapping считается `Dividends`.
- для historical marketing subtotal строка `Итого расходы на маркетинг` хранится как observed `Marketing costs` с `channel_name = total`;
- в старом historical листе строка `102` трактуется как marketing subtotal для `business_unit = b2c_moscow`;
- в старом historical листе строка `183` трактуется как marketing subtotal для `business_unit = b2c_spb`;
- в supplemental sheet `ЭКОНОМИКА (P&L) - Новый прототип` аналогичная строка subtotal по маркетингу тоже хранится как `Marketing costs` с `channel_name = total`.
- `Директорский процент` хранится как observed `Cost article - Директорский процент` с `business_unit = total`:
  - old sheet: row `211`
  - `Новый прототип`: row `223` if label is `Директорский процент`, and row `229` if label is `Итого, процент директора`

Ключевые файлы:

- [historical_sheet_canonical_metric_mapping.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/historical_sheet_canonical_metric_mapping.csv)
- [build_historical_sheet_canonical_mapping.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/build_historical_sheet_canonical_mapping.py)
- [import_historical_monthly_economics_sheet_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_historical_monthly_economics_sheet_to_fact.py)
- [import_historical_monthly_economics_prototype_extension_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_historical_monthly_economics_prototype_extension_to_fact.py)

### 2. PlanFact by business unit

Источник:

- observed monthly P&L workbook'и по:
  - `general`
  - `b2c_moscow`
  - `b2c_spb`
  - `b2b`
  - `franchise`

Роль:

- observed monthly P&L facts для позднего периода;
- observed totals и leaf rows живут одновременно;
- rollup строки не считаем calculated только потому, что они subtotal внутри PlanFact.

Ключевые правила:

- `Revenue` остаётся одной canonical metric;
- detail rows не размножаем в новые revenue-metric names;
- marketing child rows могут различаться по `channel_name`;
- `Расходы на B2B (продакшн)` сводим в `Show production costs`.

Ключевые файлы:

- [planfact_monthly_pnl_report_mapping.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/planfact_monthly_pnl_report_mapping.py)
- [import_planfact_monthly_pnl_report_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_planfact_monthly_pnl_report_to_fact.py)
- [planfact_monthly_pnl_fact_ingestion.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/planfact_monthly_pnl_fact_ingestion.md)

### 3. PlanFact observed total

Источник:

- отдельный workbook `total`

Роль:

- observed consolidated `business_unit = total`;
- это observed fact, а не calculated total.

Правило:

- observed total из PlanFact храним как reference / trace source;
- основной runtime `total` для unified monthly layer должен совпадать с суммой BU, включая `general`.

### 4. Manual dividends total history

Источник:

- curated manual list дивидендов по total-months

Роль:

- заполняет только те total-months по `Dividends`, где в unified monthly total history до этого не было значения.

Правило:

- это не полный самостоятельный P&L source;
- это narrow patch source только для `Dividends | business_unit = total`;
- он не должен менять правило, что основной runtime `total` строится как сумма BU.

Ключевые файлы:

- [manual_dividends_total_history.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/manual_dividends_total_history.csv)
- [import_manual_dividends_total_history_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_manual_dividends_total_history_to_fact.py)
- [manual_dividends_total_history.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/manual_dividends_total_history.md)

## `general` vs `total`

Это разные сущности.

- `general`
  - observed shared / unallocated / common bucket источника;
  - не считать автоматически суммой всех BU;
  - включать в derived `total` как часть общей суммы business units.

- `total`
  - derived сумма всех business units одного и того же слоя;
  - включает `general` + named BU.

Нельзя автоматически трактовать `general` как `total`.
Нельзя строить runtime `total` отдельно от суммы BU.

## Как собирается unified monthly history

Сборка зафиксирована в:

- [rebuild_monthly_pnl_history_views.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/rebuild_monthly_pnl_history_views.py)

### View 1. `monthly_metric_fact_trace`

Это trace-view всех monthly observations как есть.

В нём зафиксирован source priority:

- `planfact` -> `200`
- `manual_dividends_total_history` -> `150`
- `historical_leaf_rollup_backfill` -> `110`
- `google_sheets_monthly_economics_historical` -> `100`

### View 2. `monthly_metric_source_bucket`

Это aggregation внутри одного `source_system`.

Зачем нужен:

- если внутри одного source несколько строк маппятся в один canonical bucket, сначала их суммируем;
- только после этого сравниваем source against source.

Это критично для P&L hierarchy, где несколько observed строк могут сознательно сливаться в одну canonical metric.

### View 3. `monthly_pnl_active_history`

Это рабочая monthly history без synthetic total.

Правило выбора:

- среди active monthly sources берём один лучший source bucket по priority.

### View 4. `monthly_pnl_total_history`

Это total-layer.

Логика:

- всегда считаем derived sum по всем BU кроме `total`;
- в эту сумму обязательно входят:
  - `general`
  - `b2c_moscow`
  - `b2c_spb`
  - `b2b`
  - `franchise`
- observed `business_unit = total` можно хранить как reference / trace, но не использовать как основной runtime `total`.

То есть runtime `total` = сумма BU.

### View 5. `monthly_pnl_active_history_with_total`

Это финальный удобный unified layer:

- все обычные BU из `monthly_pnl_active_history`
- плюс `business_unit = total` из `monthly_pnl_total_history`

## Calculated rollup materialization

- Для unified monthly P&L selected rollup / formula metrics материализуем обратно в
  `fact_metric_observation` отдельным source `monthly_pnl_calculated_rollup`.
- Основной materialization step:
  [import_monthly_pnl_calculated_rollups_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_monthly_pnl_calculated_rollups_to_fact.py)
- Этот source активен в monthly history и имеет приоритет выше
  `google_sheets_monthly_economics_historical`, но ниже observed `planfact` и
  `manual_dividends_total_history`, поэтому observed monthly rows продолжают
  побеждать, а calculated rollups заполняют только gaps.
- Materialization опирается на canonical hierarchy:
  [pnl_structure_mapping_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/pnl_structure_mapping_canonical.csv)
- Он materialize только те canonical metrics, которые в P&L structure помечены как
  `observed_rollup` или `calculated_formula`, и не дублирует raw `Revenue`.
- Для historical compatibility legacy source
  `historical_leaf_rollup_backfill` всё ещё может встречаться в базе как узкий
  старый backfill `Variable costs` / `Fixed costs`, но новым основным runtime
  контуром его больше не считаем.

## Alternative leaf-only contour

- Для отдельной проверки historical P&L без subtotal-шумов собран альтернативный
  leaf-only contour.
- В этот contour попадают только lower-level P&L статьи из historical Google Sheets:
  - без `general`
  - без observed `total`
  - без subtotal-строк
- Поверх него собраны views:
  - `monthly_pnl_leaf_only_history`
  - `monthly_pnl_leaf_only_total_history`
  - `monthly_pnl_leaf_only_history_with_total`
- Historical часть этого contour теперь читается из основного
  `google_sheets_monthly_economics_historical`, без отдельного
  raw-source-дубля.
- Начиная с мая 2026 эта же `leaf-only` history дополнительно включает
  фильтрованный lower-level контур из PlanFact как `source_system = planfact_leaf_only`.
- Для PlanFact в `leaf-only` включаем:
  - lower-level P&L строки по `general`, `b2c_moscow`, `b2c_spb`, `b2b`, `franchise`
  - `Revenue` только из верхней строки `Выручка`
- Для PlanFact в `leaf-only` исключаем subtotal/result rows вроде:
  - `Переменные расходы`
  - `Постоянные расходы`
  - `Инвестиции`
  - `Маркетинг и реклама`
  - `Прочие расходы`
  - `Операционная прибыль`
  - `Прочие доходы`
  - `EBITDA`
  - `EBIT`
  - `EBT`
  - `Чистая прибыль (убыток)`
  - `Дивиденды`
  - `Нераспределенная прибыль`
- Поверх `monthly_pnl_leaf_only_history` отдельно строится recursive rollup-контур по
  [pnl_structure_mapping_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/pnl_structure_mapping_canonical.csv):
  - `monthly_pnl_leaf_only_rollup_history`
  - `monthly_pnl_leaf_only_rollup_total_history`
  - `monthly_pnl_leaf_only_rollup_history_with_total`
- С `2026-05-25` в active P&L structure:
  - `Services and setup costs` больше не включает
    `Cost article - КОМИССИИ БАНКОВ` и `Cost article - Отсмотр видео`
  - `Cost article - КОМИССИИ БАНКОВ` теперь идёт в `Variable costs`
  - `Cost article - Отсмотр видео` теперь идёт в `Variable costs`
- Начиная с `2026-05-24` в этом же leaf-only rollup-контуре есть явный formula-node:
  - `Прибыль` = canonical `Operating profit`
  - считается как `Revenue - Variable costs - Fixed costs`
  - считается отдельным derived SQL-слоем, а не обычным parent-child rollup
- Для derived `total` в leaf-only monthly contour складываем:
  - `general`
  - `b2c_moscow`
  - `b2c_spb`
  - `b2b`
  - `franchise`
- Важно:
  - `channel_name` сохраняется только на leaf-строках вроде `Marketing costs`
    по каналам;
  - при подъёме в parent-rollup (`Variable costs`, `Fixed costs`, выше по дереву)
    канал не наследуется и обнуляется;
  - это нужно, чтобы channel не менял общую P&L-атрибуцию parent-метрики и не
    создавал параллельные parent-ряды.

## Что важно не забыть

- observed subtotal из P&L = `fact`, даже если у него есть children;
- derived percentage / margin = `calculated`;
- P&L hierarchy живёт отдельным metadata-layer:
  - [pnl_structure_mapping_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/pnl_structure_mapping_canonical.csv)
- total continuity для historical layer строится через views как сумма BU, включая `general`, а не через отдельный runtime total-source;
- для historical total-check рабочая бизнес-формула сейчас такая:
  - `Net profit total = Revenue - Fixed costs - Variable costs - Marketing costs(channel=total)`;
- historical total bridge нужно читать по периодам:
  - для раннего historical блока `2020-01 .. 2020-09` рабочая проверка шла с `Marketing costs(channel=total)`, `Investment costs` и затем `Cost article - Директорский процент` по мере появления;
  - для периода `2020-11 .. 2021-12` live-проверка показала, что historical `Net profit` лучше всего сходится по формуле:
    - `Net profit = Revenue - Variable costs - Fixed costs - Marketing costs(channel=total) - Investment costs - Cost article - Директорский процент + Other income`
  - на этом участке `Tax` не нужно вычитать отдельно: он, похоже, уже встроен в historical `Net profit`;
  - начиная с `2022-01` начинается новый historical regime, где даже эта формула снова даёт большие дельты и требует отдельного разбора.
- если появляется новый monthly source, сначала надо решить:
  - observed это источник или patch;
  - для какого scope он authoritative;
  - должен ли он участвовать в source priority.
