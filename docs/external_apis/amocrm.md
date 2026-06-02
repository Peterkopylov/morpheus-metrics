# amoCRM

Официальная документация:

- [amoCRM API reference](https://www.amocrm.ru/developers/content/crm_platform/api-reference)

## Зачем нам это

amoCRM нужен как источник данных по:

- сделкам
- воронкам и этапам
- контактам
- компаниям
- задачам
- событиям / истории изменений

Это потенциальный source of truth для CRM-части метрик, воронки и части B2B/лидогенерации.

## Что уже поняли

- Для нашего проекта не нужен PHP SDK как обязательное условие.
- amoCRM можно забирать напрямую из Python через REST API.
- Для проекта это даже предпочтительнее, потому что основной аналитический контур у нас уже Python/Postgres-ориентированный.

## Рекомендуемый подход

Не тянуть amoCRM в проект через отдельный PHP-стек, а строить интеграцию как обычный ingestion pipeline:

1. авторизация к amoCRM API
2. загрузка сырых сущностей в raw-таблицы
3. нормализация в аналитические таблицы / витрины

## Что хотим забирать в raw-слой

Минимальный набор:

- `raw_amocrm_leads`
- `raw_amocrm_contacts`
- `raw_amocrm_companies`
- `raw_amocrm_tasks`
- `raw_amocrm_events`

При необходимости:

- пользователи
- кастомные поля
- воронки
- статусы / этапы
- примечания

## Предлагаемая аналитическая ценность

Что потом можно будет строить:

- количество новых сделок
- этапы воронки
- конверсия между этапами
- скорость прохождения воронки
- активность менеджеров
- CRM-источник лидов
- разрезы по B2B / корпоративным продажам

## Практическая заметка

Если делать интеграцию, то лучше держать разделение:

- raw-данные из amoCRM
- нормализованные сущности
- derived-метрики

А не пытаться сразу складывать всё в одну общую metric table.

## Текущее состояние

На момент фиксации этой заметки:

- документация по amoCRM зафиксирована
- целевой путь — Python-интеграция, а не PHP SDK
- прямой доступ к amoCRM API уже подтверждён

## Рабочий доступ

Что уже подтвердили живыми запросами:

- домен аккаунта: `https://morpheusshow.amocrm.ru`
- интеграция создана
- HTTPS callback для OAuth поднят на нашем сервере:
  - `https://134.122.83.160.sslip.io/amocrm/callback`
  - `https://134.122.83.160.sslip.io/amocrm/uninstall`
- долгосрочный токен работает как Bearer token для amoCRM API

Проверенные запросы:

- `GET /api/v4/account`
- `GET /api/v4/leads?limit=3`

Что вернулось:

- аккаунт `Морфеус МСК`
- `account_id = 32019874`
- `subdomain = morpheusshow`
- реальные сделки из CRM

Это значит, что доступ есть не только к метаданным аккаунта, но и к CRM-сущностям.

## Как проверять доступ

Минимальная проверка:

```bash
curl -sS -H "Authorization: Bearer $AMOCRM_LONG_LIVED_TOKEN" \
  -H "Accept: application/json" \
  "https://morpheusshow.amocrm.ru/api/v4/account"
```

Проверка, что открываются сделки:

```bash
curl -sS -H "Authorization: Bearer $AMOCRM_LONG_LIVED_TOKEN" \
  -H "Accept: application/json" \
  "https://morpheusshow.amocrm.ru/api/v4/leads?limit=10"
```

## Как добраться до воронок

Список воронок:

```bash
curl -sS -H "Authorization: Bearer $AMOCRM_LONG_LIVED_TOKEN" \
  -H "Accept: application/json" \
  "https://morpheusshow.amocrm.ru/api/v4/leads/pipelines"
```

Что уже подтвердили:

- `8779950` — `Квалификация`
- `8783786` — `Спектакли`
- `8783794` — `Корпоративы`
- `10869194` — `Корпоративы 2.0`
- `8784810` — `Сертификаты`
- `8784838` — `Возвраты`

Текущее weekly ingestion для B2B/funnel-метрик нужно строить по **`Корпоративы 2.0`**, а не по старой воронке `Корпоративы`.

Чтобы взять сделки только из `Корпоративы 2.0`:

```bash
curl -sS --globoff -H "Authorization: Bearer $AMOCRM_LONG_LIVED_TOKEN" \
  -H "Accept: application/json" \
  "https://morpheusshow.amocrm.ru/api/v4/leads?limit=50&filter[pipeline_id]=10869194"
```

## Как правильно работать с фильтрами

У amoCRM фильтры идут в query string в формате `filter[...]`.

Важно:

- для `curl` почти всегда использовать `--globoff`
- иначе квадратные скобки в URL могут ломать запрос
- диапазоны по времени передавать через Unix timestamps
- для отчётов явно фиксировать часовой пояс, у нас обычно `Europe/Moscow`

Базовый паттерн:

```bash
curl -sS --globoff -H "Authorization: Bearer $AMOCRM_LONG_LIVED_TOKEN" \
  -H "Accept: application/json" \
  "https://morpheusshow.amocrm.ru/api/v4/leads?limit=250&filter[pipeline_id][0]=10869194&filter[created_at][from]=FROM_TS&filter[created_at][to]=TO_TS"
```

Рабочий пример для `Корпоративы 2.0` за полную неделю `13.04.2026 00:00:00 — 19.04.2026 23:59:59` по Москве:

```bash
curl -sS --globoff -H "Authorization: Bearer $AMOCRM_LONG_LIVED_TOKEN" \
  -H "Accept: application/json" \
  "https://morpheusshow.amocrm.ru/api/v4/leads?filter[pipeline_id][0]=10869194&filter[created_at][from]=1776027600&filter[created_at][to]=1776632399&limit=250"
```

Что это значит:

- `filter[pipeline_id][0]=10869194` — только воронка `Корпоративы 2.0`
- `filter[created_at][from]` и `filter[created_at][to]` — диапазон по дате создания сделки
- `limit=250` — верхняя граница на страницу

Если нужен точный диапазон, лучше сначала посчитать timestamps отдельно и уже потом подставлять в запрос.

Чтобы не повторять ручные ошибки с Unix timestamps и `curl`, в проект добавлен безопасный helper:

```bash
python3 scripts/amocrm_leads_report.py \
  --pipeline-id 10869194 \
  --date-from 2026-04-13 \
  --date-to 2026-04-19 \
  --count-only
```

Он:

- сам считает границы дня в `Europe/Moscow`
- сам собирает query string для amoCRM
- не требует вручную подставлять `filter[...]`
- читает токен из `.env.amocrm`

Шаблон для секрета:

- `.env.amocrm.example`
- рабочий локальный файл должен называться `.env.amocrm`

## Как смотреть историю сделки

История изменений сделки идёт через общий events feed, фильтруемый по сущности `lead`.

Шаблон запроса:

```bash
curl -sS --globoff -H "Authorization: Bearer $AMOCRM_LONG_LIVED_TOKEN" \
  -H "Accept: application/json" \
  "https://morpheusshow.amocrm.ru/api/v4/events?limit=50&filter[entity]=lead&filter[entity_id]=LEAD_ID"
```

Что видно в ответе:

## Текущая weekly funnel mapping логика

На май 2026 weekly importer опирается на воронку:

- `pipeline_id = 10869194` — `Корпоративы 2.0`

И считает funnel-метрики по названиям статусов этой воронки:

- `Контакт установлен` -> `Number of contacts established`
- `Квалифицирован` -> `Number of qualified leads`
- `Презентация проведена` -> `Number of concepts sent`
- `Назначена креативная встреча` -> `Number of creative meetings scheduled`
- `Креативная встреча проведена` -> `Number of creative meetings`
- `КП отправлено` -> `Number of proposals sent`
- `Договор отправлен` -> `Number of contracts sent`
- `Договор подписан` -> `Number of contracts approved`
- `Оплата получена` -> `Number of payments received`
- `Отзыв получен` -> `Number of orders`
- `Закрыто и не реализовано` -> `Number of lost leads`

Для исторического weekly backfill до `2025-05-01` у старой воронки `Корпоративы` (`8783794`) используем отдельный маппинг отличающихся этапов:

- `Концепт отправлен` -> `Number of concepts sent`
- `Проведена креативная встреча` -> `Number of creative meetings`
- `Договор согласован` -> `Number of contracts approved`

Остальные общие этапы (`Контакт установлен`, `Квалифицирован`, `Назначена креативная встреча`, `КП отправлено`, `Договор отправлен`, `Оплата получена`, `Отзыв получен`, `Закрыто и не реализовано`) считаются одинаково в обеих воронках.

Технический нюанс:

- amoCRM может вернуть `204 No Content`, если за диапазон нет новых лидов или событий
- weekly importer должен трактовать это как пустой результат, а не как ошибку JSON

- `lead_added`
- `lead_status_changed`
- `entity_responsible_changed`
- `entity_tag_added`
- `name_field_changed`
- `sale_field_changed`
- изменения custom fields
- линки на контакт / компанию

## Подтверждённый исторический пример по старой воронке

Живой пример:

- сделка `4563465`
- название: `Питер, 200 чел., 12.12/18.12, Незнакомцы`
- `pipeline_id = 8783794` (`Корпоративы`)

Что видно по истории:

- сделка была создана
- потом переведена из `Квалификация` в `Корпоративы`
- дальше двигалась по этапам внутри `Корпоративы`
- у неё менялись:
  - ответственный
  - теги
  - бюджет
  - название

Это значит, что по amoCRM API мы уже умеем доставать не только текущий срез сделок, но и timeline изменений по конкретной сделке.

Важно:

- этот пример полезен как историческое доказательство доступа к API и событиям
- но текущий weekly fact ingestion больше не должен опираться на старую воронку `8783794`
- для weekly B2B funnel-layer действует историческое переключение по периоду:
- до `2025-05-01` использовать старую воронку `Корпоративы` (`8783794`)
- начиная с `2025-05-01` использовать `Корпоративы 2.0` (`10869194`)

## Что важно помнить

- `authorization code` у amoCRM одноразовый и быстро протухает
- для быстрой ручной проверки удобнее использовать долгосрочный токен
- токены и секреты не хранить в markdown и не коммитить в репозиторий
- если строим ingestion, то лучше читать данные через `api/v4/*` и складывать в raw-таблицы
- не собирать сложные amoCRM-запросы вручную, если можно использовать `scripts/amocrm_leads_report.py`
