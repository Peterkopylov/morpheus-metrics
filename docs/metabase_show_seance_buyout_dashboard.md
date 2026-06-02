# Metabase Show Seance Buyout Dashboard

Временный operational-контур для дэшборда выкупленности по сеансам конкретного спектакля.

Статус на `2026-05-16`.

## Что показывает

Таблица вида:

- `День недели`
- `Сеанс`
- `Количество купленных на него билетов`
- `Актуально на сеансе`

Metabase object:

- dashboard id:
  - `14`
- card id:
  - `191`
- URL:
  - `https://metabase.134.122.83.160.sslip.io/dashboard/14`

Горизонт:

- ближайшие `31` день вперёд от момента обновления snapshot

Источник:

- `ERP /shows/get` — список будущих сеансов
- `ERP /tickets/by-sell` — реальные проданные билеты, джойн по `seance_id = show_id`
- `Yandex Tickets / crm.order.list` — для корректировки актуальной посадки при переносах между сеансами

Важно:

- поле `tickets_count` в `shows/get` не используем как выкупленность
- для нового спектакля `Поезд, Чехов, два орла` оно сейчас выглядит как вместимость (`6`), а не как факт продаж
- `Количество купленных на него билетов` остаётся историей платных продаж
- `Актуально на сеансе` считает текущую посадку с учётом zero-sum переносов:
  - активные заказы считаются как seats on seance
  - если найден более поздний `0 RUB` заказ того же клиента на такое же количество билетов на другой сеанс, это трактуется как перенос
  - в таком случае seats снимаются со старого сеанса и остаются на новом

## Скрипты

Обновление snapshot-таблицы:

- [refresh_tmp_erp_show_seance_buyout_snapshot.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/refresh_tmp_erp_show_seance_buyout_snapshot.py)

Создание Metabase dashboard:

- [create_metabase_tmp_erp_show_seance_buyout_dashboard.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/create_metabase_tmp_erp_show_seance_buyout_dashboard.py)

## Таблица в Postgres

- `tmp_erp_show_seance_buyout_snapshot`

Это temporary snapshot table, её можно безопасно пересоздавать.

## Автообновление

На сервере настроен hourly refresh:

- cron file:
  - `/etc/cron.d/tmp_erp_show_seance_buyout_refresh`
- расписание:
  - `37 * * * *`
- script:
  - `/opt/analytics/parser/refresh_tmp_erp_show_seance_buyout_snapshot.py`
- log:
  - `/var/log/tmp_erp_show_seance_buyout_refresh.log`

## Базовый запуск

```bash
python3 scripts/refresh_tmp_erp_show_seance_buyout_snapshot.py \
  --database-url 'postgresql://admin:strongpassword@134.122.83.160:5432/analytics' \
  --show-name 'Поезд, Чехов, два орла'
```

```bash
python3 scripts/create_metabase_tmp_erp_show_seance_buyout_dashboard.py \
  --metabase-url 'http://134.122.83.160:3001' \
  --metabase-api-key "$METABASE_API_KEY" \
  --metabase-database-id 2 \
  --unit b2c_moscow \
  --show-name 'Поезд, Чехов, два орла'
```

## Когда использовать

- разбор выкупленности конкретного нового спектакля
- обсуждение, какие сеансы продавать/усиливать на горизонте месяца
- быстрый operational dashboard, пока не собрана более общая витрина по слотам и сеансам
