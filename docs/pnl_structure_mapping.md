# P&L Structure Mapping

Этот файл описывает, как новая P&L-структура соотносится с каноническими метриками.

## Главный принцип

P&L-иерархия — это **не отдельный второй каталог метрик**. В основном это metadata-слой для observed и rollup-узлов, но в нём могут жить и отдельные явно оговорённые formula-nodes, если они нужны как часть управленческой структуры P&L.

Правильная модель такая:

- `canonical metric` = общая сущность системы
- `P&L node` = место этой сущности в финансовой иерархии

То есть:

- канонические метрики остаются плоским общим словарём
- P&L-структура хранится как отдельный metadata-layer
- observed subtotal строки из P&L остаются в справочнике как узлы иерархии; в текущем `PlanFact` raw-import контуре в `fact` грузим top-line `Выручка` и leaf-строки, а subtotal/result узлы собираем в rollup/views
- `calculated` обычно используем только для процентов, рентабельностей и контрольных derived-метрик
- исключение: если в самой структуре P&L нужен derived node вроде `Прибыль = Выручка - Переменные расходы - Постоянные расходы`, такой узел можно держать в иерархии как `calculated_formula`, но считать отдельно от обычных rollup-связей

## Канонический файл

Основной mapping-файл:

- [pnl_structure_mapping_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/pnl_structure_mapping_canonical.csv)

Он отвечает на вопросы:

- какой P&L node есть в структуре
- у него есть дети или нет
- это leaf или observed rollup
- на какую canonical metric он ссылается
- используем existing metric или нужно создать новую

## Колонки файла

- `section`
  - верхний блок отчёта, например `Расходы`
- `business_unit`
  - если строка специфична для отдельного business unit
- `marketing_channel`
  - если строка — это channelized вариант `Marketing costs`
- `pnl_node_name`
  - название узла P&L
- `pnl_node_path`
  - полный путь узла в иерархии
- `parent_pnl_node_path`
  - родительский путь
- `level`
  - глубина узла
- `has_children`
  - есть ли дочерние строки
- `node_role`
  - `observed_rollup`, `leaf`, `calculated_formula`, реже `structural_group`
- `mapping_action`
  - `use_existing`, `create_new`, `review_needed`, `exclude`
- `canonical_metric`
  - выбранная canonical metric
- `canonical_metric_options`
  - если остались несколько вариантов и нужно решить
- `canonical_metric_kind`
  - `existing`, `candidate_new_rollup`, `candidate_new_metric`, `multiple_options`
- `source_note`
  - заметка из ручной разметки

## Как это использовать

### Если строка P&L уже есть в источнике как subtotal

Например:

- `Переменные`
- `Постоянные`
- `ФОТ - Переменные`
- `ФОТ - Постоянные`
- `Маркетинг и реклама`

Тогда:

- это observed P&L node в справочнике
- в текущем leaf-only PlanFact контуре такие строки не импортируются как raw fact, кроме явно разрешенных верхнеуровневых значений вроде `Выручка`
- для управленческого P&L они собираются системно через canonical hierarchy rollup/views

### Если строка — formula-node внутри самой структуры

Например:

- `Прибыль`

Тогда:

- она может быть частью P&L-иерархии
- но её нельзя вычислять как обычный parent-child rollup
- формула должна быть зафиксирована отдельно, например в `canonical_metric_options` или `source_note`

### Если строка — обычный leaf

Например:

- `Тех оснащение`
- `Уборка`
- `КОМИССИИ БАНКОВ`

Тогда:

- она обычно маппится на existing `Cost article - ...`
- либо создаётся новая article-level metric, если existing нет

Важно:

- положение leaf-статьи в дереве может меняться без смены самой canonical metric;
- если бизнес меняет финансовую классификацию статьи, сначала обновляем
  `pnl_structure_mapping_canonical.csv`, а уже потом rebuild monthly rollup;
- пример такого изменения:
  - с `2026-05-25` `КОМИССИИ БАНКОВ` и `Отсмотр видео` больше не считаются частью
    `Сервисы и их настройка`, а живут как отдельные статьи в `Переменных`.

### Если у строки несколько разумных вариантов

Тогда:

- строка остаётся `review_needed`
- варианты пишем в `canonical_metric_options`
- не делаем автоматический выбор молча

## Текущее состояние

По текущей разметке:

- existing mappings уже используются для большей части структуры
- новая апрельская структура `Переменные / Постоянные` зафиксирована как canonical hierarchy
- `ФОТ - Переменные` и `ФОТ - Постоянные` являются отдельными P&L nodes и маппятся на `Costs - Salary variable` / `Costs - Salary fixed`
- новые инвестиционные leaf-статьи `Новый спектакль` и `Ремонт в Малом зале` заведены как отдельные `Cost article - ...`
- расширенные маркетинговые строки маппятся в channelized `Marketing costs`: `Директ` -> `direct`, `PR и отзывы` -> `pr`, `Агентские` -> `partners`, `Общее` -> `general`
- часть узлов всё ещё помечена как `create_new`
- есть небольшой хвост `review_needed`

То есть слой уже пригоден как рабочий canonical P&L hierarchy mapping.
