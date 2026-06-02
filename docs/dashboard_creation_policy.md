# Dashboard Creation Policy

## Goal

Новый dashboard не должен становиться одноразовой витриной с логикой, размазанной между Metabase, ad hoc SQL и неучтёнными метриками.

Политика ниже нужна, чтобы каждый новый dashboard проходил через одну и ту же развилку:

- кто должен иметь доступ;
- можно ли переиспользовать существующий serving layer;
- логика должна жить в `view` или в `calculated layer`;
- где это решение зафиксировано.

## Обязательные вопросы

Перед созданием dashboard нужно ответить на вопросы:

1. Кто целевая аудитория dashboard?
2. Доступ должен быть широким или ограниченным?
3. Какие метрики или KPI в нём новые относительно текущего warehouse?
4. Эти KPI reusable или нужны только для этой витрины?
5. Есть ли уже существующий `view`, script или dashboard, который можно переиспользовать?

## Правило выбора: `view` vs `calculated`

### Используем `calculated layer`, если:

- появляется новая бизнес-метрика, которая должна существовать вне одного dashboard;
- формула может использоваться в нескольких dashboards или карточках;
- метрика требует formula ownership, trace и понятного debug path;
- метрика должна пересчитываться вместе с обновлением `fact`-слоя;
- duplication в нескольких `view` иначе почти неизбежен.

### Используем `view`, если:

- логика нужна только для выдачи данных в конкретный dashboard;
- это mainly serving shape, а не новая metric semantic;
- нужны `latest vs previous`, `YoY`, wide-table reshape, labels, helper flags;
- warehouse уже содержит все нужные observed / calculated inputs.

### Эскалация при сомнении

Если неясно, где должна жить логика:

1. Проверить, можно ли переиспользовать существующий `view`.
2. Если нет, проверить, является ли логика reusable KPI.
3. Если это reusable KPI, делать `calculated`.
4. Если это dashboard-specific serving logic, делать `view`.

## Reuse-first правило

Перед созданием нового dashboard object или нового `view` нужно проверить:

- `sql/` на существующие serving views;
- `scripts/rebuild_*view*.py` на уже собираемые dashboard bases;
- `scripts/create_metabase_*dashboard*.py` на существующие builder scripts;
- `docs/` на operational notes и уже известные dashboard IDs;
- `generated/dashboard_registry.csv` на похожие витрины.

## Реестр обязателен

Каждый новый dashboard или существенное изменение существующего dashboard должно обновлять:

- [`docs/dashboard_registry.md`](/Users/Peter/Documents/Morpheus%20Metrics/docs/dashboard_registry.md)
- [`generated/dashboard_registry.csv`](/Users/Peter/Documents/Morpheus%20Metrics/generated/dashboard_registry.csv)

Минимально нужно зафиксировать:

- `dashboard_key`
- `dashboard_name`
- `tool`
- `dashboard_id`
- `status`
- `audience`
- `access_scope`
- `owner`
- `primary_serving_layer`
- `reusable_views`
- `reusable_scripts`
- `metric_modeling_decision`
- `notes`

## Current repository examples

- `weekly_fact_metrics_dashboard_base` — reusable base view для weekly fact dashboards
- `weekly_fact_metrics_latest_comparison` — serving view для comparison dashboard
- `create_metabase_weekly_metrics_dashboard.py` — scripted dashboard creation path
- `create_metabase_planfact_dashboard.py` — scripted dashboard creation path для P&L
