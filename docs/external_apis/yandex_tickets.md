# Yandex Tickets

Официальная документация:

- [Yandex Tickets API](https://yandex.ru/support/tickets/ru/tickets-api)

## Что уже подтверждено

У нас уже есть рабочий прямой доступ к CRM API Яндекс.Билетов.

Базовый хост:

```text
https://api.tickets.yandex.net/api/crm/
```

## Текущий подтверждённый контур

На текущих данных у нас подтверждена только Москва.

Подключённая сущность:

- московский CRM login
- московский `city_id`

Для СПб отдельные данные доступа пока не зафиксированы.

## Как устроена авторизация

`auth` не хранится как постоянный токен. Он вычисляется на лету.

Схема:

1. взять логин
2. взять пароль
3. посчитать `MD5(password)`
4. посчитать `SHA1(md5 + timestamp)`
5. собрать строку:

```text
{login}:{sha1}:{timestamp}
```

Где `timestamp` — Unix timestamp в секундах.

Эквивалент на Python:

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

## Основные endpoint'ы, которые уже использовали

### Список заказов

```text
GET https://api.tickets.yandex.net/api/crm/?action=crm.order.list&auth={AUTH}&city_id={CITY_ID}
```

### Детали заказа

```text
GET https://api.tickets.yandex.net/api/crm/?action=crm.order.info&auth={AUTH}&city_id={CITY_ID}&order_id[]={ORDER_ID}
```

### Отчёт по событию

```text
GET https://api.tickets.yandex.net/api/crm/?action=crm.report.event&auth={AUTH}&city_id={CITY_ID}&event_ids={EVENT_ID}
```

## Что уже умеем делать

- читать заказы и их суммы
- видеть `event_id`, `tickets_count`, `sum`, `is_returned`, `agent_id`
- получать детали заказа и билетов
- разворачивать `event_id -> event_name` через `crm.report.event`

## Как доставать информацию про спектакли

Это уже подтверждённый рабочий паттерн.

### Идея

В заказах Яндекс.Билетов название спектакля не лежит напрямую удобным полем в `crm.order.list`.

Рабочая связка такая:

1. взять заказы через `crm.order.list`
2. у каждого заказа взять `event_id`
3. для каждого `event_id` вызвать `crm.report.event`
4. из ответа взять:
   - `event_name`
   - `event_date`
   - `activity_id`
5. агрегировать заказы, билеты и сумму уже по `event_name`

### Что это даёт

Так можно собрать:

- сколько билетов выкуплено на какой спектакль
- сколько заказов приходится на каждый спектакль
- выручку по спектаклям
- отдельно выделять сертификаты, если они заведены как отдельные события

### Какие endpoint'ы для этого нужны

#### 1. Список заказов

```text
GET /api/crm/?action=crm.order.list&auth={AUTH}&city_id={CITY_ID}
```

Из него берём:

- `id`
- `order_date`
- `event_id`
- `tickets_count`
- `sum`
- `is_returned`
- `status`

#### 2. Отчёт по событию

```text
GET /api/crm/?action=crm.report.event&auth={AUTH}&city_id={CITY_ID}&event_ids={EVENT_ID}
```

Из него берём:

- `event_name`
- `event_date`
- `activity_id`
- `tickets_sold`
- `tickets_sold_sum`

### Пример живого подтверждения

Для заказа:

- `63007859`

в деталях заказа был:

- `event_id = 59306413`

А через `crm.report.event` для `59306413` мы получили:

- `event_name = "Ответ Гиппократа"`
- `event_date = "2026-04-24 19:45:00"`
- `activity_id = 39707796`

То есть связка `order -> event_id -> event_name` реально работает.

### Важный нюанс

Текущий `crm.order.list` у нас на практике отдаёт не “всю историю”, а recent feed.

На момент проверки:

- в фиде было `1000` последних заказов
- самый ранний заказ в фиде был от `2026-03-07`

Это значит:

- для недавних периодов паттерн работает хорошо
- для более старых периодов нужно отдельно проверять, хватает ли глубины фида

### Практическая схема агрегации по спектаклям

При расчёте:

- исключать заказы с `status = 0`
- исключать returned, если нужен чистый sold count
- агрегировать:
  - `tickets_count` -> билеты
  - `sum` -> денежная сумма
  - `orders` -> количество заказов

### Что уже удалось собрать таким способом

Мы уже собирали московский мартовский срез по спектаклям через:

- `crm.order.list`
- `event_id -> crm.report.event -> event_name`

И получили рабочую таблицу вида:

- `Ответ Гиппократа`
- `До свадьбы доживёт`
- `Судный день`
- `22'07`
- `Загадка Амулета`
- `ВДОХ`
- `Иное место`
- `Подарочный сертификат (Москва)`

То есть этот способ уже можно считать нашим рабочим стандартом для спектакльной аналитики из Яндекс.Билетов.

## Практические выводы, которые уже подтверждены

### 1. Заказы можно агрегировать по спектаклям

Рабочая схема:

- взять `crm.order.list`
- у заказов получить `event_id`
- через `crm.report.event` получить:
  - `event_name`
  - `activity_id`
  - показатели продаж по событию

### 2. Сертификаты, похоже, живут на уровне события / мероприятия

На практике это оказалось надёжнее, чем попытки искать сертификаты только по полям билета.

### 3. Возвраты

Флаг `is_returned` в заказах есть, но через него не всегда получается напрямую восстановить денежную сумму возврата.

### 4. Москва vs СПб

Пока подтверждён только московский доступ. Для СПб нужен отдельный набор данных доступа.

## Полезная рабочая заметка

Более подробная старая заметка по этой интеграции лежит здесь:

- [`/Users/Peter/Documents/Morpheus Metrics/YANDEX_TICKETS_API_NOTES.md`](/Users/Peter/Documents/Morpheus%20Metrics/YANDEX_TICKETS_API_NOTES.md)
