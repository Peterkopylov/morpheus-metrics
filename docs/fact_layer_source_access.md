# Fact Layer Source Access

Операционная карта источников для нового факт-слоя.

Задача файла:

- держать в одном месте все подтверждённые способы добраться до источников данных;
- быстро понимать, что уже готово для ingestion-скриптов;
- не хранить секреты в markdown, а хранить только пути, где они должны лежать.

## Принцип

Для каждого источника фиксируем:

- `access_state` — насколько он готов для локального скрипта;
- `secret_location` — где должен лежать токен / ключ / конфиг;
- `validated_access` — что уже проверено живым запросом;
- `best_use_in_fact_layer` — для каких метрик это хороший source of truth;
- `known_gaps` — что мешает автоматической загрузке прямо сейчас.

## Access State Legend

- `ready_local` — можно использовать из локального проекта прямо сейчас.
- `ready_no_secret` — секрет не нужен, можно ходить сразу.
- `ready_doc_only` — доступ подтверждён, но локальный секрет/файл сейчас не лежит в проекте.
- `indirect_source` — источник не дёргаем напрямую как API, а читаем через уже загруженные таблицы / файлы.

## Source Registry

| Source | Access state | Secret / config location | Validated access | Best use in fact layer | Known gaps |
| --- | --- | --- | --- | --- | --- |
| `analytics Postgres` | `ready_local` | DSN в [`README.md`](/Users/Peter/Documents/Morpheus%20Metrics/README.md) | удалённая БД `analytics` на `134.122.83.160:5432` отвечает | целевое хранилище факт-слоя, existing weekly layer, PlanFact layer | локального `psql` нет, для скриптов лучше сразу использовать `psycopg2` |
| `legacy weekly Google Sheets -> fact_metrics` | `indirect_source` | регулярные source sheets: [Moscow sheet](https://docs.google.com/spreadsheets/d/1gHuxPxZntVLAxhxY9yFuBRhvozm45r2LcnvId83CY-s/edit?gid=1411303700#gid=1411303700), [SPB sheet](https://docs.google.com/spreadsheets/d/1q71g1XD5fwTMo7xbEe1fGvXVTRyPfEswCPxyjVTEZi0/edit?gid=1411303700#gid=1411303700); canonical service account: `morpheus@appointments-1084.iam.gserviceaccount.com` | `fact_metrics` заполнена и содержит weekly history | backfill и reference-layer со старой weekly логикой | именно этот service account должен иметь share на боевые таблицы; если прямой доступ в текущей сессии не работает, сначала проверяем share на него |
| `ERP API` | `ready_no_secret` | не нужен | `POST /tickets/by-sell`, `POST /shows/get` уже многократно проверены | shows / cancellations / visitors / survey / salary / weekly ticket sales | для weekly ticket-sales questions (`orders/tickets/revenue` by show/agent) это теперь primary source; `status = 0` трактуем как отмену |
| `Yandex Metrica` | `ready_local` | [`.env.yandex_metrica`](/Users/Peter/Documents/Morpheus%20Metrics/.env.yandex_metrica), [`.env.yandex_metrica_spb`](/Users/Peter/Documents/Morpheus%20Metrics/.env.yandex_metrica_spb) | counters list, stat API, direct traffic / geo / show pageviews уже проверены; для SPB кабинета сохранён отдельный access token | website visits, visits by channel, visits by show pages, geo of ad traffic, performance marketing revenue | сейчас токены могут совпадать с Direct-контуром, но храним их отдельно, чтобы не смешивать источники и кабинеты |
| `Yandex Direct` | `ready_local` | [`.env.yandex_direct`](/Users/Peter/Documents/Morpheus%20Metrics/.env.yandex_direct), [`.env.yandex_direct_spb`](/Users/Peter/Documents/Morpheus%20Metrics/.env.yandex_direct_spb) | `Reports API` отвечает `HTTP 200`, живые кампании видны; отдельный SPB кабинет тоже подтверждён через `Reports API` | marketing costs, clicks, impressions, campaign activity | campaign geography и site attribution живут в другом контуре, не путать с Метрикой; revenue-поля Direct не считаем source of truth для доходов перформанса |
| `amoCRM` | `ready_local` | [`.env.amocrm`](/Users/Peter/Documents/Morpheus%20Metrics/.env.amocrm) | account, leads, pipelines, filters уже проверялись живыми запросами; weekly importer уже добавлен и переключает B2B weekly funnel по исторической дате: до `2025-05-01` использует `Корпоративы` (`pipeline_id = 8783794`), начиная с `2025-05-01` — `Корпоративы 2.0` (`pipeline_id = 10869194`) | B2B leads, funnel metrics, creative meetings, pipeline conversions | long-lived token сохранён локально; weekly importer маппит funnel по названиям статусов выбранной воронки и трактует `204 No Content` как пустой результат, а не как падение |
| `Airtable` | `ready_local` | [`.env.airtable`](/Users/Peter/Documents/Morpheus%20Metrics/.env.airtable) | база `appc2HrGFaUHLj6tO` и её schema читаются | B2B project finance / budgets / project-level revenue and costs | это не финальный analytics layer, а операционный источник; лучше тянуть нужные таблицы в raw-layer |
| `PlanFact` | `indirect_source` | не нужен API-секрет; источник приходит через xlsx import | `planfact_cashflow_entries`, `planfact_cashflow_analytic`, `planfact_pnl_test` уже живые | finance revenue, account balance, P&L, cost articles | это не live API; новые данные появляются только после импорта выписки |
| `Yandex Tickets API` | `ready_local` | [`.env.yandex_tickets`](/Users/Peter/Documents/Morpheus%20Metrics/.env.yandex_tickets), [`.env.yandex_tickets_spb`](/Users/Peter/Documents/Morpheus%20Metrics/.env.yandex_tickets_spb) | московский и петербургский контуры сохранены локально | reference / reconciliation for ticket sales if needed | больше не primary source для weekly fact ingestion; оставляем как optional reference |
| `Metabase API` | `ready_local` | [`.env.metabase`](/Users/Peter/Documents/Morpheus%20Metrics/.env.metabase) | dashboards и cards уже правились через API | не источник фактов, а слой публикации и проверки витрин | не использовать как source of truth для метрик |

Дополнительные operational notes:

- схема подключения к кабинетам и разделение `main` / `spb` зафиксированы в [yandex_direct.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/external_apis/yandex_direct.md)
- для факт-слоя weekly/monthly `Marketing costs` считаем primary-source из **Yandex Direct**, а не из Metrica direct-costs срезов
- для факт-слоя weekly/monthly `Performance marketing revenue` считаем primary-source из **Yandex Metrica**, а не из `Yandex Direct Reports API`
- technical compatibility: metric key `yandex_direct_conversion_revenue` сохранён, но теперь означает canonical metric name `Performance marketing revenue`
- Metrica query для performance revenue: `ym:s:favoriteGoalsConvertedRUBRevenue` с `attribution=automatic`, dimensions `ym:s:<attribution>TrafficSource,ym:s:<attribution>AdvEngine`, включаем только `ad / ya_direct` и `ad / ya_undefined`
- weekly ingestion сайта из Метрики зафиксирован в [yandex_metrica_weekly_fact_ingestion.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/yandex_metrica_weekly_fact_ingestion.md)
- `manual_table` остаётся обязательным полным numeric reference-layer: все численные значения из weekly manual tables нужно импортировать независимо от того, есть ли для этих же бизнес-сущностей другой primary source
- для `manual_table` канонический источник полноты — это live Google Sheets, открытые через service account `morpheus@appointments-1084.iam.gserviceaccount.com`
- `fact_metrics` для `manual_table` считаем только staging / snapshot-слоем; если число видно в live sheet, но не дошло до `fact_metrics`, это parser/staging gap, а не причина не импортировать метрику
- не тянем из `manual_table` только то, что явно помечено как calculated / deferred-to-calculated
- для weekly B2C agent sales в `manual_table` partner revenue rows интерпретируем как `net of commission`:
  - `кассир` и `яндекс афиша` = `gross * 0.90`
  - `тикетленд` = `gross * 0.85`
  - `афиша ру` = `gross * 0.93`
- operationally weekly manual importer теперь умеет добирать missing numeric values напрямую из live Google Sheets через service account; reconciled artifact в `generated/manual_table_live_transfer_status_<week>_reconciled.csv` остаётся полезным debug/reference слоем, но больше не нужен как обязательная ручная подготовка каждой недели
- monthly assembly logic для объединения historical sheet, PlanFact, observed total и manual dividends backfill зафиксирована в:
  - [monthly_metric_history_assembly.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/monthly_metric_history_assembly.md)

## Source-by-Source Notes

### 1. analytics Postgres

Canonical target database:

- host: `134.122.83.160`
- port: `5432`
- db: `analytics`
- user: `admin`

Рабочий DSN уже зафиксирован в:

- [README.md](/Users/Peter/Documents/Morpheus%20Metrics/README.md)

Практика:

- для новых ingestion-скриптов использовать `psycopg2`;
- не рассчитывать на локальный `psql`, потому что он сейчас не установлен.

### Legacy reference tables in `analytics`

Это те таблицы и view, которые продолжают быть полезны как reference-layer, даже
если новый факт-слой будет жить отдельно.

#### Weekly legacy layer

Регулярные source sheets, из которых weekly ingestion продолжает забирать данные:

- Москва:
  - [Google Sheet](https://docs.google.com/spreadsheets/d/1gHuxPxZntVLAxhxY9yFuBRhvozm45r2LcnvId83CY-s/edit?gid=1411303700#gid=1411303700)
- СПб:
  - [Google Sheet](https://docs.google.com/spreadsheets/d/1q71g1XD5fwTMo7xbEe1fGvXVTRyPfEswCPxyjVTEZi0/edit?gid=1411303700#gid=1411303700)

Это именно те регулярные таблицы, которые weekly-ingestion складывает в `analytics`.

- `fact_metrics`
  - основной reference-слой старых weekly-метрик;
  - здесь лежит исторический weekly backfill по городам и группам метрик.

- `raw_weekly_metrics`
  - сырой импорт weekly-таблиц;
  - полезен, если нужно перепроверить, как метрика выглядела до нормализации.

- `metric_aliases`
  - справочник нормализации старых metric labels;
  - полезен для backfill и legacy-to-canonical mapping.

- `unmapped_metrics`
  - список legacy-метрик, которые ingestion не смог нормально сопоставить;
  - useful as a guardrail при миграции в новый каталог.

- `weekly_import_runs`
  - лог weekly-ingestion запусков;
  - нужен для аудита и понимания, когда и чем были загружены weekly-данные.

- `dashboard_refresh_runs`
  - лог пересборки weekly dashboard / views;
  - не источник фактов, но полезный operational reference.

#### Weekly reference views

- `weekly_metrics_yoy_series_6w`
- `weekly_metrics_yoy_latest_week`
- `weekly_metrics_latest_comparison`
- `weekly_metrics_trace`
- `weekly_dashboard_status`

Эти view не являются source of truth для нового факт-слоя, но помогают:

- быстро сверять старую weekly-логику;
- проверять, как legacy-метрики сейчас подаются в аналитике;
- делать sanity-check новых загрузок против старых витрин.

#### Manual weekly layer

- `manual_metric_entries`
  - ручной слой поверх weekly-логики;
  - пока может быть пустым, но его надо помнить как reference на случай ручных метрик.

- `app_metric_search`
  - объединяющий search-view по `fact_metrics` и `manual_metric_entries`;
  - полезен для быстрых сверок, но не как target fact layer.

#### PlanFact reference layer

- `planfact_cashflow_entries`
  - сырой импорт PlanFact-выписок.

- `planfact_cashflow_analytic`
  - нормализованный cashflow view.

- `planfact_pnl_test`
  - текущий reference P&L view.

Если новый факт-слой будет брать finance-метрики из PlanFact, именно эти объекты
сейчас являются reference-точкой внутри `analytics`.

#### Legacy monthly P&L reference layer

  - нормализованный one-time import старого wide CSV:
    - `/Users/Peter/Downloads/Месяц_статистика и цели - ЭКОНОМИКА (P&L) - для базы.csv`
  - хранит monthly history в long format:
    - `business_unit_raw`
    - `business_unit_key`
    - `metric_name`
    - `period_start`
    - `value_raw`
    - `value_numeric`
    - `value_type`

Практически это useful для:

- длинного historical reference до появления нового факт-слоя;
- сверок с legacy monthly P&L логикой;
- controlled backfill месячных метрик, если понадобится перенос в canonical layer.

Отдельная рабочая карточка по мосту из этого legacy source в новый факт-слой:


### 2. ERP API

Рабочие endpoints:

- `POST https://morpheus-server.ru:45010/tickets/by-sell` — Москва
- `POST https://morpheus-server.ru:45011/tickets/by-sell` — СПб
- `POST https://morpheus-server.ru:45010/shows/get`
- `POST https://morpheus-server.ru:45011/shows/get`

Что уже знаем:

- `tickets/by-sell` даёт ticket-level продажи с `order_id`, `order_created`, `seance_id`, `agent_id`, `total`;
- `shows/get` даёт `ID`, `event_title`, `show_start`, `guests`, `cancelled`, `tickets_count`, `tickets_cert`;
- рабочий join:
  - `tickets.seance_id = shows.ID`

Рабочие заметки:

- [ERP_API_TO_WEEKLY_METRICS_NOTES.md](/Users/Peter/Documents/Morpheus%20Metrics/ERP_API_TO_WEEKLY_METRICS_NOTES.md)
- [ERP_AGENT_ID_HYPOTHESES.md](/Users/Peter/Documents/Morpheus%20Metrics/ERP_AGENT_ID_HYPOTHESES.md)
- [erp_weekly_fact_ingestion.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/erp_weekly_fact_ingestion.md)
- [erp_endpoint_metric_mapping.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/erp_endpoint_metric_mapping.md)
- [erp_salary_variable_logic.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/erp_salary_variable_logic.md)
- [erp_survey_satisfaction_logic.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/erp_survey_satisfaction_logic.md)
- [erp_site_widget_comparison.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/erp_site_widget_comparison.md)
- [erp prod.postman_collection.json](/Users/Peter/Documents/Morpheus%20Metrics/postman/erp/erp%20prod.postman_collection.json)

Текущая архитектурная роль ERP для билетных продаж:

- не primary source;
- использовать как `secondary / reference` для:
  - быстрых operational checks;
  - временного SPB fallback;
  - reconciliation против Yandex Tickets.

### 3. Yandex Metrica

Основные счётчики для сайта:

- Москва: `48759785` — `morpheus-show.ru`
- СПб: `97365452` — `spb.morpheus-show.ru`

Уже подтверждённые задачи:

- weekly site visits;
- visits by channel;
- direct-only visits;
- geography of ad traffic;
- show pageviews по URL-path filters;
- performance marketing revenue from favorite-goals converted RUB revenue.

Правило для доходов перформанса:

- источник: `Yandex Metrica Stat API`;
- metric: `ym:s:favoriteGoalsConvertedRUBRevenue`;
- attribution: `automatic`;
- dimensions: `ym:s:<attribution>TrafficSource`, `ym:s:<attribution>AdvEngine`;
- включаем engine ids `ya_direct` и `ya_undefined`;
- контроль за май `2026`: Москва `420 320 + 36 700 = 457 020 р.`, СПб `278 000 + 26 500 = 304 500 р.`.

Рабочая документация:

- [docs/external_apis/yandex_metrica.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/external_apis/yandex_metrica.md)

### 4. Yandex Direct

Подтверждённые use cases:

- full spend;
- clicks;
- impressions;
- live campaigns via `Reports API`;
- geo of impressions / clicks в direct-контуре.

Не используем как source of truth:

- доходы перформанс-маркетинга;
- `Revenue` и goal-specific revenue поля из Direct Reports API не воспроизводят реальные суммы заказов из Метрики достаточно надёжно для факт-слоя.

Практика:

- для списка реально живых кампаний использовать `Reports API`;
- `Campaigns.get` использовать как вспомогательный endpoint для структуры и `CounterIds`.

Рабочая документация:

- [docs/external_apis/yandex_direct.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/external_apis/yandex_direct.md)

### 5. amoCRM

Что уже проверено исторически:

- account info;
- leads;
- pipelines;
- filtered pipeline queries;
- helper script для created_at ranges.

Практика для нового скрипта:

- перед началом работы проверить, что локально существует `.env.amocrm`;
- если файла нет, считать источник `temporarily blocked locally`, даже если доступ в целом уже подтверждён.

Рабочая документация:

- [docs/external_apis/amocrm.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/external_apis/amocrm.md)

### 6. Airtable

Подтверждённая база:

- `appc2HrGFaUHLj6tO` — `📂 Сметочная`

Практика:

- использовать как project-finance и ops source;
- перед production-ingestion лучше сначала складывать raw copies в Postgres.

Рабочая документация:

- [docs/external_apis/airtable.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/external_apis/airtable.md)

### 7. PlanFact

Это не API-источник, а импортируемый finance-layer.

Практика:

- source-файлы импортируются в `planfact_cashflow_entries`;
- аналитика строится поверх:
  - `planfact_cashflow_analytic`
  - `planfact_pnl_test`
- monthly P&L fact-layer дополнительно загружается из отдельных workbook’ов по business unit:
  - `general`
  - `b2c_moscow`
  - `b2c_spb`
  - `b2b`
  - `franchise`

Когда использовать:

- finance revenue;
- account balance;
- article-based costs;
- P&L-derived measures.

Отдельное правило:

- в monthly P&L `Revenue` остаётся одной canonical metric;
- детализация revenue-строк сохраняется в payload, а не через новые metric names.

### 8. Yandex Tickets

Полезен как альтернативный order-level источник по билетам и спектаклям, особенно для Москвы.

Подтверждённый workflow:

- `crm.order.list` -> `event_id`
- `crm.report.event` -> `event_name`

Рабочая документация:

- [docs/external_apis/yandex_tickets.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/external_apis/yandex_tickets.md)
- [yandex_tickets_fact_layer_decision.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/yandex_tickets_fact_layer_decision.md)

Новый подтверждённый спектакль по состоянию на `2026-05-16`:

- Москва: `Поезд, Чехов, два орла`
  - в Яндекс.Билетах виден как `event_name`
  - в ERP виден в `POST /shows/get`
  - в Метрике виден по path `/poezd-chehov-dva-orla`

Идеология для факт-слоя:

- ticket sales (`Revenue`, `Number of tickets`, `Number of orders`)
  в разрезах `show` и `agent`
  должны по умолчанию идти через **Yandex Tickets**;
- ERP для этих метрик — только secondary source / reconciliation / fallback.

## Recommended Script Order

Если писать новый ingestion-скрипт под факт-слой, логичный порядок такой:

1. `analytics Postgres` — target layer
2. `ERP API` — B2C tickets / orders / shows / visitors
3. `Yandex Metrica` — site visits / channel visits / show pages / performance marketing revenue
4. `Yandex Direct` — marketing costs / clicks / impressions
5. `amoCRM` — B2B and franchise leads
6. `Airtable` — B2B project finance
7. `PlanFact` — finance overlays / monthly facts
8. `legacy fact_metrics` — only for backfill and controlled bridging

## Practical Ready-to-Use Checklist

Перед следующим скриптом достаточно проверить:

- есть ли [`.env.yandex_metrica`](/Users/Peter/Documents/Morpheus%20Metrics/.env.yandex_metrica)
- есть ли [`.env.airtable`](/Users/Peter/Documents/Morpheus%20Metrics/.env.airtable)
- есть ли локальный `.env.amocrm`
- доступна ли удалённая БД `analytics`
- нужен ли нам live `ERP` / `Metrica` / `Direct`, или достаточно backfill из `fact_metrics`

Если все четыре пункта выше зелёные, можно писать полноценный ingestion без поиска контекста по проекту.
