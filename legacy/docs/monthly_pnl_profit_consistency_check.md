# Monthly P&L Profit Consistency Check

Эта проверка валидирует monthly P&L на уровне:

- `business_unit`
- `period_start`

Правило проверки:

- `Net profit = Revenue - Variable costs - Fixed costs`

Источник данных:

- `monthly_pnl_active_history_with_total`

Скрипт:

- [build_monthly_pnl_profit_consistency_report.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/build_monthly_pnl_profit_consistency_report.py)

Отчёт:

- [monthly_pnl_profit_consistency_report.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/monthly_pnl_profit_consistency_report.csv)

Колонки отчёта:

- `business_unit`
- `period_start`
- `review_attention`
- `coverage_status`
- `present_metrics_count`
- `check_status`
- `missing_metrics`
- `source_systems`
- `Revenue`
- `Variable costs`
- `Fixed costs`
- `Net profit`
- `calculated_net_profit`
- `delta`
- `abs_delta`

Интерпретация:

- `coverage_status = complete`
  - все 4 метрики присутствуют
- `coverage_status = partial`
  - не хватает хотя бы одной из 4 метрик
- `check_status = exact_match`
  - формула сошлась точно
- `check_status = small_delta`
  - небольшое расхождение
- `check_status = moderate_delta`
  - заметное расхождение
- `check_status = large_delta`
  - сильное расхождение или фактически несобранный P&L-блок
- `check_status = missing_required_metric`
  - формулу нельзя честно проверить, потому что недостаёт компонентов

Практическое правило чтения:

- сначала смотреть `review_attention = high`
- затем разделять:
  - `partial coverage`
  - `complete coverage but non-zero delta`

Это помогает отличать:

- проблемы полноты historical mapping / ingestion
- от проблем реальной несходимости P&L-структуры
