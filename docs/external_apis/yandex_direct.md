# Yandex Direct

Официальная документация:

- [Yandex Direct API](https://yandex.ru/dev/direct/doc/ru/)
- [Getting data with get](https://yandex.ru/dev/direct/doc/ru/best-practice/get)
- [Access and authorization](https://yandex.ru/dev/direct/doc/ru/concepts/access)

## Что уже подтверждено

По состоянию на `2026-04-26` доступ к боевому `Reports API` подтверждён.

Рабочее приложение:

- `Статистика Яндекс Директа API`
- `ClientID = d1877831b6124376a7f1a8c45f2527f3`

Отдельный SPB-кабинет:

- `ClientID = 70a1dba4ad7148b4acdf000cdd093e13`
- права на скрине включают:
  - `Яндекс.Директ`
  - `Яндекс.Метрика`
- это отдельный личный кабинет, не тот же контур, что основной московский

Рабочий токен хранить локально в:

- `/Users/Peter/Documents/Morpheus Metrics/.env.yandex_direct`

SPB-контур хранить локально отдельно в:

- `/Users/Peter/Documents/Morpheus Metrics/.env.yandex_direct_spb`

Признак, что доступ действительно заработал:

- запрос к `https://api.direct.yandex.com/json/v5/reports` вернул `HTTP 200`
- в ответе пришли реальные кампании, даты, расходы, клики и показы
- этот же токен также успешно открывает `Yandex Metrica Management API`

## Связь с Яндекс.Метрикой

По состоянию на `2026-04-26` подтверждено, что рабочий Direct-токен можно
использовать и для Метрики:

- `GET https://api-metrika.yandex.net/management/v1/counters` -> `HTTP 200`

Но важно:

- доступы к счётчикам у разных приложений/токенов могут отличаться
- один токен не гарантирует видимость всех тех же счётчиков, что и другой

Практически мы уже увидели такую разницу:

- старый metrica-токен видел `47081142` (`immersivniy.ru`)
- новый direct-токен этот счётчик не видит
- при этом новый direct-токен видит дополнительные map/sprav-счётчики, которых не было у старого токена

Общие подтверждённые счётчики у обоих токенов:

- `48759785` — `Иммерсивное шоу Морфеус`
- `97365452` — `Морфеус СПБ`
- `97291492` — `Иммерсивный театр Морфеус - набережная реки Мойки, 28`
- `105771009` — `Морфеус - Малый Дровяной переулок, 6`

## Как хранить доступ

Чувствительные данные не держать в markdown.

Локальный файл:

- `/Users/Peter/Documents/Morpheus Metrics/.env.yandex_direct`

Рекомендуемые переменные:

```env
YANDEX_DIRECT_CLIENT_ID=d1877831b6124376a7f1a8c45f2527f3
YANDEX_DIRECT_CLIENT_SECRET=<SECRET>
YANDEX_DIRECT_ACCESS_TOKEN=<TOKEN>
```

Для отдельного SPB кабинета:

```env
YANDEX_DIRECT_SPB_CLIENT_ID=70a1dba4ad7148b4acdf000cdd093e13
YANDEX_DIRECT_SPB_CLIENT_SECRET=<SECRET>
YANDEX_DIRECT_SPB_ACCESS_TOKEN=<TOKEN>
```

Шаблон без секрета:

- `/Users/Peter/Documents/Morpheus Metrics/.env.yandex_direct.example`
- `/Users/Peter/Documents/Morpheus Metrics/.env.yandex_direct_spb.example`

## Схема подключения к рекламному кабинету

В проекте сейчас считаем, что у нас есть **два отдельных контура Яндекс.Директа**:

1. основной кабинет
   - env: `/Users/Peter/Documents/Morpheus Metrics/.env.yandex_direct`
   - используется для московского рекламного контура
2. отдельный SPB кабинет
   - env: `/Users/Peter/Documents/Morpheus Metrics/.env.yandex_direct_spb`
   - используется для петербургского рекламного контура

Для каждого кабинета храним отдельно:

- `CLIENT_ID`
- `CLIENT_SECRET`
- `ACCESS_TOKEN`

То есть логика подключения такая:

1. Определяем, в какой кабинет идём: `main` или `spb`.
2. Берём соответствующий env-файл.
3. Используем `ACCESS_TOKEN` как `Bearer` в запросах к:
   - `https://api.direct.yandex.com/json/v5/reports`
4. Если нужно получить новый токен:
   - открываем OAuth-ссылку с нужным `client_id`
   - логинимся тем Яндекс-аккаунтом, у которого есть доступ именно к нужному кабинету
   - сохраняем новый `access_token` в соответствующий env-файл
5. После этого обязательно делаем sanity check через `Reports API`.

Практическое правило:

- не смешивать московский и SPB токены
- не переиспользовать один env-файл для двух кабинетов
- при вопросах про расходы/клики/показы сначала явно фиксировать, **какой именно кабинет** нужен

Текущая привязка:

- `main` -> Москва / основной Direct-контур
- `spb` -> отдельный петербургский Direct-контур

## Что сейчас сохранено по SPB кабинету

По состоянию на `2026-05-02` в проекте уже сохранены:

- `ClientID`
- `Client secret`

Также уже сохранён и подтверждён:

- `SPB access token`

То есть SPB-контур теперь уже не просто prepared local config, а рабочая verified API session.

Подтверждённый sanity check для отдельного SPB кабинета:

- запрос к `https://api.direct.yandex.com/json/v5/reports` за `2026-04-20..2026-04-26` вернул `HTTP 200`
- в ответе пришли реальные кампании:
  - `поиск`
  - `РЕТАРГЕТ`
  - `sertcat.ru от 01.03.25`
  - `b2b спб`
  - `spb.morpheus-show.ru ДОП ТРАФИК — 2`

## Как получать токен

Для этого приложения:

```text
https://oauth.yandex.ru/authorize?response_type=token&client_id=d1877831b6124376a7f1a8c45f2527f3
```

Токен должен выдаваться под тем Яндекс-аккаунтом, у которого:

- есть доступ к нужному Direct-аккаунту
- уже одобрена заявка на Direct API

## Рабочий базовый тест

Минимальный sanity check:

```bash
curl -sS \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' \
  -H 'Accept-Language: ru' \
  -H 'Content-Type: application/json; charset=utf-8' \
  -H 'processingMode: auto' \
  -d '{
    "params": {
      "SelectionCriteria": {"DateFrom": "2026-04-01", "DateTo": "2026-04-25"},
      "FieldNames": ["CampaignName", "Date", "Cost", "Clicks", "Impressions"],
      "ReportName": "Direct API sanity check",
      "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
      "DateRangeType": "CUSTOM_DATE",
      "Format": "TSV",
      "IncludeVAT": "YES",
      "IncludeDiscount": "NO"
    }
  }' \
  'https://api.direct.yandex.com/json/v5/reports'
```

## Что уже видели в ответе

Уже подтверждены реальные строки с кампаниями вида:

- `Морфеус поиск горяч conv`
- `morpheus-show.ru ОКОЛОЦЕЛЕВЫЕ (СУДНЫЙ ДЕНЬ)`
- `morpheus-show.ru от 03.12.21 — ДОП ТРАФИК`
- `b2b поиск и сети (мск)`
- `b2b поиск33`
- `morpheus-show.ru turist`

И полями:

- `CampaignName`
- `Date`
- `Cost`
- `Clicks`
- `Impressions`

## Как правильно определять живые кампании

Важное практическое правило:

- для списка реально живых кампаний опираться в первую очередь на `Reports API`
- `Campaigns.get` использовать как вспомогательный endpoint для структуры и настроек

Почему:

- `Reports API` показывает кампании, по которым реально есть статистика за выбранный период
- это лучше совпадает с тем, что видно в UI Директа
- `Campaigns.get` может вернуть неполный или устаревший на вид набор кампаний относительно интерфейса

Рабочая процедура:

1. Сначала получить список кампаний через `Reports API` за нужный период.
2. Считать этот список основным источником для ответа на вопрос "какие кампании сейчас живые".
3. Потом при необходимости добирать детали через `Campaigns.get`:
   - `CounterIds`
   - `Type`
   - `Status`
   - `State`
4. Если `Reports API` и `Campaigns.get` расходятся, для аналитики расходов и активности доверять `Reports API`.

Минимальный запрос для списка живых кампаний:

```bash
curl -sS \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' \
  -H 'Accept-Language: ru' \
  -H 'Content-Type: application/json; charset=utf-8' \
  -H 'processingMode: auto' \
  -d '{
    "params": {
      "SelectionCriteria": {"DateFrom": "2026-03-27", "DateTo": "2026-04-26"},
      "FieldNames": ["CampaignId", "CampaignName"],
      "ReportName": "Campaign id name check",
      "ReportType": "CAMPAIGN_PERFORMANCE_REPORT",
      "DateRangeType": "CUSTOM_DATE",
      "Format": "TSV",
      "IncludeVAT": "YES",
      "IncludeDiscount": "NO"
    }
  }' \
  'https://api.direct.yandex.com/json/v5/reports'
```

На `2026-04-26` эта процедура дала такой актуальный список живых кампаний:

- `68138838` — `Морфеус поиск горяч conv`
- `75600775` — `morpheus-show.ru ОКОЛОЦЕЛЕВЫЕ (СУДНЫЙ ДЕНЬ)`
- `75600910` — `morpheus-show.ru turist`
- `119938884` — `morpheus-show.ru от 03.12.21 — ДОП ТРАФИК`
- `701616937` — `b2b поиск и сети (мск)`
- `706925235` — `b2b поиск33`

## Как определять географию в Direct

В Direct у нас уже подтвердились как минимум два разных гео-среза, и они отвечают
на разные вопросы.

### 1. `TargetingLocationName`

Использовать, когда нужен ответ на вопрос:

- где кампания таргетируется
- какие гео-локации стоят на стороне рекламного кабинета

Это скорее **география таргетинга**, а не обязательно география реальных
пользователей.

Практический вывод:

- этот срез полезен для понимания настройки кампаний
- но он может не совпадать с географией фактических визитов на сайт

### 2. `LocationOfPresenceName`

Использовать, когда нужен ответ на вопрос:

- где физически находился пользователь, который увидел или кликнул объявление

Это уже ближе к **реальной географии показов и кликов**.

Практический вывод:

- для вопроса "были ли показы/клики по Санкт-Петербургу" этот срез оказался
  полезнее, чем `TargetingLocationName`
- именно через `LocationOfPresenceName` мы увидели маленький, но реальный
  петербургский хвост по показам и кликам

### Какой срез брать в каком случае

- вопрос про настройку кампании -> `TargetingLocationName`
- вопрос про фактическую географию аудитории показов/кликов -> `LocationOfPresenceName`
- вопрос про географию уже состоявшихся визитов на сайт -> это уже не Direct, а
  **Yandex Metrica**

### Важная граница Direct

Через Direct можно доставать:

- показы
- клики
- расходы
- географию показов и кликов

Но через Direct нельзя достать:

- визиты сайта
- географию сессий сайта

Для этого нужен Metrica API.

## Важный нюанс по Cost

`Cost` приходит в сыром API-формате и перед использованием в дэшбордах его нужно
нормализовать до обычных рублей.

Перед построением витрин это значение лучше всегда прогонять через проверочную
нормализацию на известном периоде.

## Revenue не берем из Yandex Direct

По состоянию на `2026-06-02` проверено, что `Reports API`
`CAMPAIGN_PERFORMANCE_REPORT` поле `Revenue` и goal-specific поля вида
`Revenue_<goal_id>_<attribution_model>` не воспроизводят реальные суммы заказов
из интерфейса и экспорта Директа. Для части кампаний API возвращает статическую
ценность цели вместо фактической суммы заказа.

Правило fact layer:

- `Yandex Direct` является primary source для `Marketing costs`, clicks,
  impressions и campaign-level рекламной статистики.
- Доходы от перформанс-маркетинга не берем из Direct Reports API.
- Доходы от перформанс-маркетинга берем из `Yandex Metrica`; см.
  [Yandex Metrica](./yandex_metrica.md).

## Практический следующий шаг

Когда будем строить dashboard:

- сначала сделать маленький extractor `Reports API -> raw table`
- потом нормализовать `Cost`
- и только после этого собирать витрины расходов по дням / кампаниям / направлениям
- revenue для performance-строки присоединять из `Yandex Metrica`, не из Direct
