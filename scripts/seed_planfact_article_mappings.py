#!/usr/bin/env python3
import argparse
import json

import psycopg2
from psycopg2.extras import RealDictCursor


def ensure_schema(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS planfact_article_mappings (
            id BIGSERIAL PRIMARY KEY,
            source_system TEXT NOT NULL DEFAULT 'planfact',
            raw_parent_articles TEXT,
            raw_article TEXT NOT NULL,
            accounting_article_id BIGINT NOT NULL REFERENCES dim_planfact_accounting_articles(id),
            mapping_method TEXT NOT NULL DEFAULT 'manual',
            mapping_confidence TEXT NOT NULL DEFAULT 'high',
            notes TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT planfact_article_mappings_unique
                UNIQUE NULLS NOT DISTINCT (source_system, raw_parent_articles, raw_article)
        );
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS planfact_article_mappings_accounting_article_idx
        ON planfact_article_mappings (accounting_article_id);
        """
    )


def seed_exact_mappings(cur) -> None:
    cur.execute(
        """
        WITH source_pairs AS (
            SELECT DISTINCT
                'planfact'::text AS source_system,
                parent_articles AS raw_parent_articles,
                article AS raw_article
            FROM planfact_cashflow_analytic
            WHERE article IS NOT NULL
        ),
        exact_candidates AS (
            SELECT
                s.source_system,
                s.raw_parent_articles,
                s.raw_article,
                d.id AS accounting_article_id,
                d.path
            FROM source_pairs s
            JOIN dim_planfact_accounting_articles d
              ON d.article_name = s.raw_article
             AND d.is_active = TRUE
            WHERE s.raw_article NOT IN ('[Зачисление]', '[Списание]')
              AND (
                    (s.raw_parent_articles = 'Доходы' AND d.path = 'income/Доходы/' || s.raw_article)
                 OR (s.raw_parent_articles = 'Доходы - Франшиза' AND d.path = 'income/Доходы/Франшиза/' || s.raw_article)
                 OR (s.raw_parent_articles = 'Доходы - Прочие доходы' AND d.path = 'income/Доходы/Прочие доходы/' || s.raw_article)
                 OR (s.raw_parent_articles = 'Расходы' AND d.path = 'expense/Расходы/' || s.raw_article)
                 OR (s.raw_parent_articles = 'Расходы - ФОТ' AND d.path = 'expense/Расходы/ФОТ/' || s.raw_article)
                 OR (s.raw_parent_articles = 'Расходы - ПЕРЕЕЗД' AND d.path = 'expense/Расходы/ПЕРЕЕЗД/' || s.raw_article)
                 OR (s.raw_parent_articles = 'Расходы - ПРЕМИИ 2025' AND d.path = 'expense/Расходы/ПРЕМИИ 2025/' || s.raw_article)
                 OR (s.raw_parent_articles = 'Расходы - Для спектаклей' AND d.path = 'expense/Расходы/Для спектаклей/' || s.raw_article)
                 OR (s.raw_parent_articles = 'Расходы - Помещение и офис' AND d.path = 'expense/Расходы/Помещение и офис/' || s.raw_article)
                 OR (s.raw_parent_articles = 'Расходы - Сервисы и их настройка' AND d.path = 'expense/Расходы/Сервисы и их настройка/' || s.raw_article)
                 OR (s.raw_parent_articles = 'Расходы - Логистика' AND d.path = 'expense/Расходы/Логистика/' || s.raw_article)
                 OR (s.raw_parent_articles = 'Капитал' AND d.path = 'equity/Капитал/' || s.raw_article)
              )
            UNION ALL
            SELECT
                s.source_system,
                s.raw_parent_articles,
                s.raw_article,
                d.id AS accounting_article_id,
                d.path
            FROM source_pairs s
            JOIN dim_planfact_accounting_articles d
              ON d.is_active = TRUE
            WHERE (s.raw_parent_articles, s.raw_article, d.path) IN (
                ('Расходы', 'Корпоративы ЗП проектные', 'expense/Расходы/ПРЕМИИ 2025/Корпоративы ЗП проектные'),
                ('Расходы', 'Налог на прибыль (доходы)', 'expense/Расходы/Прочие расходы/Налог на прибыль (доходы)'),
                ('Доходы', 'Нераспределенный доход', 'income/Доходы/Нераспределенный доход'),
                ('Расходы', 'Нераспределенный расход', 'expense/Расходы/Нераспределенный расход')
            )
        )
        INSERT INTO planfact_article_mappings (
            source_system,
            raw_parent_articles,
            raw_article,
            accounting_article_id,
            mapping_method,
            mapping_confidence,
            notes,
            is_active,
            updated_at
        )
        SELECT
            source_system,
            raw_parent_articles,
            raw_article,
            accounting_article_id,
            'exact_path_match',
            'high',
            'Auto-seeded from exact parent/article path match',
            TRUE,
            NOW()
        FROM (
            SELECT DISTINCT ON (source_system, raw_parent_articles, raw_article)
                source_system,
                raw_parent_articles,
                raw_article,
                accounting_article_id
            FROM exact_candidates
            ORDER BY source_system, raw_parent_articles, raw_article, accounting_article_id
        ) deduped
        ON CONFLICT (source_system, raw_parent_articles, raw_article) DO UPDATE
        SET
            accounting_article_id = EXCLUDED.accounting_article_id,
            mapping_method = EXCLUDED.mapping_method,
            mapping_confidence = EXCLUDED.mapping_confidence,
            notes = EXCLUDED.notes,
            is_active = TRUE,
            updated_at = NOW();
        """
    )


def fetch_summary(cur):
    cur.execute(
        """
        SELECT
            COUNT(*) AS mapping_count,
            COUNT(*) FILTER (WHERE mapping_method = 'exact_path_match') AS exact_path_match_count
        FROM planfact_article_mappings
        WHERE is_active = TRUE;
        """
    )
    mapping_summary = cur.fetchone()

    cur.execute(
        """
        WITH source_pairs AS (
            SELECT DISTINCT parent_articles AS raw_parent_articles, article AS raw_article
            FROM planfact_cashflow_analytic
            WHERE article IS NOT NULL
        )
        SELECT
            COALESCE(s.raw_parent_articles, '<null>') AS raw_parent_articles,
            s.raw_article
        FROM source_pairs s
        LEFT JOIN planfact_article_mappings m
          ON m.source_system = 'planfact'
         AND m.raw_parent_articles IS NOT DISTINCT FROM s.raw_parent_articles
         AND m.raw_article = s.raw_article
         AND m.is_active = TRUE
        WHERE m.id IS NULL
        ORDER BY 1, 2;
        """
    )
    unmapped = cur.fetchall()

    cur.execute(
        """
        SELECT
            m.raw_parent_articles,
            m.raw_article,
            d.path AS mapped_path
        FROM planfact_article_mappings m
        JOIN dim_planfact_accounting_articles d ON d.id = m.accounting_article_id
        WHERE m.is_active = TRUE
        ORDER BY m.raw_parent_articles NULLS FIRST, m.raw_article;
        """
    )
    mapped = cur.fetchall()

    return mapping_summary, mapped, unmapped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                ensure_schema(cur)
                seed_exact_mappings(cur)
                mapping_summary, mapped, unmapped = fetch_summary(cur)

        print(
            json.dumps(
                {
                    "mapping_summary": mapping_summary,
                    "mapped_pairs": mapped,
                    "unmapped_pairs": unmapped,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
