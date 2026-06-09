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

## Известные риски

- Если API отвечает `403 Access is denied`, обычно проблема в одном из трёх мест:
  - не тот OAuth app / не те права
  - токен выдан не тем аккаунтом
  - у аккаунта нет доступа к нужному счётчику
