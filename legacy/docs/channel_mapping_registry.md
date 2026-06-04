# Channel Mapping Registry

Единая таблица соответствий для маркетинговых каналов между:

- canonical warehouse taxonomy
- `Yandex.Metrica`
- `ERP survey answers[2]` (`откуда узнали`)

Файл-источник:

- [generated/channel_mapping_registry.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/channel_mapping_registry.csv)

## Canonical system channels

Текущий канонический набор `marketing_channel_names`:

- `perfomance`
- `organic`
- `social`
- `partners`
- `pr`
- `friends`
- `referral`
- `email`
- `other`

Важно:

- `partners` = `Агрегаторы / партнеры`
- `pr` = отдельный канал `PR`
- эти два канала нельзя схлопывать друг в друга

## Current Mapping Notes

### Yandex.Metrica

Текущая нормализация одинаковая в:

- [scripts/import_yandex_metrica_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_yandex_metrica_weekly_to_fact.py)
- [scripts/import_yandex_metrica_tracked_purchase_visits_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_yandex_metrica_tracked_purchase_visits_weekly_to_fact.py)

Ключевые решения:

- `ad + ya_direct` -> `perfomance`
- `ad + ya_undefined` -> `perfomance`
- paid social ad-engines тоже -> `perfomance`
- `social` и `messenger` -> `social`
- `direct`, `internal` -> `organic`
- `saved`, `undefined` -> `other`

Открытые вопросы:

- нужен ли отдельный bucket для `internal`
- не слишком ли агрессивно весь paid social схлопывается в `perfomance`
- стоит ли `direct` из Метрики хранить отдельно от `organic`

### Surveys

Нормализация ответов `answers[2]` сейчас живет в:

- [scripts/import_erp_survey_satisfaction_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_erp_survey_satisfaction_weekly_to_fact.py)

А dashboard-level mapping survey category -> canonical channel сейчас зашит в:

- [sql/create_weekly_marketing_operational_view.sql](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_weekly_marketing_operational_view.sql)

Ключевые решения:

- `Яндекс Афиша` -> `partners`
- `От друзей` -> `friends`
- `Реклама в интернете` -> `perfomance`
- `Яндекс / Google` -> `referral`
- `Карты Яндекс, Google, 2ГИС` -> `referral`
- `Наш сайт` -> `organic`
- `Подарили сертификат` -> `friends`

Открытые вопросы:

- `Наш сайт` может быть closer to brand/direct than to organic
- `Карты ...` можно вынести в отдельный discovery/local bucket, если такой канал появится в canonical scope
- `friends` и `referral` теперь разделены семантически, и это стоит отдельно проверить на пользовательских кейсах

## Recommendation

Сейчас registry уже полезен как source of truth для обсуждения и ревью mapping-решений.

Следующий хороший шаг:

1. перестать дублировать mapping руками в SQL/Python
2. читать survey channel mapping из одного registry-файла
3. отдельно решить, хотим ли мы расширять canonical taxonomy (`pr`, `internal`, `brand/direct`, `maps/discovery`)
