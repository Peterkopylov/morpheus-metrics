**PlanFact Monthly P&L**
Этот контур нужен для monthly fact-layer по P&L без хранения всех финансовых операций.

Источник:
- [Отчет о прибылях и убытках по периоду (5).xlsx](/Users/Peter/Downloads/%D0%9E%D1%82%D1%87%D0%B5%D1%82%20%D0%BE%20%D0%BF%D1%80%D0%B8%D0%B1%D1%8B%D0%BB%D1%8F%D1%85%20%D0%B8%20%D1%83%D0%B1%D1%8B%D1%82%D0%BA%D0%B0%D1%85%20%D0%BF%D0%BE%20%D0%BF%D0%B5%D1%80%D0%B8%D0%BE%D0%B4%D1%83%20(5).xlsx)
- [Отчет о прибылях и убытках по периоду - general.xlsx](/Users/Peter/Downloads/Отчет%20о%20прибылях%20и%20убытках%20по%20периоду%20-%20general.xlsx)
- [Отчет о прибылях и убытках по периоду - b2cmoscow.xlsx](/Users/Peter/Downloads/Отчет%20о%20прибылях%20и%20убытках%20по%20периоду%20-%20b2cmoscow.xlsx)
- [Отчет о прибылях и убытках по периоду - b2cspb.xlsx](/Users/Peter/Downloads/Отчет%20о%20прибылях%20и%20убытках%20по%20периоду%20-%20b2cspb.xlsx)
- [Отчет о прибылях и убытках по периоду - b2b.xlsx](/Users/Peter/Downloads/Отчет%20о%20прибылях%20и%20убытках%20по%20периоду%20-%20b2b.xlsx)
- [Отчет о прибылях и убытках по периоду - franchise.xlsx](/Users/Peter/Downloads/Отчет%20о%20прибылях%20и%20убытках%20по%20периоду%20-%20franchise.xlsx)
- лист: `Статьи по периодам с прибылью`

Принцип:
- в `fact_metric_observation` импортируем месячные строки P&L как наблюдаемые факты источника;
- процентные строки рентабельности не считаем raw facts;
- финансовые операции поштучно для этого слоя не храним.
- каждый workbook загружается независимо в свой `business_unit`.
- observed consolidated workbook из PlanFact грузится отдельно в `business_unit = total`.

Ключевая логика:
- `Revenue` в канонике один;
- из PlanFact в fact layer импортируем только верхнюю observed строку `Выручка`;
- дочерние revenue-строки типа `Продажа билетов B2C`, `Организация мероприятий (B2B)`, `Франшиза`, `Паушалка`, `Роялти`, `Другие продажи`, `Корректировка неучтенного` не импортируем, чтобы не задваивать revenue внутри одного business unit;
- различие между ними сохраняется в `payload.source_label` и `payload.source_row_number`, а не в имени метрики;
- `Актёры ФОТ` маппится в `Costs - Salary variable`.

Что считаем `fact`:
- денежные totals и subtotals:
  - `Выручка`
  - `Основные расходы`
  - `Операционная прибыль`
  - `Прочие доходы`
  - `Прочие расходы`
  - `EBITDA`
  - `EBIT`
  - `EBT`
  - `Чистая прибыль (убыток)`
  - `Дивиденды`
  - `Нераспределенная прибыль`
- денежные line items:
  - revenue breakdown
  - expense article rows
  - expense subtotals

Что считаем `calculated`:
- `Операционная рентабельность`
- `Рентабельность по EBITDA`
- `Рентабельность по EBIT`
- `Рентабельность по EBT`
- `Рентабельность чистой прибыли`

Бизнес-правило:
- начиная с `2026-05-24` monthly PlanFact importer кладёт в `fact` только:
  - lower-level leaf P&L строки;
  - верхнюю observed строку `Выручка` как единственный revenue subtotal;
- subtotal / result rows вроде:
  - `Переменные расходы`
  - `Постоянные расходы`
  - `Инвестиции`
  - `ФОТ - Переменные`
  - `ФОТ - Постоянные`
  - `Маркетинг и реклама`
  - `Прочие расходы`
  - `Операционная прибыль`
  - `EBITDA`
  - `EBIT`
  - `EBT`
  - `Чистая прибыль (убыток)`
  - `Дивиденды`
  - `Нераспределенная прибыль`
  больше не импортируются как raw facts;
- эти rollup/result значения должны восстанавливаться через calculated / recursive rollup contour поверх leaf-статей;
- если строка уже укладывается в существующую canonical metric, новую метрику не создаём.
- если в новых PlanFact workbook’ах появляется новая P&L-строка или новый subtotal/leaf-узел, которого ещё нет в текущем mapping/иерархии:
  - сначала обновляем [pnl_structure_mapping_canonical.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/pnl_structure_mapping_canonical.csv);
  - затем обновляем [planfact_monthly_pnl_report_mapping.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/planfact_monthly_pnl_report_mapping.py);
  - и только после этого переимпортируем PlanFact в `fact`;
  - нельзя молча добавлять новую строку только в importer без синхронизации P&L structure.
- alert rule:
  - если строка, которая раньше считалась `leaf`, в новом PlanFact вдруг становится `parent` и получает дочерние строки,
    importer должен падать с ошибкой;
  - это считается срочным сигналом, что структура P&L изменилась и mapping/иерархию надо пересмотреть до следующего импорта.

Скрипты:
- metadata / classification:
  - [refresh_planfact_monthly_pnl_report_metadata.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/refresh_planfact_monthly_pnl_report_metadata.py)
- import to fact:
  - [import_planfact_monthly_pnl_report_to_fact.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/import_planfact_monthly_pnl_report_to_fact.py)
- mapping module:
  - [planfact_monthly_pnl_report_mapping.py](/Users/Peter/Documents/Morpheus%20Metrics/scripts/planfact_monthly_pnl_report_mapping.py)

Артефакты:
- fact vs calculated map:
  - [planfact_monthly_pnl_fact_vs_calculated.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/planfact_monthly_pnl_fact_vs_calculated.csv)
- import report:
  - [planfact_monthly_pnl_report_to_fact_import_report.csv](/Users/Peter/Documents/Morpheus%20Metrics/generated/planfact_monthly_pnl_report_to_fact_import_report.csv)

Последний подтверждённый импорт:
- дата: `2026-05-16`
- workbook’ов: `6`
- business units:
  - `total`
  - `general`
  - `b2c_moscow`
  - `b2c_spb`
  - `b2b`
  - `franchise`
- inserted facts: `2144`
