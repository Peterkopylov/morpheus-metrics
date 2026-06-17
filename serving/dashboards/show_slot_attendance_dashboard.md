# Dashboard по слотам и посещаемости

Статус на `2026-06-17`.

## Что сделано

Для нового public dashboard собран seance-level snapshot:

- [refresh_erp_show_slot_attendance_snapshot.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/refresh_erp_show_slot_attendance_snapshot.py)

И serving layer:

- [create_show_slot_attendance_dashboard_base.sql](/Users/Peter/Documents/Morpheus%20Metrics/sql/create_show_slot_attendance_dashboard_base.sql)
- [rebuild_show_slot_attendance_dashboard_base.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/rebuild_show_slot_attendance_dashboard_base.py)

Для публикации в Metabase добавлен builder:

- [create_metabase_show_slot_attendance_dashboard.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/create_metabase_show_slot_attendance_dashboard.py)

## Доступ

- Metabase collection: `Общедоступные`
- collection id: `9`
- Москва:
  - dashboard id: `25`
  - card id: `340`
  - URL:
    - `https://metabase.134.122.83.160.sslip.io/dashboard/25`
- СПб:
  - dashboard id: `26`
  - card id: `339`
  - URL:
    - `https://metabase.134.122.83.160.sslip.io/dashboard/26`

Companion dashboards:

- Москва — среднее число гостей по слотам:
  - dashboard id: `28`
  - card id: `342`
  - URL:
    - `https://metabase.134.122.83.160.sslip.io/dashboard/28`
- СПб — среднее число гостей по слотам:
  - dashboard id: `27`
  - card id: `341`
  - URL:
    - `https://metabase.134.122.83.160.sslip.io/dashboard/27`

## Источник

- `ERP /shows/get`

Snapshot сохраняет по каждому сеансу:

- город / business unit
- название спектакля
- дата и время сеанса
- фактических гостей (`guests`)
- полную посадку (`tickets_count`)
- площадку и зал
- флаг отмены

## Что показывает dashboard

Отдельный dashboard для:

- `Москва`
- `СПб`

Фильтры:

- `Период с`
- `Период по`
- `Спектакль` — множественный выбор

Layout:

- строки:
  - `Время`
- колонки:
  - `1/пн ... 7/вск`

Значение в ячейке:

- `SUM(guests) / SUM(capacity_tickets) * 100`

Текущий live-format:

- `83% (6)` = посещаемость слота и число спектаклей в выборке

Companion variant:

- `5.8 (6)` = среднее число гостей на спектакль в слоте и число спектаклей в выборке

Отменённые сеансы:

- включаются в denominator
- всегда дают `0` в guests numerator
- то есть cancelled show снижает итоговую посещаемость слота, а не исчезает из выборки

Это не среднее из процентных значений по сеансам, а ratio-of-sums по выбранной группе. Так результат остаётся математически корректным при смешении нескольких спектаклей, дат и слотов.

## Model choice

`view`:

- seance-level shaping для slot matrix
- fixed weekday columns
- city-specific dashboard publishing

`not calculated`:

- reusable canonical metric по слотам пока не вводим, потому что логика сейчас специфична именно для этого dashboard shape и строится на seance-level snapshot, которого раньше не было в calculated contour

## Операционный запуск

1. Обновить snapshot:

```bash
python3 scripts/refresh_erp_show_slot_attendance_snapshot.py \
  --database-url 'postgresql://admin:strongpassword@134.122.83.160:5432/analytics' \
  --date-from '2026-01-01' \
  --date-to '2026-06-17'
```

2. Пересобрать view:

```bash
python3 scripts/serving/rebuild_show_slot_attendance_dashboard_base.py \
  --database-url 'postgresql://admin:strongpassword@134.122.83.160:5432/analytics'
```

3. Создать dashboard в Metabase:

```bash
python3 scripts/serving/create_metabase_show_slot_attendance_dashboard.py \
  --metabase-url 'http://134.122.83.160:3001' \
  --metabase-api-key "$METABASE_API_KEY" \
  --metabase-database-id 2 \
  --metabase-collection-id 9 \
  --show-name-field-id <FIELD_ID_FOR_SHOW_NAME> \
  --unit b2c_moscow
```

```bash
python3 scripts/serving/create_metabase_show_slot_attendance_dashboard.py \
  --metabase-url 'http://134.122.83.160:3001' \
  --metabase-api-key "$METABASE_API_KEY" \
  --metabase-database-id 2 \
  --metabase-collection-id 9 \
  --show-name-field-id <FIELD_ID_FOR_SHOW_NAME> \
  --unit b2c_spb
```

Companion average-guests dashboards:

```bash
python3 scripts/serving/create_metabase_show_slot_attendance_dashboard.py \
  --metabase-url 'http://134.122.83.160:3001' \
  --metabase-api-key "$METABASE_API_KEY" \
  --metabase-database-id 2 \
  --metabase-collection-id 9 \
  --show-name-field-id <FIELD_ID_FOR_SHOW_NAME> \
  --unit b2c_moscow \
  --value-mode average_guests
```

```bash
python3 scripts/serving/create_metabase_show_slot_attendance_dashboard.py \
  --metabase-url 'http://134.122.83.160:3001' \
  --metabase-api-key "$METABASE_API_KEY" \
  --metabase-database-id 2 \
  --metabase-collection-id 9 \
  --show-name-field-id <FIELD_ID_FOR_SHOW_NAME> \
  --unit b2c_spb \
  --value-mode average_guests
```

`show_name_field_id` должен указывать на поле `show_name` в `show_slot_attendance_dashboard_base` после sync metadata в Metabase.

## Scope note

- historical cutoff:
  - only data from `2026-01-01` and later is intended for this dashboard

- time granularity:
  - user-facing analysis can stay at weekly-or-broader decision level
  - backend still keeps seance-level timestamps, because without exact seance datetime we cannot correctly place values into `время x день недели`
