# Legacy Monthly P&L -> Fact Ingestion

Рабочая заметка по разовому мосту из legacy monthly P&L в новый факт-слой.

Статус на `2026-05-01`.

## Источник

- source file:
  - `/Users/Peter/Downloads/Месяц_статистика и цели - ЭКОНОМИКА (P&L) - для базы.csv`
- normalized legacy reference table:
  - `legacy_monthly_pnl_reference`

## Target

- target fact table:
  - `fact_metric_observation`
- `source_system`:
  - `legacy_monthly_pnl_csv`
- `source_run_id`:
  - `Месяц_статистика и цели - ЭКОНОМИКА (P&L) - для базы.csv`

## Import script

- script:
  - [import_legacy_monthly_pnl_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/legacy/scripts/import_legacy_monthly_pnl_to_fact.py)

Текущая логика скрипта:

- умеет удалять предыдущий импорт именно этого source file:
  - `--delete-existing`
- кладёт только строки с явным маппингом в новый каталог
- пишет monthly facts в `fact_metric_observation`
- сохраняет подробный report по загрузке

## Последний прогон

Последний известный результат:

- удалено старых строк:
  - `253`
- загружено новых строк:
  - `934`

Report file:

- [legacy_monthly_pnl_to_fact_import_report.csv](/Users/Peter/Documents/Morpheus%20Metrics/legacy/generated/legacy_monthly_pnl_to_fact_import_report.csv)

## Что уже маппится

На текущем этапе подтверждённо грузятся:

- `Number of shows`
- `Number of show visitors`
- `Returns amount`
- `Revenue`
- `Revenue - Other`
- `Revenue - Financial operations`
- `Marketing costs`
- часть `cost article`-метрик из PlanFact-каталога
- `Scheduling complexity`

Примеры article-level попаданий:

- `Cost article - Комиссия`
- `Cost article - Аренда и коммуналка`
- `Cost article - Уборка`
- `Cost article - КОМИССИИ БАНКОВ`
- `Cost article - Другое`
- `Cost article - Реквизит/костюмы`
- `Cost article - Страховые взносы`

## Что ещё не маппится автоматически

Главные непринятые блоки сейчас:

- процентные и ratio-метрики
- profitability / margin агрегаты
- часть legacy ФОТ-строк
- часть специальных revenue variants

Типичные примеры:

- `%заполняемости`
- `%к выручке`
- `% ФОТ в выручке ШОУ`
- `Маржинальный доход`
- `Общая прибыль`
- `Прибыль для основателей`
- `Расчетная выручка периода (по реализации)`

## Как вернуться к этой задаче позже

Когда будем продолжать, полезно идти в таком порядке:

1. открыть этот файл;
2. открыть report:
   - [legacy_monthly_pnl_to_fact_import_report.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/legacy_monthly_pnl_to_fact_import_report.csv)
3. посмотреть, какие `legacy_metric_name` ещё остались `skipped`;
4. для каждой спорной строки решить одно из трёх:
   - map to existing metric
   - create new metric
   - keep only as legacy reference

## Поле для будущей интерпретации

Сюда потом можно дописать agreed mapping-решения по legacy строкам.

### Pending interpretation

- TBD
