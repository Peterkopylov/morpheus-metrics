#!/usr/bin/env python3
import argparse

import psycopg2


VIEW_SQL = """
DROP VIEW IF EXISTS planfact_pnl_test;

CREATE VIEW planfact_pnl_test AS
WITH mapped AS (
    SELECT
        p.source_row_number,
        COALESCE(p.accrual_date, p.payment_date) AS report_date,
        date_trunc('month', COALESCE(p.accrual_date, p.payment_date)::timestamp)::date AS month_start,
        p.row_type,
        p.entry_role,
        p.article,
        p.parent_articles,
        p.activity_type,
        p.project_name,
        p.business_unit_id,
        p.business_unit_code,
        p.business_unit_name,
        p.analytics_unit_code,
        p.analytics_unit_name,
        p.currency,
        p.amount,
        m.id AS mapping_id,
        d.id AS accounting_article_id,
        d.article_name AS accounting_article_name,
        d.path AS accounting_path,
        d.tab_code AS accounting_tab_code,
        d.depth AS accounting_depth,
        d.sort_order AS accounting_sort_order,
        parent.id AS parent_accounting_article_id,
        parent.article_name AS parent_accounting_article_name,
        parent.sort_order AS parent_accounting_sort_order,
        grandparent.id AS grandparent_accounting_article_id,
        grandparent.article_name AS grandparent_accounting_article_name,
        grandparent.sort_order AS grandparent_accounting_sort_order
    FROM planfact_cashflow_analytic p
    LEFT JOIN planfact_article_mappings m
      ON m.source_system = 'planfact'
     AND m.raw_parent_articles IS NOT DISTINCT FROM p.parent_articles
     AND m.raw_article = p.article
     AND m.is_active = TRUE
    LEFT JOIN dim_planfact_accounting_articles d
      ON d.id = m.accounting_article_id
    LEFT JOIN dim_planfact_accounting_articles parent
      ON parent.id = d.parent_article_id
    LEFT JOIN dim_planfact_accounting_articles grandparent
      ON grandparent.id = parent.parent_article_id
    WHERE p.row_type <> 'Перемещение'
      AND COALESCE(p.accrual_date, p.payment_date) IS NOT NULL
      AND p.amount IS NOT NULL
      AND p.article IS NOT NULL
      AND p.article NOT IN ('[Зачисление]', '[Списание]')
), classified AS (
    SELECT
        mapped.*,
        CASE
            WHEN accounting_tab_code = 'income' AND parent_accounting_article_name = 'Прочие доходы' THEN 'Прочие доходы'
            WHEN accounting_path = 'equity/Капитал/Дивиденды' THEN 'Дивиденды'
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Амортизация' THEN 'Амортизация'
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Проценты по кредитам и займам' THEN 'Проценты по кредитам и займам'
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Налог на прибыль (доходы)' THEN 'Налог на прибыль (доходы)'
            WHEN accounting_path LIKE 'income/%' THEN 'Выручка'
            WHEN accounting_path LIKE 'expense/%' THEN 'Основные расходы'
            ELSE 'Нераспределенное'
        END AS pnl_section,
        CASE
            WHEN accounting_tab_code = 'income' AND parent_accounting_article_name = 'Прочие доходы' THEN 'Прочие доходы'
            WHEN accounting_path = 'equity/Капитал/Дивиденды' THEN 'Дивиденды'
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Амортизация' THEN 'Амортизация'
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Проценты по кредитам и займам' THEN 'Проценты по кредитам и займам'
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Налог на прибыль (доходы)' THEN 'Налог на прибыль (доходы)'
            WHEN accounting_depth = 3 THEN parent_accounting_article_name
            WHEN accounting_depth = 2 THEN accounting_article_name
            ELSE accounting_article_name
        END AS pnl_group,
        CASE
            WHEN accounting_path = 'equity/Капитал/Дивиденды' THEN NULL
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Амортизация' THEN NULL
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Проценты по кредитам и займам' THEN NULL
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Налог на прибыль (доходы)' THEN NULL
            WHEN accounting_depth = 3 THEN accounting_article_name
            ELSE NULL
        END AS pnl_article,
        CASE
            WHEN accounting_path LIKE 'income/%' AND NOT (accounting_tab_code = 'income' AND parent_accounting_article_name = 'Прочие доходы') THEN 10
            WHEN accounting_path LIKE 'expense/%'
                 AND accounting_path NOT IN (
                     'expense/Расходы/Прочие расходы/Амортизация',
                     'expense/Расходы/Прочие расходы/Проценты по кредитам и займам',
                     'expense/Расходы/Прочие расходы/Налог на прибыль (доходы)'
                 ) THEN 20
            WHEN accounting_path LIKE 'income/Доходы/Прочие доходы/%' THEN 30
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Амортизация' THEN 40
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Проценты по кредитам и займам' THEN 50
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Налог на прибыль (доходы)' THEN 60
            WHEN accounting_path = 'equity/Капитал/Дивиденды' THEN 70
            ELSE 999
        END AS pnl_section_order,
        CASE
            WHEN accounting_path = 'equity/Капитал/Дивиденды' THEN accounting_sort_order
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Амортизация' THEN accounting_sort_order
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Проценты по кредитам и займам' THEN accounting_sort_order
            WHEN accounting_path = 'expense/Расходы/Прочие расходы/Налог на прибыль (доходы)' THEN accounting_sort_order
            WHEN accounting_depth = 3 THEN parent_accounting_sort_order
            WHEN accounting_depth = 2 THEN accounting_sort_order
            ELSE accounting_sort_order
        END AS pnl_group_order,
        CASE
            WHEN accounting_depth = 3
             AND accounting_path NOT IN (
                 'equity/Капитал/Дивиденды',
                 'expense/Расходы/Прочие расходы/Амортизация',
                 'expense/Расходы/Прочие расходы/Проценты по кредитам и займам',
                 'expense/Расходы/Прочие расходы/Налог на прибыль (доходы)'
             ) THEN accounting_sort_order
            ELSE NULL
        END AS pnl_article_order,
        amount AS amount_signed,
        abs(amount) AS amount_abs
    FROM mapped
)
SELECT
    source_row_number,
    report_date,
    month_start,
    row_type,
    entry_role,
    article,
    parent_articles,
    activity_type,
    project_name,
    business_unit_id,
    business_unit_code,
    business_unit_name,
    analytics_unit_code,
    analytics_unit_name,
    currency,
    amount,
    mapping_id,
    accounting_article_id,
    accounting_article_name,
    accounting_path,
    accounting_tab_code,
    accounting_depth,
    pnl_section,
    pnl_group,
    pnl_article,
    pnl_section_order,
    pnl_group_order,
    pnl_article_order,
    amount_signed,
    amount_abs
FROM classified;
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(VIEW_SQL)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
