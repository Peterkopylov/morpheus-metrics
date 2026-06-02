# Fact Metric Source Of Truth

Единый реестр вида:

- `метрика`
- `параметры`
- `где берём`
- `как считаем`

Главный артефакт:

- `/Users/Peter/Documents/Morpheus Metrics/legacy/generated/fact_metric_source_of_truth.csv`

Генератор:

- `/Users/Peter/Documents/Morpheus Metrics/legacy/scripts/generate_fact_metric_source_of_truth.py`

Важно:

- это рабочий source-of-truth artifact, из которого потом собирается canonical слой
- versioned seed-правила для него лежат в `legacy/generated/legacy_seed/`, а не в корне `generated/`
- для повседневного чтения системы в первую очередь смотри `generated/fact_metric_source_of_truth_canonical.csv`

## Колонки

- `metric_name`
- `business_unit`
- `show_scope`
- `partner_scope`
- `channel_scope`
- `frequency`
- `source_role`
- `source_system`
- `where_from`
- `how_counted`
- `reference_doc`
- `status_note`
- `source_row_ref`

## Как читать `source_role`

- `primary`
  - текущий source of truth для этого среза
- `secondary`
  - usable fallback / operational substitute, но не главный источник
- `reference`
  - сверочный или legacy-слой
- `pending`
  - источник задуман, но ещё не доведён до рабочего контура
- `needs_decision`
  - правило есть, но выбор источника ещё надо дожать

## Ключевые зафиксированные решения

- `manual_table`
  - это не “запасной кусок только там, где нет другого источника”
  - это обязательный полный numeric reference-layer
  - все численные значения из weekly manual tables должны забираться в факт-слой
  - наличие `primary` источника в другом сервисе не отменяет импорт из `manual_table`
  - live Google Sheets считаем каноническим источником полноты manual-слоя
  - `fact_metrics` — это staging / технический snapshot, а не источник правды о том, все ли числа мы увидели
  - если число есть в live sheet, но его нет в `fact_metrics`, это parser/staging gap, а не бизнес-решение
  - не тянем только то, что явно помечено как calculated / deferred-to-calculated

- `Revenue`, `Number of tickets`, `Number of orders` для B2C по `general / show / partner`
  - `primary = Yandex Tickets`
  - `secondary = ERP`
  - `reference = manual_table`
- `Revenue / Number of tickets / Number of orders` по `channel`
  - пока `primary = manual_table`
- `Marketing costs`
  - `primary = Yandex Direct`
  - `Yandex Metrica` держим только как analytical/reference срез
- `Website visits`
  - `primary = Yandex Metrica`
- `Number of shows`, `Number of shows cancelled`, `Number of show visitors`
  - `primary = ERP`
- `Costs - Salary variable`
  - B2C weekly -> `primary = ERP`
- survey-based weekly metrics
  - `primary = ERP / survey.satisfaction`
- monthly `Cost article -*`
  - `primary = PlanFact`

## Зачем это нужно

Этот файл нужен как operational truth-table перед тем, как:

- писать ingestion-скрипты
- спорить, откуда должна браться метрика
- разбирать расхождения между сервисами
- объяснять, почему одна и та же метрика может жить в нескольких источниках
