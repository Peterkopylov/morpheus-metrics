# Yandex Metrica

Официальная документация:

- [Yandex Metrica API](https://yandex.ru/dev/metrika/ru/)
- [Reports API](https://yandex.ru/dev/metrika/ru/stat/)

## Что уже подтверждено

Мы уже успешно получили доступ к API Метрики и видим счётчики.

Рабочий базовый тест:

```bash
curl -sS \
  -H 'Authorization: OAuth <ACCESS_TOKEN>' \
  'https://api-metrika.yandex.net/management/v1/counters'
```

Успешный ответ уже возвращал список счётчиков, в том числе:

- `48759785` — `Иммерсивное шоу Морфеус` (`morpheus-show.ru`)
- `97365452` — `Морфеус СПБ` (`spb.morpheus-show.ru`)
- `47081142` — `immersivniy.ru`

## Как получать доступ

1. Нужен OAuth app именно под Яндекс.Метрику.
2. Токен должен принадлежать аккаунту, у которого есть доступ к нужным счётчикам.
3. Для запросов используется заголовок:

```text
Authorization: OAuth <ACCESS_TOKEN>
```

В проекте токены для Метрики теперь храним отдельно от Директа:

- [`.env.yandex_metrica`](/Users/Peter/Documents/Morpheus%20Metrics/.env.yandex_metrica)
- [`.env.yandex_metrica_spb`](/Users/Peter/Documents/Morpheus%20Metrics/.env.yandex_metrica_spb)

Даже если фактически используется тот же Yandex OAuth token, что и для соседнего Direct-контура, на уровне проекта храним Метрику отдельно, чтобы не путать источники.

## Полезные endpoint'ы

### Список счётчиков

```text
GET https://api-metrika.yandex.net/management/v1/counters
```

### Обычный отчёт

```text
GET https://api-metrika.yandex.net/stat/v1/data
```

### Таймсерия / разбивка по неделям

```text
GET https://api-metrika.yandex.net/stat/v1/data/bytime
```

## Что уже делали

### Weekly visits по Москве

Счётчик:

- `48759785` — `morpheus-show.ru`

Запрос:

```bash
curl -sS -G \
  -H 'Authorization: OAuth <ACCESS_TOKEN>' \
  --data-urlencode 'ids=48759785' \
  --data-urlencode 'metrics=ym:s:visits' \
  --data-urlencode 'date1=2026-03-16' \
  --data-urlencode 'date2=2026-04-12' \
  --data-urlencode 'group=week' \
  'https://api-metrika.yandex.net/stat/v1/data/bytime'
```

### Конверсия в покупку по Москве

Рабочая цель:

- `458052768` — `Автоцель Яндекс Билеты: покупка`

Запрос:

```bash
curl -sS -G \
  -H 'Authorization: OAuth <ACCESS_TOKEN>' \
  --data-urlencode 'ids=48759785' \
  --data-urlencode 'metrics=ym:s:visits,ym:s:goal458052768visits,ym:s:goal458052768conversionRate' \
  --data-urlencode 'date1=2026-04-13' \
  --data-urlencode 'date2=2026-04-19' \
  'https://api-metrika.yandex.net/stat/v1/data'
```

### Просмотры страниц отдельных спектаклей

Мы уже использовали `ym:pv:pageviews` и фильтры по `ym:pv:URLPathFull`, чтобы получать просмотры страниц спектаклей за месяц.

Типовой запрос:

```bash
curl -sS -G \
  -H 'Authorization: OAuth <ACCESS_TOKEN>' \
  --data-urlencode 'ids=48759785' \
  --data-urlencode 'metrics=ym:pv:pageviews' \
  --data-urlencode 'date1=30daysAgo' \
  --data-urlencode 'date2=today' \
  --data-urlencode "filters=ym:pv:URLPathFull=~'^/gippocrat([?#].*)?$' OR ym:pv:URLPathFull=~'^/gippocrat#.*$'" \
  'https://api-metrika.yandex.net/stat/v1/data'
```

Это позволяет агрегировать:

- обычный URL
- URL с `#selectcity`
- URL с другими hash-фрагментами
- query-string варианты

### Канонические page-path для страниц спектаклей

По состоянию на `2026-05-02` используем такие базовые URL-path для show-page
выгрузок из Метрики:

- `Ответ Гиппократа` -> `/gippocrat`
- `Судный день` -> `/sudnyj-den`
- `До свадьбы доживёт` -> `/do-svadby-dozhivet`
- `22'07` -> `/2207`
- `ВДОХ` -> `/vdoh`
- `Загадка Амулета` -> `/zagadka-amuleta`
- `Иное место` -> `/inoe-mesto`
- `Поезд, Чехов, два орла` -> `/poezd-chehov-dva-orla`

Для Санкт-Петербурга используем тот же path на домене `spb.morpheus-show.ru`.

Примеры:

- Москва:
  - `https://morpheus-show.ru/zagadka-amuleta`
  - `https://morpheus-show.ru/inoe-mesto`
  - `https://morpheus-show.ru/poezd-chehov-dva-orla`
- СПб:
  - `https://spb.morpheus-show.ru/zagadka-amuleta`
  - `https://spb.morpheus-show.ru/inoe-mesto`

## Какие weekly-метрики в базе к каким счётчикам Метрики бьются

По состоянию на `2026-04-26` мы уже сверили weekly-данные из базы с Метрикой на
совпадение по неделям.

### Москва

Строка в базе:

- `cеансы (морфеус) ВИЗИТЫ БЕЗ corporative`

Лучше всего бьётся со счётчиком:

- `48759785` — `Иммерсивное шоу Морфеус`
- сайт: `morpheus-show.ru`

Практически:

- по неделям `2026-03-23`, `2026-03-30`, `2026-04-06`, `2026-04-13`
  совпадение было `1-в-1`
- на неделе `2026-03-16` была небольшая дельта `221` визит

Рабочий вывод:

- московская weekly-посещаемость сайта должна читаться именно из счётчика `48759785`

### Санкт-Петербург

Строка в базе:

- `Количество заходов на сайт`

Она идеально бьётся со счётчиком:

- `97365452` — `Морфеус СПБ`
- сайт: `spb.morpheus-show.ru`

Проверенные недели:

- `2026-03-16`
- `2026-03-23`
- `2026-03-30`
- `2026-04-06`
- `2026-04-13`

По этим неделям совпадение было `1-в-1`.

Рабочий вывод:

- петербургская weekly-посещаемость сайта должна читаться из счётчика `97365452`

### Что не подходит

Для weekly site visits не подходят как основной источник:

- map/sprav-счётчики
- сумма `site + maps`

То есть для сайта используем именно:

- Москва -> `48759785`
- СПб -> `97365452`

## Как определять географию в Метрике

Для Метрики важно разделять два вопроса:

- география всех визитов сайта
- география именно рекламных визитов из Яндекс.Директа

### 1. География рекламных визитов из Директа

Рабочий и уже проверенный путь:

- dimension: `ym:s:regionCity`
- filters:
  - `ym:s:lastTrafficSource=='ad'`
  - `ym:s:lastAdvEngine=='ya_direct'`
- metric: обычно `ym:s:visits`

Это отвечает на вопрос:

- из каких городов пришли реальные визиты на сайт из Яндекс.Директа

Практически именно этим способом мы уже подтвердили, что на петербургский
счётчик `97365452` реально приходят рекламные визиты из `Saint Petersburg`,
даже когда direct geo-report по показам выглядел более "московским".

### 2. География всех визитов сайта

Если нужен не рекламный, а общий сайтовый geo-срез, можно брать ту же
гео-dimension без direct-фильтров:

- dimension: `ym:s:regionCity`
- metric: `ym:s:visits`

Это отвечает на вопрос:

- из каких городов вообще приходят пользователи на сайт

### Какой срез брать в каком случае

- где были реальные рекламные визиты на сайт -> `ym:s:regionCity` + direct filters
- где вообще были визиты сайта -> `ym:s:regionCity` без direct filters
- где были показы и клики рекламы до сайта -> это уже **Direct API**, не Метрика

### Практическая граница Метрики

Метрика хорошо отвечает на вопросы про:

- визиты
- сессии
- каналы
- географию визитов
- конверсии
- доход

Но Метрика не является первичным источником для:

- полного кабинетного spend
- полного числа показов в рекламном кабинете

Для этих задач source of truth остаётся Direct API.

## Решение для факт-слоя

По состоянию на `2026-05-02` для нового факт-слоя считаем так:

- `Marketing costs` берём из **Yandex Direct**
- `Yandex Metrica` используем для:
  - `Website visits`
  - visits by channel
  - visits / pageviews по страницам шоу
  - geo of ad traffic
  - `Performance marketing revenue`

То есть metrica direct-costs отчёты можно использовать как аналитический/reference срез,
но не как основной source of truth для weekly marketing spend.

## Performance marketing revenue

По состоянию на `2026-06-02` source of truth для доходов от
перформанс-маркетинга — `Yandex Metrica`, а не `Yandex Direct Reports API`.

Причина: `Yandex Direct Reports API` для части кампаний возвращает статическую
ценность цели, а не реальную сумму заказа. Метрика отдает реальные суммы заказов
через revenue избранных целей.

Canonical metric:

- metric key: `yandex_direct_conversion_revenue`
- metric name: `Performance marketing revenue`
- legacy note: key оставлен старым для совместимости существующих витрин
- source system: `yandex_metrica`
- channel: `perfomance`

Запрос:

```text
GET https://api-metrika.yandex.net/stat/v1/data
ids=<counter_id>
date1=<period_start>
date2=<period_end>
metrics=ym:s:favoriteGoalsConvertedRUBRevenue
dimensions=ym:s:<attribution>TrafficSource,ym:s:<attribution>AdvEngine
attribution=automatic
accuracy=full
```

В fact layer включаем только строки:

- `ym:s:<attribution>TrafficSource = ad`
- `ym:s:<attribution>AdvEngine = ya_direct`
- `ym:s:<attribution>AdvEngine = ya_undefined`

Контрольная сверка за май `2026`, счетчик Москва `48759785`:

- `Yandex: Direct` = `420 320 р.`
- `Yandex.Direct: Undetermined` = `36 700 р.`
- performance revenue = `457 020 р.`

## Известные риски

- Если API отвечает `403 Access is denied`, обычно проблема в одном из трёх мест:
  - не тот OAuth app / не те права
  - токен выдан не тем аккаунтом
  - у аккаунта нет доступа к нужному счётчику

## Идея для future use: goal-based отчёты

Полезное рабочее наблюдение:

- в Яндекс-стеке можно строить отчёты, опираясь на **номера целей**
- это особенно полезно для performance-срезов:
  - ecommerce-воронка
  - заказ / оплата
  - выбранные конверсии
  - goal-based атрибуция

Важно держать это именно как принцип:

- сначала ищем **goal IDs** у нужного счётчика
- потом уже выбираем конкретный API-путь под задачу
- не привязываемся заранее к одному жёсткому endpoint

Практически это значит:

- один и тот же бизнес-вопрос может решаться через разные срезы:
  - `Direct Reports API`
  - `Metrica Stat API`
  - direct-costs отчёты Метрики

То есть формулировка на будущее такая:

- **через номер цели идти можно**
- **но конкретный путь запроса надо подбирать под тип отчёта, а не считать универсальным**
