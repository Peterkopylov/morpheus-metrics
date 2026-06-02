# Yandex Tickets as Primary Source for Ticket Sales

Архитектурное решение, зафиксированное на `2026-05-02`.

## Решение

Для вопросов и метрик, связанных именно с **продажей билетов**, primary source
должен быть **Yandex Tickets API**, а не ERP.

Это относится к B2C билетным продажам в следующих разрезах:

- `Revenue`
- `Number of tickets`
- `Number of orders`

И особенно в таких breakdown'ах:

- по `show`
- по `agent / partner`

## Почему

Недавние сверки по Москве за неделю `2026-04-20 .. 2026-04-26` показали:

1. `ERP /tickets/by-sell` не всегда идеально совпадает с Яндекс.Билетами на уровне
   `order_id`.
2. Есть как минимум три источника расхождения:
   - в Яндекс.Билетах заказ уже `status = 0`, а в ERP он остаётся положительным;
   - ERP иногда хранит неполный состав билетов по живому заказу;
   - ERP может вернуть отдельные записи вне requested периода, если без доп. фильтра
     довериться только самому endpoint.
3. Для agent/show sales logic Яндекс.Билеты ближе к system of record.

Итог:

- для operational / near-real-time контуров ERP полезен;
- для билетных sales-вопросов primary truth должен быть Yandex Tickets.

## Практическое правило

### Что берём из Yandex Tickets

По возможности именно из Яндекс.Билетов строим:

- weekly / monthly sales by show
- weekly / monthly sales by agent
- revenue / tickets / orders по B2C билетным продажам

Рабочая логика:

- `crm.order.list`
- фильтр на нужный период по `order_date`
- `sold-only` логика:
  - исключать `status = 0`
  - исключать `is_returned = 1`
- `event_id -> crm.report.event -> event_name`

### Что остаётся за ERP

ERP остаётся useful для:

- `Number of shows`
- `Number of shows cancelled`
- `Number of show visitors`
- survey / protocol / quality layers
- salary / bonus layers
- fast operational checks, если нужен near-real-time feed

А также как:

- fallback / reference layer
- временный substitute, пока нет нужного Yandex Tickets кабинета

## Текущий rollout status

На момент решения:

- Москва в Yandex Tickets уже подтверждена как рабочий контур;
- СПб кабинет ещё не подключён в проекте.

Пока не подключён СПб:

- ticket-sales ideology уже считается утверждённой;
- для СПб временно можно жить на ERP/reference logic;
- после появления личного кабинета СПб те же sales-метрики нужно перевести на
  Yandex Tickets.

## Что это значит для нового факт-слоя

Для ticket-sales метрик надо мыслить так:

- `primary_source = yandex_tickets`
- `secondary_source = erp`
- `manual_table = reference / reconciliation / legacy logic`

То есть если вопрос звучит как:

- “сколько билетов продано”
- “сколько заказов”
- “какая выручка от билетов”
- “по каким агентам”
- “по каким спектаклям”

то default answer path должен начинаться с **Yandex Tickets**.
