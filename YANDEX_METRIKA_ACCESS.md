# Yandex Metrica Access

## Current OAuth app

- Product: `Яндекс.Метрика`
- `client_id`: `0532c7c5674544019a882a07a7a772bc`
- `client_secret`: `2df986847ecd48f782bdd15db05fe908`
- `redirect_uri`: `https://oauth.yandex.ru/verification_code`

## Required access

The OAuth app must be created with Yandex Metrica access, not only Yandex Direct.

The token must belong to a Yandex account that has access to the needed counters.

## How to get a token

Open:

`https://oauth.yandex.ru/authorize?response_type=token&client_id=0532c7c5674544019a882a07a7a772bc`

Then:

1. Log in with the Yandex account that has access to the counters.
2. Approve access.
3. Copy the resulting `access_token`.

## How to test access

Basic check:

```bash
curl -sS \
  -H 'Authorization: OAuth <ACCESS_TOKEN>' \
  'https://api-metrika.yandex.net/management/v1/counters'
```

Successful access returns a JSON object with `rows` and `counters`.

## Confirmed working result

We successfully tested access with a valid token and received `6` counters.

Important counters:

- `48759785` — `Иммерсивное шоу Морфеус`
  - site: `morpheus-show.ru`
  - permission: `edit`
- `97365452` — `Морфеус СПБ`
  - site: `spb.morpheus-show.ru`
  - permission: `edit`
- `47081142` — `immersivniy.ru`

Additional visible counters included Yandex Maps / directory related counters with `view` permission.

## Useful API endpoint

Counters list:

- `GET https://api-metrika.yandex.net/management/v1/counters`

Main documentation:

- `https://yandex.ru/dev/metrika/ru/stat/`

## Working queries we already used

### 1. Check that the token can see counters

```bash
curl -sS \
  -H 'Authorization: OAuth <ACCESS_TOKEN>' \
  'https://api-metrika.yandex.net/management/v1/counters'
```

### 2. Weekly visits for the Moscow main site

Counter:

- `48759785` — `Иммерсивное шоу Морфеус`
- site: `morpheus-show.ru`

Example query for weekly visits:

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

This was used to compare Metrica visits with the weekly metric:

- `САЙТ / cеансы (морфеус) ВИЗИТЫ БЕЗ corporative`

### 3. Purchase conversion for the Moscow main site

The working purchase goal we used:

- `458052768` — `Автоцель Яндекс Билеты: покупка`

Example query:

```bash
curl -sS -G \
  -H 'Authorization: OAuth <ACCESS_TOKEN>' \
  --data-urlencode 'ids=48759785' \
  --data-urlencode 'metrics=ym:s:visits,ym:s:goal458052768visits,ym:s:goal458052768conversionRate' \
  --data-urlencode 'date1=2026-04-13' \
  --data-urlencode 'date2=2026-04-19' \
  'https://api-metrika.yandex.net/stat/v1/data'
```

### 4. Pageviews for individual show pages over the last month

Endpoint:

- `GET https://api-metrika.yandex.net/stat/v1/data`

Metric used:

- `ym:pv:pageviews`

Dimension used for exploration:

- `ym:pv:URLPathFull`

First we inspected top URLs:

```bash
curl -sS -G \
  -H 'Authorization: OAuth <ACCESS_TOKEN>' \
  --data-urlencode 'ids=48759785' \
  --data-urlencode 'dimensions=ym:pv:URLPathFull' \
  --data-urlencode 'metrics=ym:pv:pageviews' \
  --data-urlencode 'date1=30daysAgo' \
  --data-urlencode 'date2=today' \
  --data-urlencode 'limit=50' \
  --data-urlencode 'sort=-ym:pv:pageviews' \
  'https://api-metrika.yandex.net/stat/v1/data'
```

Then we queried exact show URLs with `filters` on `ym:pv:URLPathFull`.

Patterns that worked:

- `/gippocrat`
- `/sudnyj-den`
- `/do-svadby-dozhivet`
- `/2207`
- `/vdoh`
- `/zagadka-amuleta`
- `/inoe-mesto`

Example for one show page:

```bash
curl -sS -G \
  -H 'Authorization: OAuth <ACCESS_TOKEN>' \
  --data-urlencode 'ids=48759785' \
  --data-urlencode 'metrics=ym:pv:pageviews' \
  --data-urlencode 'date1=30daysAgo' \
  --data-urlencode 'date2=today' \
  --data-urlencode \"filters=ym:pv:URLPathFull=~'^/gippocrat([?#].*)?$' OR ym:pv:URLPathFull=~'^/gippocrat#.*$'\" \
  'https://api-metrika.yandex.net/stat/v1/data'
```

This approach lets us aggregate all variants of the same page, including:

- plain URL
- `#selectcity`
- other hash fragments
- query-string variants

## Notes

- A token created for Yandex Direct only is not enough for Metrica.
- If API returns `403 Access is denied`, check:
  - the OAuth app product/scope,
  - the Yandex account used during authorization,
  - whether that account has access to the target Metrica counters.
