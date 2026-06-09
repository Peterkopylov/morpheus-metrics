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

## Полезные dashboard IDs

- `4` — `Moscow Weekly Metrics Charts`
- `5` — `SPB Weekly Metrics Charts`
- `3` — `Weekly Metrics YoY`
- `7` — `Weekly Metrics Latest Comparison`
- `8` — `TEMP ERP Sales KPI Prototype`
- `9` — `TEMP ERP Sellout Next 30 Days`

## Что уже сделано через API

- добавлены status cards на weekly dashboards Москвы и СПб
- layout обоих дэшбордов был обновлён через Metabase API
- создан dashboard `Weekly Metrics Latest Comparison` с двумя latest-week таблицами для Москвы и СПб
- создан dashboard `TEMP ERP Sales KPI Prototype` на временной ERP snapshot table
- создан dashboard `TEMP ERP Sellout Next 30 Days` на временной ERP future-shows snapshot table

## TEMP ERP Sellout Next 30 Days

Dashboard:

- `9` — `TEMP ERP Sellout Next 30 Days`

Назначение:

- быстрый operational dashboard по ближайшим `30` дням
- строки = даты
- колонки = аббревиатуры спектаклей
- для каждого спектакля на дату показываются:
  - число сеансов
  - `%` выкупленности

Источник:

- временная таблица `tmp_erp_sellout_next_30d_snapshot`

Как собирается snapshot:

- будущие сеансы берутся из `ERP /shows/get`
- для каждого будущего сеанса берутся:
  - `show_id`
  - `event_title`
  - `show_start`
  - `tickets_count`
- реальные проданные билеты считаются из `ERP /tickets/by-sell`
- match:
  - `tickets.by_sell.seance_id = shows.get.show_id`
- sold count:
  - количество ticket rows с `total > 0`

Как считается `%`:

- по каждой дате и аббревиатуре спектакля
- `sold_tickets = sum(sold_tickets_orders)`
- `max_tickets = sum(tickets_count)`
- `% = sold_tickets / max_tickets`

Технические файлы:

- `scripts/refresh_tmp_erp_sellout_next_30d_snapshot.py`
- `scripts/create_metabase_tmp_erp_sellout_next_30d_dashboard.py`

Автообновление:

- на сервере настроен hourly cron
- файл: `/etc/cron.d/tmp_erp_sellout_next_30d_refresh`
- лог: `/var/log/tmp_erp_sellout_next_30d_refresh.log`
- расписание:

```cron
22 * * * * root /usr/bin/python3 /opt/analytics/parser/refresh_tmp_erp_sellout_next_30d_snapshot.py >> /var/log/tmp_erp_sellout_next_30d_refresh.log 2>&1
```
