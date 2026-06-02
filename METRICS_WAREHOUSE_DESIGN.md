# Metrics Warehouse Design

## Goal

Построить единую базу данных по метрикам компании так, чтобы:

- в одном месте жили финансовые и нефинансовые метрики;
- было понятно, что является первичным источником, а что расчетом;
- можно было дебажить происхождение каждой цифры;
- Google Sheets перестали быть единственным местом истины;
- данные из сервисов можно было постепенно делать основными источниками истины.

## Current Situation

Сейчас метрики собираются в нескольких форматах:

- есть регулярно обновляемая weekly Google Sheet по Москве и Санкт-Петербургу;
- есть накопленная monthly база метрик, которая сейчас регулярно не пополняется;
- есть несколько онлайн-сервисов с первичной информацией:
  - PlanFact
  - ERP
  - AMOCRM
  - Yandex Metrica
- часть данных из сервисов уже используется для ручной/полуручной сборки Google Sheets, из-за чего возникают дубли.

## Core Design Principle

Не строить "одну большую таблицу со всеми метриками".

Вместо этого строить хранилище метрик из нескольких слоев:

1. raw layer
2. standardized layer
3. fact layer
4. semantic / calculated layer

Ключевая идея:

- Google Sheets может оставаться удобной операционной витриной;
- но source of truth должен быть явно определен в базе;
- наблюдаемые метрики и расчетные метрики нельзя смешивать в одном слое без различия.

## Layer 1. Raw Layer

Сюда складываются данные "как есть", без сложной бизнес-логики.

Примеры таблиц:

- `raw_google_weekly_metrics`
- `raw_google_monthly_metrics`
- `raw_planfact_entries`
- `raw_erp_events`
- `raw_amocrm_entities`
- `raw_yandex_metrica`

Принципы:

- хранить `loaded_at`;
- хранить `source_system`;
- хранить исходный идентификатор строки/сущности;
- по возможности хранить raw payload;
- ничего не "исправлять" и не "нормализовать" в этом слое.

Назначение слоя:

- возможность пересобрать верхние слои;
- аудит;
- дебаг;
- защита от потери контекста исходных данных.

## Layer 2. Standardized Layer

Здесь данные приводятся к общей модели.

### Main Dimensions

- `dim_business_unit`
- `dim_metric`
- `dim_date`
- `dim_source_system`
- при необходимости:
  - `dim_channel`
  - `dim_product`
  - `dim_city`

### Key Dictionary: `dim_metric`

В этом справочнике каждая метрика должна быть описана явно.

Пример полей:

- `metric_code`
- `metric_name`
- `metric_group`
- `business_unit_scope`
- `default_grain`
- `value_type`
- `is_calculated`
- `owner`
- `description`
- `source_of_truth`

### Metric Source Mapping

Отдельно нужен реестр соответствий:

- `metric_source_mapping`

В нем должно храниться:

- из какого источника приходит метрика;
- какому raw полю, строке, диапазону или ячейке она соответствует;
- какое правило трансформации используется;
- какой уровень доверия у соответствия.

## Layer 3. Fact Layer

Нужен не один факт "на все", а несколько факт-таблиц по разному зерну.

### Recommended Fact Tables

- `fact_metric_observations`
- `fact_finance_transactions`
- `fact_show_activity`
- `fact_crm_pipeline`
- `fact_web_traffic`

### `fact_metric_observations`

Это слой для наблюдаемых метрик.

Пример зерна:

- `metric_id`
- `business_unit_id`
- `period_start`
- `period_end`
- `grain`
- `source_system_id`
- `value`
- `value_raw`
- `currency`
- `trace_id`
- `source_locator`

Сюда кладутся только:

- атомарные показатели;
- либо согласованные агрегаты, если они уже считаются в trusted source.

Сюда не нужно класть сложные управленческие derived KPI без отдельной пометки.

## Layer 4. Semantic / Calculated Layer

Этот слой нужен для расчетных показателей.

Сюда попадают:

- `% к выручке`
- средние значения
- маржинальность
- прибыль
- доля расходов
- директорский процент
- другие derived KPI

### Formula Registry

Нужен отдельный каталог формул:

- `metric_formula_definitions`

Пример полей:

- `metric_code`
- `formula_expression`
- `depends_on`
- `grain`
- `business_unit_scope`
- `version`
- `comment`

### Calculated Fact Layer

Нужна отдельная факт-таблица или materialized view:

- `fact_metric_calculations`

Главный принцип:

