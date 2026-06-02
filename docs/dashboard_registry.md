# Dashboard Registry

## Purpose

Реестр нужен, чтобы у каждого dashboard в проекте был понятный operational след:

- для кого он сделан;
- где он живёт;
- на каком слое данных сидит;
- что было переиспользовано;
- была ли добавлена новая metric semantic в `calculated layer` или только serving `view`.

Метабейз сам по себе не должен быть единственным источником этой информации.

## Files

- data file: [`generated/dashboard_registry.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/dashboard_registry.csv)
- policy: [`docs/dashboard_creation_policy.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/dashboard_creation_policy.md)

## Update rule

Обновлять реестр нужно всегда, когда происходит одно из событий:

- создаётся новый dashboard;
- существующий dashboard существенно меняется;
- под dashboard создаётся новый `view`;
- под dashboard добавляются новые `calculated` метрики;
- dashboard переводится в `planned`, `active`, `deprecated` или `prototype`.

## Column guide

- `dashboard_key` — стабильный короткий идентификатор
- `dashboard_name` — отображаемое имя
- `tool` — например `metabase`
- `dashboard_id` — ID объекта в BI, если уже существует
- `status` — `planned`, `prototype`, `active`, `deprecated`
- `audience` — для кого dashboard сделан
- `access_scope` — ожидаемая видимость или группа доступа
- `owner` — кто бизнес-владелец или основной запросивший
- `collection_or_folder` — куда публикуется dashboard
- `primary_serving_layer` — базовый источник выдачи: `fact`, `calculated`, `view`, `mixed`
- `reusable_views` — какие view были переиспользованы
- `reusable_scripts` — какие scripts были переиспользованы
- `metric_modeling_decision` — `view_only`, `calculated_added`, `reused_existing`, `mixed`
- `notes` — краткое объяснение решения
- `source_doc` — документ или note с деталями
- `last_reviewed_on` — дата последней актуализации записи
