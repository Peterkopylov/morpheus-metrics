# ERP Endpoint -> Metric Mapping

Рабочая карта соответствия между ERP endpoint'ами и нашим каталогом метрик.

Статус на `2026-05-02`.

Проверка делалась на живых ответах ERP за неделю:

- `2026-04-20` -> `2026-04-26`

## Принцип

В этой таблице:

- `Direct source` — endpoint можно использовать как прямой source для текущего fact layer.
- `Derived / reference` — endpoint полезен, но скорее как вспомогательный или для следующего слоя.
- `No current mapping` — endpoint пока не даёт метрику из текущего каталога 1-в-1.

## Mapping

| Endpoint | Что реально лежит | Наши метрики | Статус | Комментарий |
| --- | --- | --- | --- | --- |
| `POST /tickets/by-sell` | продажи билетов по дате продажи, `order_id`, `agent_id`, `total`, `seance_id`, `status` | `Revenue`, `Number of tickets`, `Number of orders` | `Direct source` | Основной weekly sales endpoint. В active weekly logic `status = 0` трактуем как отмену и исключаем такие строки; `status != 0` считаем активной продажей. |
| `POST /shows/get` | список сеансов, `event_title`, `cancelled`, `guests`, `tickets_count`, `tickets_cert`, `tickets_invite` | `Number of shows`, `Number of shows cancelled`, `Number of show visitors`, часть `Number of tickets/Revenue` по `show` через join | `Direct source` | Рабочий join: `tickets.seance_id = shows.show_id`. |
| `POST /tickets/by-seance` | билеты на сеансы за даты сеанса, а не даты продажи | потенциально `Number of tickets` / `Revenue` по факту проведения | `Derived / reference` | Useful для operational checks и attended/show-date views, но не основной source для weekly sales. |
| `POST /schedule` | расписание сеансов, назначенные актёры, доступные актёры, отмена | `Scheduling complexity` (в будущем), возможно incident/support metrics | `Derived / reference` | Структура богатая, но прямой формулы к текущей метрике ещё нет. |
| `POST /schedule/generate` | текстовая сводка расписания для объявлений | нет | `No current mapping` | Полезно людям, но не факт-слой. |
| `POST /actors/schedule/unavailable/get` | отметки “не могу” по актёру на неделю | нет в текущем source catalog | `Derived / reference` | Может пригодиться для отдельного HR / staffing layer. |
| `POST /schedule/personal` | личное расписание актёра: в каких спектаклях участвует | нет | `Derived / reference` | Useful для support/debugging salary logic. |
| `POST /recordings` | список загруженных записей спектаклей | нет | `No current mapping` | Больше похоже на ops / AI-processing layer. |
| `GET /actors` | справочник актёров с alias, ставками и show-rate blocks | нет напрямую | `Derived / reference` | Справочник для join'ов в salary/staffing logic. |
| `POST /salaries/period` | по каждому alias: `seances`, `shows_income`, `bonuses`, `bonus_income`, `balance`, `errors` | `Costs - Salary variable` | `Direct source candidate` | Лучший кандидат на weekly variable salary costs. Нужна бизнес-формула: что именно суммируем в факт. |
| `POST /payments` | фактические выплаты зарплаты | `Costs - Salary variable` или reference to cash-out | `Derived / reference` | Это не начисление, а выплата. Вероятно useful как сверка и cash timing, не как основной accrual fact. |
| `POST /bonuses` | дополнительные выплаты (`Иное`), сумма и reason | `Costs - Salary variable` | `Direct source candidate` | Скорее компонент variable salary costs, который надо добавлять к основной salary logic. |
| `GET /salaries` | история изменения ставок | нет напрямую | `Derived / reference` | Useful для backfill и rate audit, но не weekly fact сам по себе. |
| `GET /salaries/latest` | актуальные ставки по каждому alias и шоу/роли | нет напрямую | `Derived / reference` | Важно: рабочий метод именно `GET`, не `POST`. Useful для расчёта salary accrual. |
| `GET /metrics` | “метрики справедливости”: `appointed_to_all`, `appointed_to_availability`, `available_to_all`, `available_to_all_avg` | нет в текущем каталоге | `No current mapping` | Это staffing fairness / involvement metrics. Можно вынести в будущий people-performance layer. |
| `POST /survey/satisfaction` | зрительский опрос: `answers`, `seance_name`, `seance_date`, cast | `Quality - External`, `Number of source-attribution responses` | `Direct source candidate` | Реально заполнен. Уже подтверждено, что `answers[2]` = “откуда узнали”, а не только satisfaction. |
| `POST /survey/answers/get-by-survey` | ответы актёров: `contact`, `unity`, `discovery`, `how_to_find`, `lost_ones`, `gold_standard`, `dead_count`, `show` | `Quality - Internal`, `Number of deaths on OG`, quality ratios по OG | `Direct source candidate` | Это actor / protocol survey. Поле `how_to_find` по факту не маркетинговый source, а внутрисюжетный ответ. Для метрики source-attribution не использовать. |
| `POST /survey/answers/get-summary` | агрегаты: `overall_show_summary`, `master_show_summary`, `master_show_count`, ... | `Quality - Internal` | `Direct source candidate` | Это summary layer поверх actor survey. Похоже на уже посчитанные качества/оценки по мастерам и шоу. |

