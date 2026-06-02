# Yandex Metrica Weekly Fact Ingestion

## Что это

Отдельный weekly ingestion из `Yandex Metrica` в новый факт-слой
`fact_metric_observation`.

По состоянию на `2026-05-02` этот pass используется для:

- `Website visits` по каналам
- `Website visits` по страницам шоу
- `Website visits` по `b2b` странице `/corporative`

И **не** используется для:

- `Marketing costs`

Для расходов принято отдельное правило:

- `Marketing costs` -> primary source = `Yandex Direct`

## Счётчики

Москва:

- `48759785` — `Иммерсивное шоу Морфеус`

СПб:

- `97365452` — `Морфеус СПБ`

## Токены

Основной контур:

- `/Users/Peter/Documents/Morpheus Metrics/.env.yandex_metrica`
  - `YANDEX_DIRECT_ACCESS_TOKEN`

SPB-контур:

- `/Users/Peter/Documents/Morpheus Metrics/.env.yandex_metrica_spb`
  - `YANDEX_DIRECT_SPB_ACCESS_TOKEN`

## Скрипт

- `/Users/Peter/Documents/Morpheus Metrics/scripts/import_yandex_metrica_weekly_to_fact.py`

## Какие метрики грузим

### 1. Website visits by channel

Источник:

- `ym:s:visits`

Dimensions:

- `ym:s:lastTrafficSource`
- `ym:s:lastAdvEngine`

Нормализация в наш `channel_name`:

- `organic` -> `organic`
- `referral` -> `referral`
- `recommend` -> `referral`
- `mail` -> `email`
- `social`, `messenger` -> `social`
- `ad + ya_direct / ya_undefined` -> `perfomance`
- `ad + instagram / vkontakte / facebook / unknown` -> `perfomance`
- `direct`, `internal` -> `organic`
- всё прочее -> `other`

Для `b2b` channel-split считается не по всему сайту, а по странице:

- `https://morpheus-show.ru/corporative`

Подход:

- источник: основной московский счётчик `48759785`
- метрика: `ym:s:visits`
- dimensions:
  - `ym:s:lastTrafficSource`
  - `ym:s:lastAdvEngine`
- фильтр по `ym:pv:URLPathFull` на `/corporative`

### 2. Website visits by show pages

Источник:

- `ym:pv:pageviews`

Подход:

- отдельный запрос на каждый show-path
- фильтр по `ym:pv:URLPathFull`

Канонические path:

- `Ответ Гиппократа` -> `/gippocrat`
- `Судный день` -> `/sudnyj-den`
- `До свадьбы доживёт` -> `/do-svadby-dozhivet`
- `22'07` -> `/2207`
- `ВДОХ` -> `/vdoh`
- `Загадка Амулета` -> `/zagadka-amuleta`
- `Иное место` -> `/inoe-mesto`
- `Поезд, Чехов, два орла` -> `/poezd-chehov-dva-orla`

Для СПб используется тот же path на домене `spb.morpheus-show.ru`.

## Куда пишем в fact layer

Таблица:

- `public.fact_metric_observation`

Поля:

- `source_system = yandex_metrica`
- `source_run_id = yandex_metrica_weekly_v1`
- `period_granularity = week`
- `period_start = monday`
- `period_end = sunday`

Разрезы:

- channel rows:
  - `channel_name` заполнен
  - `show_name = null`
- show-page rows:
  - `show_name` заполнен
  - `channel_name = null`
- b2b corporative rows:
  - общий ряд: `business_unit = b2b`, `show_name = null`, `channel_name = null`
  - channel rows: `business_unit = b2b`, `channel_name` заполнен

## Подтверждённый weekly pass

Период:

- `2026-04-20` -> `2026-04-26`

Результат:

- inserted: `24`

Отчёт:

- `/Users/Peter/Documents/Morpheus Metrics/generated/yandex_metrica_weekly_to_fact_import_report.csv`

Примеры загруженных значений:

Москва:

- `Website visits / channel:direct = 4775`
- `Website visits / show:Ответ Гиппократа = 452`

СПб:

- `Website visits / channel:direct = 1001`
- `Website visits / show:Ответ Гиппократа = 262`

## Команда запуска

```bash
python3 /Users/Peter/Documents/Morpheus\ Metrics/scripts/import_yandex_metrica_weekly_to_fact.py \
  --database-url 'postgresql://admin:strongpassword@134.122.83.160:5432/analytics' \
  --week-start 2026-04-20 \
  --delete-existing
```

## Ограничения и решения

- show-level rows сейчас грузятся как `ym:pv:pageviews`, а не как session visits
- это осознанно сохранено в fact-layer как `Website visits`, потому что правило в каталоге
  описывает visits/show-page layer, а не ecommerce conversion layer
- если позже захотим разделить `pageviews` и `visits`, лучше добавить отдельную каноническую
  метрику, а не silently менять смысл уже загруженных рядов