- observed metrics отдельно;
- calculated metrics отдельно.

## How To Treat Google Sheets

Google Sheets не нужно сразу убирать из процесса.

Но нужно поменять их роль.

### Current Role

Сейчас Google Sheets одновременно:

- источник;
- место расчета;
- витрина;
- иногда manual override.

### Recommended Role

Краткосрочно:

- продолжать парсить weekly и monthly sheets как curated source.

Среднесрочно:

- постепенно заменять sheet-derived показатели расчетами из raw сервисов.

Долгосрочно:

- оставить Google Sheets только как:
  - операционный ввод;
  - override;
  - fallback;
  - validation layer.

## How To Handle Duplicates

Сейчас одна и та же сущность может существовать:

- в сервисе;
- в weekly Google Sheet;
- в monthly базе;
- в управленческой расчетной модели.

Для каждой бизнес-метрики нужен один `master source`.

Примеры:

- `Поступления на счет` -> PlanFact / finance
- `Проведено шоу` -> ERP
- `Посещаемость сайта` -> Yandex Metrica
- `Сделки в работе` -> AMOCRM
- `Маржинальный доход` -> formula
- `ручной KPI, которого больше нигде нет` -> Google Sheet

## Metric Classification

Все метрики стоит разделить минимум на 3 класса.

### 1. Observed

То, что можно получить напрямую:

- выручка;
- расходы;
- билеты;
- спектакли;
- гости;
- визиты;
- заявки.

### 2. Allocated

То, что получается из наблюдаемых по правилам распределения:

- сертификаты с коэффициентом;
- распределение общей выручки;
- общие расходы спецпроектов;
- управленческие аллокации.

### 3. Calculated

То, что считается формулой:

- среднее количество гостей;
- `% к выручке`;
- маржинальный доход;
- прибыль;
- рентабельность.

## Minimal Target Schema

Если делать практично и без лишней абстракции, то минимально целевая структура такая:

### Dimensions

- `dim_business_unit`
- `dim_metric`
- `dim_metric_source_mapping`
- `dim_formula_definition`

### Facts

- `fact_metric_observations`
- `fact_metric_calculations`
- `fact_finance_transactions`
- `fact_show_activity`
- `fact_crm_pipeline`
- `fact_web_traffic`

### Raw

- `raw_google_weekly_metrics`
- `raw_google_monthly_metrics`
- `raw_planfact`
- `raw_erp`
- `raw_amocrm`
- `raw_yandex_metrica`

## What To Do With Monthly Metrics

Monthly metrics не нужно выбрасывать.

Их стоит загрузить как historical curated layer:

- `raw_google_monthly_metrics`
- затем нормализовать в `fact_metric_observations`
- пометить `source_system = monthly_sheet`

Даже если monthly dataset не пополняется регулярно, он полезен как история и как база для сравнения.

## Implementation Priority

### 1. Freeze the Metric Dictionary

Зафиксировать словарь метрик:

- название;
- код;
- grain;
- unit / business unit scope;
- тип;
- observed vs calculated;
- source of truth.

### 2. Separate Observed and Calculated

Это даст самую большую чистоту модели.

### 3. Build Unified Curated Fact

Сначала объединить weekly + monthly curated metrics в единый слой наблюдений.

### 4. Ingest Primary Systems Step By Step

Сначала:

- PlanFact
- ERP

Потом:

- Yandex Metrica
- AMOCRM

### 5. Move Master Source From Sheet To Systems

Не все сразу, а по одной группе метрик.

Например:

- сначала финансовые;
- потом операционные;
- потом CRM;
- потом web;
- потом derived KPI.

## Practical Result

Итоговая цель — не просто "база со всеми метриками", а полноценное metrics warehouse:

- сырые источники;
- нормализованные наблюдения;
- слой формул;
- явный словарь метрик;
- явный lineage;
- понятный debugging path;
- поддержка Metabase и управленческой аналитики.

## Why This Design Fits The Current Company Setup

Такой дизайн хорошо подходит под текущую реальность компании, потому что:

- у вас уже есть несколько источников;
- есть дубли между сервисами и Google Sheets;
- есть финансовые и нефинансовые показатели;
- есть расчетные показатели;
- важно понимать происхождение цифр;
- важно не ломать текущий операционный процесс сразу.

То есть архитектура позволяет:

- не выбрасывать уже существующие Google Sheets;
- постепенно переводить систему на trusted primary sources;
- получать reproducible KPI;
- хранить управленческую модель явно, а не "в головах" или только в таблицах.
