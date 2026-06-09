# Yandex Tickets API Notes

Рабочая заметка по прямому доступу к Яндекс.Билетам.

Дата фиксации:
- `2026-04-19`

## Где лежат исходные файлы

В проекте сохранены два Postman-файла:

- `/Users/Peter/Documents/Morpheus Metrics/postman/yandex_tickets/Yandex tickets API.postman_environment.json`
- `/Users/Peter/Documents/Morpheus Metrics/postman/yandex_tickets/yandex-tickets.postman_collection.json`

## Что уже подтверждено

- API живой и отвечает по хосту:
  - `https://api.tickets.yandex.net/api/crm/`
- Коллекция рабочая.
- `YT_AUTH` не хранится готовым значением в environment.
- `YT_AUTH` генерируется в `prerequest` script внутри Postman collection.
- Подключение уже проверено живым запросом к `crm.order.list`.

## Текущая подключенная сущность

По текущему environment подключена только Москва:

- `YT_LOGIN = morpheus_crm_msc`
- `YT_CITY_ID = 39319731`

Для Санкт-Петербурга в проекте пока не найдено:

- второго `YT_CITY_ID`
- отдельного логина
- второго Postman environment

## Как считается `YT_AUTH`

В Postman collection используется такая схема:

1. взять `YT_LOGIN`
2. взять `YT_PASSWORD`
3. посчитать `MD5(password)`
4. посчитать `SHA1(md5 + timestamp)`
5. собрать строку:

```text
{login}:{sha1}:{timestamp}
```

Где:

- `timestamp` — Unix timestamp в секундах
- `md5` — hex digest от пароля
- `sha1` — hex digest от строки `md5 + timestamp`

## Эквивалент на Python

```python
import hashlib
import time

login = "..."
password = "..."
timestamp = str(int(time.time()))
md5 = hashlib.md5(password.encode()).hexdigest()
sha1 = hashlib.sha1((md5 + timestamp).encode()).hexdigest()
auth = f"{login}:{sha1}:{timestamp}"
```

## Основные endpoint'ы из коллекции

### 1. Список заказов

```text
POST https://api.tickets.yandex.net/api/crm/?action=crm.order.list&auth={YT_AUTH}&city_id={YT_CITY_ID}&start_date=...&end_date=...
```

### 2. Детали заказов

```text
POST https://api.tickets.yandex.net/api/crm/?action=crm.order.info&auth={YT_AUTH}&city_id={YT_CITY_ID}&order_id[]=...
```

### 3. Отчёт по событию

```text
POST https://api.tickets.yandex.net/api/crm/?action=crm.report.event&auth={YT_AUTH}&city_id={YT_CITY_ID}&event_ids=...
```

## Что уже видно в ответе `crm.order.list`

На живом запросе API возвращает, например:

- `id`
- `customer_id`
- `customer.name`
- `customer.phone`
- `customer.email`
- `status`
- `is_returned`
- `order_date`
- `event_id`
- `tickets_count`
- `sum`
- `fee`
- `sale_type`
- `agent_id`

## Практические замечания

- `YT_AUTH` лучше считать заново перед каждым запросом.
- Если `auth` не передан, API отвечает:

```json
{"status":"1","error":"Session ID is not received"}
```

- В текущем проекте уже подтверждено, что схема авторизации из Postman collection работает.

## Что нужно для СПб

Чтобы подключить Петербург, нужен один из вариантов:

- отдельный `YT_CITY_ID`
- отдельный логин/пароль
- отдельный Postman environment

Пока в проекте этих данных нет.
