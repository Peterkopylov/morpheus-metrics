# ERP Salary Variable Logic

Рабочая заметка по тому, как мы сейчас интерпретируем `Costs - Salary variable` из ERP.

Статус на `2026-05-02`.

## Что считаем источником

Основные endpoint'ы:

- `POST /salaries/period`
- `POST /bonuses`

Вспомогательные reference endpoint'ы:

- `POST /payments`
- `GET /salaries`
- `GET /salaries/latest`

## Базовая логика

Для weekly `Costs - Salary variable` используем:

- `salaries/period`
  - как основное начисление за период
- `bonuses`
  - как часть той же variable salary

Что **не** используем как основной факт:

- `payments`
  - это cash payout, а не базовое начисление за неделю

## Как строим weekly facts

### 1. Show-level

Для разреза `show` берём:

- `salary_payed` из `salaries/period.seances`

И суммируем по каноническому названию шоу.

То есть `show`-строки отражают только ту часть variable salary, которую ERP
даёт честно привязанной к конкретному сеансу / шоу.

### 2. Bonus allocation

Бонусы добавляем к `show` только если:

- у bonus есть `seance_id`
- `seance_id` можно сматчить к show
- название show канонизируется в наш каталог

Если этого нет, bonus **не раскладываем искусственно по шоу**.

### 3. General

Для `general` строки по городу берём:

- `salary_total = sum(shows_income)` из `salaries/period`
- `bonus_total = sum(amount)` из `bonuses`

И считаем:

- `general = salary_total + bonus_total`

Это значит:

- `general` всегда включает весь bonus tail
- `show` не обязан суммироваться в `general`

## Важное правило

`show`-разрез и `general`-разрез здесь **не обязаны совпадать по сумме**.

Причина:

- часть bonus строк приходит без `seance_id`
- их нельзя надёжно раскидать по шоу
- поэтому они сидят только в `general`

Это ожидаемое поведение, а не ошибка.

## Последний подтверждённый weekly pass

Период:

- `2026-04-20` -> `2026-04-26`

### Москва

- `general`:
  - `281 673`
- нераспределённый bonus tail:
  - `7 410`

### СПб

- `general`:
  - `177 050`
- нераспределённый bonus tail:
  - `8 700`

## Где это реализовано

- script:
  - [import_erp_salary_variable_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_erp_salary_variable_weekly_to_fact.py)
- report:
  - [erp_salary_variable_weekly_to_fact_import_report.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/erp_salary_variable_weekly_to_fact_import_report.csv)

## Какой смысл у payload

В `fact_metric_observation.payload` сейчас пишем:

- для `show`-строк:
  - `salary_component`
  - `bonus_component_allocated`
  - `unit_unallocated_bonus_total`
- для `general`-строк:
  - `salary_total`
  - `bonus_total`
  - `bonus_allocated_to_shows`
  - `bonus_unallocated_tail`

Это нужно, чтобы потом можно было быстро проверить, из чего сложилось значение.

## Следующий возможный шаг

Если захотим улучшить show-level split, можно отдельно исследовать:

- можно ли часть bonus без `seance_id` привязать к шоу по `reason`
- или надо осознанно оставить это только в `general`
