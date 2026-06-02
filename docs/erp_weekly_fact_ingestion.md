# ERP Weekly -> Fact Ingestion

Рабочая заметка по первому weekly-мосту из ERP в новый факт-слой.

Статус на `2026-05-02`.

Важно:

- weekly ticket sales now come from `ERP`, not `Yandex Tickets`;
- для weekly `Revenue`, `Number of tickets`, `Number of orders`
  по `general`, `show` и `partner/agent`
  primary source теперь `ERP /tickets/by-sell`.

## Источник

- source system:
  - `ERP API`
- reference collection:
  - [erp prod.postman_collection.json](/Users/Peter/Documents/Morpheus%20Metrics/postman/erp/erp%20prod.postman_collection.json)
- period tested:
  - `2026-04-20` -> `2026-04-26`
- endpoints:
  - `POST https://morpheus-server.ru:45010/tickets/by-sell`
  - `POST https://morpheus-server.ru:45011/tickets/by-sell`
  - `POST https://morpheus-server.ru:45010/shows/get`
  - `POST https://morpheus-server.ru:45011/shows/get`

## Target

- target fact table:
  - `fact_metric_observation`
- `source_system`:
  - `erp`
- `source_run_id`:
  - `erp_weekly_v1`

## Import script

- script:
  - [import_erp_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_erp_weekly_to_fact.py)

Текущая логика скрипта:

- умеет удалять предыдущий импорт за тот же weekly run:
  - `--delete-existing`
- забирает продажи и показы по двум B2C контурам:
  - `b2c_moscow`
  - `b2c_spb`
- строит weekly facts только по тем метрикам, где ERP-смысл сейчас подтверждён
- пишет подробный report по вставленным и пропущенным строкам
- в ticket sales держит только active sales:
  - `status = 0` -> отмена, строку исключаем
  - `status != 0` и `total > 0` -> считаем продажей
- для `show`-разреза у sales-метрик делает расширенный `shows/get` lookup:
  - продажи всё ещё считаются по sell date в рамках недели
  - но `seance_id -> show_name` ищется в окне `week_start .. week_end + 180 days`
  - это нужно, чтобы продажи на будущие сеансы не терялись на show-level

## Ключевая техническая логика

Рабочий join между продажами и шоу:

- `tickets.seance_id = shows.show_id`

Это важная деталь:

- join по `shows.ID` не подходит;
- weekly `Number of shows` и `Number of show visitors` используют только узкое недельное окно `shows/get`;
- weekly show-level `Revenue` / `Number of tickets` / `Number of orders` используют расширенный lookup-window для show attribution;
- часть строк без join всё равно остаётся отдельным known issue, например не-show продукты вроде сертификатных `seance_id`.

## Последний прогон

Последний известный результат:

- загружено:
  - `74`
- пропущено:
  - `14`

Report file:

- [erp_weekly_to_fact_import_report.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/erp_weekly_to_fact_import_report.csv)

## Что уже маппится

На текущем этапе подтверждённо грузятся:

- `Revenue`
- `Number of tickets`
- `Number of orders`
- `Number of shows`
- `Number of shows cancelled`
- `Number of show visitors`

Для трёх sales-метрик:

- `Revenue`
- `Number of tickets`
- `Number of orders`

weekly source of truth теперь именно `ERP`.

Дополнительно:

- weekly `Website orders` считается как подмножество `Number of orders`
- фильтр:
  - только owned site/widget agent
  - Москва: `39320770`
  - СПб: `39801873`

Поддерживаемые разрезы в этом первом проходе:

- `general`
- `show`
- `partner`

Нюанс:

- partner split сейчас рабочий только там, где уже есть надёжный `agent_id -> partner_name` mapping.

## Что реально загрузилось в последний weekly pass

### Москва

- `Revenue`:
  - `1 405 280`
- `Number of tickets`:
  - `289`
- `Number of orders`:
  - `155`

### СПб

- `Revenue`:
  - `593 750`
- `Number of tickets`:
  - `172`
- `Number of orders`:
  - `93`

## Что пока не грузится

Основные пропуски в первом проходе были:

- `Number of source-attribution responses` (candidate, not loaded in first pass)
  - причина:
    - `direct_erp_source_share_not_available`
- `Quality - Internal`
  - причина:
    - `survey_endpoints_not_working`
- часть строк по `Загадка Амулета`
  - причина:
    - историческая рассинхронизация канонизации `Загадка амулета` / `Загадка Амулета`

## Что проверяли дополнительно

Пробовали survey-related endpoints:

- `/survey/satisfaction`
- `/survey/answers/get-summary`
- `/survey/answers/get-by-survey`

Результат:

- summary endpoints сейчас не дают стабильный usable weekly source;
- поэтому `Quality - Internal` пока не берём из ERP в production-like pass.

## Known gaps

- не завершён `agent_id -> partner_name` mapping для СПб;
- `Number of source-attribution responses` не был загружен в первый pass, хотя позже уже подтвердили его через `survey/satisfaction.answers[2]`;
- `Quality - Internal` survey layer пока не готов для автоматической weekly загрузки;
- новый московский спектакль `Поезд, Чехов, два орла` уже виден в `shows/get`, но пока не имеет истории в survey/salary слоях.

## Как вернуться к этой задаче позже

Когда будем продолжать, полезно идти в таком порядке:

1. открыть этот файл;
2. открыть report:
   - [erp_weekly_to_fact_import_report.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/erp_weekly_to_fact_import_report.csv)
3. проверить, что изменилось в:
   - `ERP_AGENT_ID_HYPOTHESES.md`
   - `ERP_API_TO_WEEKLY_METRICS_NOTES.md`
4. добить оставшиеся вопросы по:
   - partner mapping для СПб
   - survey/source-share availability

## Следующий логичный шаг

- добавить надёжный SPB partner mapping;
- следить за появлением `Поезд, Чехов, два орла` в ticket-sales / survey / salary слоях;
- отдельно решить, когда загружаем `Number of source-attribution responses` из ERP и как поверх него считаем derived `Source share`;
