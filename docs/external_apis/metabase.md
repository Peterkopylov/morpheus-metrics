# Metabase

Неофициальный, но рабочий operational note для нашего внутреннего Metabase.

## URL

- `https://metabase.134.122.83.160.sslip.io`
- внутренний прямой URL контейнера: `http://134.122.83.160:3001`

## Какой доступ уже подтверждён

- вход под пользователем `peter.kopylov@gmail.com` работает
- API key работает для `GET /api/dashboard`
- через Metabase API уже успешно менялись живые dashboard objects

## Где хранить секрет

Секретный API key не держим в markdown.

Локальный файл для работы из проекта:

- `.env.metabase`

Шаблон:

- `.env.metabase.example`

Оба файла предназначены для локального использования, а `.env.metabase` добавлен в `.gitignore`.

## Что сейчас важно помнить

- ключ называется `Codex`
- ключ валиден и был проверен живым запросом к `/api/dashboard`
- для автоматических правок Metabase лучше использовать API key, а не логин/пароль и session
- новые dashboard/card объекты по умолчанию не создаём в `root` (`Наша аналитика`)
- для создания новых объектов нужно явно передавать `--metabase-collection-id`
- root допускается только при осознанном явном opt-in через `--allow-root`

## Полезные dashboard IDs

- `4` — `Moscow Weekly Metrics Charts`
- `5` — `SPB Weekly Metrics Charts`
- `3` — `Weekly Metrics YoY`
- `7` — `Weekly Metrics Latest Comparison`
- `14` — `TEMP Выкупленность по сеансам — Поезд, Чехов, два орла`
- `16` — `Weekly Metrics YoY (fact)`
- `17` — `Moscow Weekly Metrics Charts (fact)`
- `18` — `SPB Weekly Metrics Charts (fact)`

## Полезные collection IDs

- `9` — `Общедоступные`
- `11` — `Archive` (внутри `Общедоступные`)
- `12` — `Tech` (внутри `Общедоступные`)

## Полезные card / object notes

- dashboard `14`
  - card `191`
  - URL: `https://metabase.134.122.83.160.sslip.io/dashboard/14`
  - source table: `tmp_erp_show_seance_buyout_snapshot`

## Что уже сделано через API

- добавлены status cards на weekly dashboards Москвы и СПб
- layout обоих дэшбордов был обновлён через Metabase API
- создан dashboard `Weekly Metrics Latest Comparison` с двумя latest-week таблицами для Москвы и СПб
- созданы fact-based аналоги weekly dashboards:
  - `Weekly Metrics YoY (fact)`
  - `Moscow Weekly Metrics Charts (fact)`
  - `SPB Weekly Metrics Charts (fact)`
- создан временный dashboard выкупленности по сеансам для нового спектакля `Поезд, Чехов, два орла`
- добавлен скрипт [`scripts/serving/create_metabase_weekly_technical_dashboard.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/serving/create_metabase_weekly_technical_dashboard.py) для техпроверки последней загруженной недели
- для seance buyout dashboard настроен отдельный hourly snapshot refresh через `/etc/cron.d/tmp_erp_show_seance_buyout_refresh`
- weekly dashboard family разложена по shared collections:
  - канонические dashboards живут в `Общедоступные`
  - legacy duplicates живут в `Общедоступные/Archive`
  - backing cards этих dashboards спрятаны в `Общедоступные/Tech`

## Служебные скрипты

- [`scripts/reorganize_metabase_collections.py`](/Users/Peter/Documents/Morpheus%20Metrics/scripts/reorganize_metabase_collections.py) — массово переносит dashboards и их backing cards по collection paths
