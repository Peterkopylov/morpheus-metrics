# ERP Survey Satisfaction Logic

Рабочая заметка по тому, как мы сейчас интерпретируем зрительский опрос из ERP
`POST /survey/satisfaction`.

Статус на `2026-05-02`.

## Источник

Endpoint:

- `POST /survey/satisfaction`

В ответе на каждой записи есть:

- `seance_id`
- `seance_name`
- `seance_date`
- `answers`
- `actors`

Главное поле для факт-слоя:

- `answers`

## Что уже точно поняли по вопросам

### Question 1

Поле:

- `answers["1"]`

Что это:

- оценка спектакля по шкале `1..5`

Как используем:

- `Number of show rating responses`
  - count непустых ответов по `answers["1"]`
- `Sum of post-show ratings`
  - сумма числовых ответов `answers["1"]`

Это позволяет потом считать:

- среднюю оценку спектакля как derived metric:
  - `Sum of post-show ratings / Number of show rating responses`

### Question 2

Поле:

- `answers["2"]`

Что это:

- “откуда узнали”

Примеры реальных значений:

- `Друзья, Знакомые`
- `Я.Афиша`
- `Яндекс / Google`
- `Соц. сети`
- `Карты Яндекс, Google, 2ГИС`
- `Подарили сертификат`
- `Реклама в интернете`
- `Сайт MORPHEUS`

Как используем:

- `Number of source-attribution responses`
  - count ответов по нормализованной категории

Важно:

- в факт-слое это **count**
- derived `Source share` считаем позже поверх count'ов

### Question 3

Поле:

- `answers["3"]`

Что это:

- бинарный ответ категории `Да/Нет`

Как используем:

- `Number of question 3 responses`
  - count ответов по категории и show

### Question 4

Поле:

- `answers["4"]`

Что это:

- категориальный ответ, сейчас наблюдали:
  - `Конечно`
  - `Не сейчас`

Как используем:

- `Number of question 4 responses`
  - count ответов по категории и show

## Show binding

Все survey-ответы можно привязывать к конкретному шоу через:

- `seance_name`

В fact layer это пишется как:

- `show_name`

Рабочая канонизация шоу совпадает с остальными ERP weekly imports:

- `Ответ Гиппократа`
- `До свадьбы доживёт`
- `22'07`
- `ВДОХ`
- `Иное место`
- `Поезд, Чехов, два орла`
- `Загадка Амулета`
- `Судный день`

## Какие метрики мы импортируем еженедельно

### 1. Number of post-show survey responses

Смысл:

- count записей, где хотя бы один из `answers[1..4]` непустой

Разрезы:

- `general`
- `show`

### 2. Number of show rating responses

Смысл:

- count непустых `answers["1"]`

Разрезы:

- `show`

### 3. Sum of post-show ratings

Смысл:

- сумма числовых `answers["1"]`

Разрезы:

- `show`

### 4. Number of source-attribution responses

Смысл:

- count ответов `answers["2"]` по нормализованной категории

Разрезы:

- `general + category`
- `show + category`

Категория хранится в:

- `value_text`

### 5. Number of question 3 responses

Смысл:

- count ответов `answers["3"]` по категории

Разрезы:

- `show + category`

Категория хранится в:

- `value_text`

### 6. Number of question 4 responses

Смысл:

- count ответов `answers["4"]` по категории

Разрезы:

- `show + category`

Категория хранится в:

- `value_text`

## Где это реализовано

- script:
  - [import_erp_survey_satisfaction_weekly_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_erp_survey_satisfaction_weekly_to_fact.py)
- report:
  - [erp_survey_satisfaction_weekly_to_fact_import_report.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/erp_survey_satisfaction_weekly_to_fact_import_report.csv)

## Последний подтверждённый weekly pass

Период:

- `2026-04-20` -> `2026-04-26`

Результат:

- inserted:
  - `150`
- skipped:
  - `0`

### Metric counts in that pass

- `Number of post-show survey responses`:
  - `15`
- `Number of show rating responses`:
  - `13`
- `Sum of post-show ratings`:
  - `13`
- `Number of source-attribution responses`:
  - `65`
- `Number of question 3 responses`:
  - `22`
- `Number of question 4 responses`:
  - `22`

## Important model choice

Для `source attribution` в факт-слое **не** пишем `share` как базовую метрику.

Пишем:

- `Number of source-attribution responses`

А derived `Source share` считаем потом из:

- `source_count / total_nonempty_answers_q2`

## Next possible step

Когда захотим развить этот слой:

- добавить derived `Average post-show rating`
- добавить derived `Source share`
- если понадобится, завести русские labels / normalized enums для Q3/Q4 categories
