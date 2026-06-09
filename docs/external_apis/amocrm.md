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
- `8784810` — `Сертификаты`
- `8784838` — `Возвраты`

Чтобы взять сделки только из `Корпоративы`:

```bash
curl -sS --globoff -H "Authorization: Bearer $AMOCRM_LONG_LIVED_TOKEN" \
  -H "Accept: application/json" \
  "https://morpheusshow.amocrm.ru/api/v4/leads?limit=50&filter[pipeline_id]=8783794"
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
  "https://morpheusshow.amocrm.ru/api/v4/leads?limit=250&filter[pipeline_id][0]=8783794&filter[created_at][from]=FROM_TS&filter[created_at][to]=TO_TS"
```

Рабочий пример для `Корпоративы` за полную неделю `13.04.2026 00:00:00 — 19.04.2026 23:59:59` по Москве:

```bash
curl -sS --globoff -H "Authorization: Bearer $AMOCRM_LONG_LIVED_TOKEN" \
  -H "Accept: application/json" \
  "https://morpheusshow.amocrm.ru/api/v4/leads?filter[pipeline_id][0]=8783794&filter[created_at][from]=1776027600&filter[created_at][to]=1776632399&limit=250"
```

Что это значит:

- `filter[pipeline_id][0]=8783794` — только воронка `Корпоративы`
- `filter[created_at][from]` и `filter[created_at][to]` — диапазон по дате создания сделки
- `limit=250` — верхняя граница на страницу

Если нужен точный диапазон, лучше сначала посчитать timestamps отдельно и уже потом подставлять в запрос.

Чтобы не повторять ручные ошибки с Unix timestamps и `curl`, в проект добавлен безопасный helper:

```bash
python3 scripts/amocrm_leads_report.py \
  --pipeline-id 8783794 \
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

- `lead_added`
- `lead_status_changed`
- `entity_responsible_changed`
- `entity_tag_added`
- `name_field_changed`
- `sale_field_changed`
- изменения custom fields
- линки на контакт / компанию

## Подтверждённый пример по Корпоративам

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

## Что важно помнить

- `authorization code` у amoCRM одноразовый и быстро протухает
- для быстрой ручной проверки удобнее использовать долгосрочный токен
- токены и секреты не хранить в markdown и не коммитить в репозиторий
- если строим ingestion, то лучше читать данные через `api/v4/*` и складывать в raw-таблицы
- не собирать сложные amoCRM-запросы вручную, если можно использовать `scripts/amocrm_leads_report.py`