## Что уже выглядит особенно сильным

### 1. Sales / operations

Самые надёжные и уже рабочие:

- `tickets/by-sell`
- `shows/get`

Они покрывают:

- `Revenue`
- `Number of tickets`
- `Number of orders`
- `Number of shows`
- `Number of shows cancelled`
- `Number of show visitors`

Отдельное наблюдение по состоянию на `2026-05-16`:

- новый московский спектакль `Поезд, Чехов, два орла` уже виден в:
  - `POST /shows/get`
  - `POST /schedule` как сокращение `ПЧ`
- это значит, что для ERP-канонизации шоу его уже нужно держать в `SHOW_CANON`, даже если weekly sales/survey history пока короткая.

### 2. Variable salary costs

Самый сильный набор кандидатов:

- `salaries/period`
- `bonuses`
- `payments`
- reference:
  - `salaries`
  - `salaries/latest`

Отдельная рабочая логика зафиксирована здесь:

- [erp_salary_variable_logic.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/erp_salary_variable_logic.md)
- [erp_site_widget_comparison.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/erp_site_widget_comparison.md)

Рабочая гипотеза:

- `salaries/period` — базовое начисление / what is earned for period
- `bonuses` — дополнительная переменная часть
- `payments` — cash payout, useful for reconciliation but not necessarily the base fact itself

### 3. Internal / survey metrics

Сейчас лучшие кандидаты:

- `survey/answers/get-by-survey`
- `survey/answers/get-summary`

Почему:

- `get-by-survey` реально заполнен;
- там есть поля, похожие на:
  - `Number of source-attribution responses`
  - `Number of deaths on OG`
  - quality sub-metrics
- `get-summary` уже агрегирует часть этого в готовые ratios / averages.

### 4. External quality

Кандидат:

- `survey/satisfaction`

Отдельная рабочая логика зафиксирована здесь:

- [erp_survey_satisfaction_logic.md](/Users/Peter/Documents/Morpheus%20Metrics/docs/erp_survey_satisfaction_logic.md)

Почему:

- endpoint реально заполнен;
- на последней полной неделе:
  - Москва: `171` ответ, `127` записей с непустыми ответами
  - СПб: `84` ответа, `59` записей с непустыми ответами

Главная дыра:

- пока не расшифровано, что означают вопросы `1..4`.

### 5. Source attribution

Теперь рабочая гипотеза уже подтверждена:

- базовую метрику `Number of source-attribution responses` надо брать из:
  - `survey/satisfaction.answers[2]`

А не из:

- `survey/answers/get-by-survey.how_to_find`

Почему:

- в `answers[2]` реально лежат значения вида:
  - `Друзья, Знакомые`
  - `Я.Афиша`
  - `Яндекс / Google`
  - `Соц. сети`
  - `Карты Яндекс, Google, 2ГИС`
  - `Подарили сертификат`
- а в `get-by-survey.how_to_find` лежат actor/protocol free-text ответы, не похожие на маркетинговый source.

Важно:

- из ERP это получается сначала как **count of non-empty answers by source**
- `share` нужно считать уже у нас:
  - `source_count / total_nonempty_answers`

Ограничение:

- ERP source taxonomy не совпадает 1-в-1 с legacy manual sheet.
- Например:
  - `Яндекс / Google` приходит одной категорией, без split на `Google поиск` и `Яндекс поиск`
  - `Я.Афиша`, `Т банк афиша`, `Тафиша` нужно склеивать в `Яндекс Афиша`

Сопутствующая базовая метрика, которую добавили в каталог:

- `Number of post-show survey responses`

Её смысл:

- count всех непустых `answers[2]`
- это знаменатель для расчёта derived-метрики `Source share`
- и одновременно useful context metric для качества weekly source coverage

## Что пока не надо тащить в source layer

На текущем этапе я бы не делал source-ingestion для:

- `schedule/generate`
- `recordings`
- `actors/schedule/unavailable/get`
- `schedule/personal`
- `metrics`

Это useful reference / future layers, но не первая волна fact ingestion.

## Practical next step

Если продолжать ERP-ingestion, я бы шёл так:

1. добить формулу для `Costs - Salary variable` из:
   - `salaries/period`
   - `bonuses`
   - при необходимости `payments`
2. расшифровать поля `survey/satisfaction.answers[1..4]`
3. импортировать `Number of source-attribution responses` из `survey/satisfaction.answers[2]`
4. поверх него считать derived-метрику `Source share`
5. проверить, как exactly использовать `get-summary`:
   - как direct fact source
   - или как validation layer для расчёта из `get-by-survey`
