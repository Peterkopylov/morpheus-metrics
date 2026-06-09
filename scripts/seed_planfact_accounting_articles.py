#!/usr/bin/env python3
import argparse
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


@dataclass(frozen=True)
class ArticleNode:
    name: str
    tab_code: str
    tab_name: str
    parent_path: Optional[str]
    sort_order: int
    is_group: bool = False
    is_locked: bool = False
    notes: Optional[str] = None


def slugify(value: str) -> str:
    value = value.lower().strip().replace("ё", "е")
    value = re.sub(r"[^a-zа-я0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "item"


def build_seed_nodes() -> List[ArticleNode]:
    nodes: List[ArticleNode] = []

    def add(
        name: str,
        tab_code: str,
        tab_name: str,
        sort_order: int,
        parent_path: Optional[str] = None,
        is_group: bool = False,
        is_locked: bool = False,
        notes: Optional[str] = None,
    ) -> None:
        nodes.append(
            ArticleNode(
                name=name,
                tab_code=tab_code,
                tab_name=tab_name,
                parent_path=parent_path,
                sort_order=sort_order,
                is_group=is_group,
                is_locked=is_locked,
                notes=notes,
            )
        )

    # Root tabs
    add("Доходы", "income", "Доходы", 10, is_group=True)
    add("Расходы", "expense", "Расходы", 20, is_group=True)
    add("Активы", "asset", "Активы", 30, is_group=True)
    add("Обязательства", "liability", "Обязательства", 40, is_group=True)
    add("Капитал", "equity", "Капитал", 50, is_group=True)

    # Income tab
    add("Корректировка неучтенного", "income", "Доходы", 110, "income/Доходы")
    add("Другие продажи", "income", "Доходы", 120, "income/Доходы", is_group=True)
    add("Франшиза", "income", "Доходы", 130, "income/Доходы", is_group=True)
    add("Паушалка", "income", "Доходы", 131, "income/Доходы/Франшиза")
    add("Роялти", "income", "Доходы", 132, "income/Доходы/Франшиза")
    add("Продажа билетов B2C", "income", "Доходы", 140, "income/Доходы", is_group=True)
    add("Продажа билетов СПБ", "income", "Доходы", 141, "income/Доходы/Продажа билетов B2C")
    add("Продажа билетов Москва", "income", "Доходы", 142, "income/Доходы/Продажа билетов B2C")
    add("Организация мероприятий (B2B)", "income", "Доходы", 150, "income/Доходы")
    add("Нераспределенный доход", "income", "Доходы", 155, "income/Доходы")
    add("Прочие доходы", "income", "Доходы", 160, "income/Доходы", is_group=True, is_locked=True)
    add("Возвраты покупок", "income", "Доходы", 161, "income/Доходы/Прочие доходы")
    add("Проценты по вкладам", "income", "Доходы", 162, "income/Доходы/Прочие доходы")
    add("Курсовая разница (+)", "income", "Доходы", 163, "income/Доходы/Прочие доходы", is_locked=True)

    # Expense tab
    add("ФОТ", "expense", "Расходы", 210, "expense/Расходы", is_group=True)
    add("Другое ФОТ", "expense", "Расходы", 211, "expense/Расходы/ФОТ")
    add("IT ФОТ", "expense", "Расходы", 212, "expense/Расходы/ФОТ")
    add("Управленческий персонал ФОТ", "expense", "Расходы", 213, "expense/Расходы/ФОТ")
    add("Актёры ФОТ", "expense", "Расходы", 214, "expense/Расходы/ФОТ")
    add("Административный персонал ФОТ", "expense", "Расходы", 215, "expense/Расходы/ФОТ")
    add("Корпоративы фикс", "expense", "Расходы", 216, "expense/Расходы/ФОТ")

    add("ПЕРЕЕЗД", "expense", "Расходы", 220, "expense/Расходы", is_group=True)
    add("Техника", "expense", "Расходы", 221, "expense/Расходы/ПЕРЕЕЗД")
    add("Свет/Мебель/Предметы интерьера", "expense", "Расходы", 222, "expense/Расходы/ПЕРЕЕЗД")
    add("Ремонт/Стройка/Стройматериалы", "expense", "Расходы", 223, "expense/Расходы/ПЕРЕЕЗД")

    add("ПРЕМИИ 2025", "expense", "Расходы", 230, "expense/Расходы", is_group=True)
    add("Премии управленч персонал", "expense", "Расходы", 231, "expense/Расходы/ПРЕМИИ 2025")
    add("Премии административный персонал", "expense", "Расходы", 232, "expense/Расходы/ПРЕМИИ 2025")
    add("Премии актёры", "expense", "Расходы", 233, "expense/Расходы/ПРЕМИИ 2025")
    add("Корпоративы ЗП проектные", "expense", "Расходы", 234, "expense/Расходы/ПРЕМИИ 2025")

    add("Разные налоги и взносы", "expense", "Расходы", 240, "expense/Расходы", is_group=True)
    add("Страховые взносы", "expense", "Расходы", 241, "expense/Расходы/Разные налоги и взносы")
    add("Агентские", "expense", "Расходы", 250, "expense/Расходы", is_group=True)
    add("Комиссия", "expense", "Расходы", 251, "expense/Расходы/Агентские")
    add("Услуги типографии", "expense", "Расходы", 260, "expense/Расходы")
    add("Другое", "expense", "Расходы", 270, "expense/Расходы")
    add("Расходы на B2B (продакшн)", "expense", "Расходы", 280, "expense/Расходы")
    add("Возвраты", "expense", "Расходы", 290, "expense/Расходы")

    add("Для спектаклей", "expense", "Расходы", 300, "expense/Расходы", is_group=True)
    add("Тех оснащение", "expense", "Расходы", 301, "expense/Расходы/Для спектаклей")
    add("Реквизит/костюмы", "expense", "Расходы", 302, "expense/Расходы/Для спектаклей")

    add("Маркетинг и реклама", "expense", "Расходы", 310, "expense/Расходы")

    add("Помещение и офис", "expense", "Расходы", 320, "expense/Расходы", is_group=True)
    add("Уборка", "expense", "Расходы", 321, "expense/Расходы/Помещение и офис")
    add("Мебель и предметы интерьера", "expense", "Расходы", 322, "expense/Расходы/Помещение и офис")
    add("Ремонт и обслуживание", "expense", "Расходы", 323, "expense/Расходы/Помещение и офис")
    add("Расходники (офисные)", "expense", "Расходы", 324, "expense/Расходы/Помещение и офис")
    add("Ежемесячные счета", "expense", "Расходы", 325, "expense/Расходы/Помещение и офис")
    add("Аренда и коммуналка", "expense", "Расходы", 326, "expense/Расходы/Помещение и офис")

    add("Сервисы и их настройка", "expense", "Расходы", 330, "expense/Расходы", is_group=True)
    add("КОМИССИИ БАНКОВ", "expense", "Расходы", 331, "expense/Расходы/Сервисы и их настройка")
    add("Отсмотр видео", "expense", "Расходы", 332, "expense/Расходы/Сервисы и их настройка")

    add("Командные", "expense", "Расходы", 340, "expense/Расходы", is_group=True)
    add("Представительские", "expense", "Расходы", 341, "expense/Расходы/Командные")
    add("Командировочные", "expense", "Расходы", 342, "expense/Расходы/Командные")
    add("Транспорт", "expense", "Расходы", 343, "expense/Расходы/Командные")
    add("Проживание", "expense", "Расходы", 344, "expense/Расходы/Командные")

    add("Логистика", "expense", "Расходы", 350, "expense/Расходы", is_group=True)
    add("Доставка", "expense", "Расходы", 351, "expense/Расходы/Логистика")
    add("Такси", "expense", "Расходы", 352, "expense/Расходы/Логистика")
    add("Нераспределенный расход", "expense", "Расходы", 355, "expense/Расходы")

    add("Прочие расходы", "expense", "Расходы", 360, "expense/Расходы", is_group=True)
    add("Курсовая разница (-)", "expense", "Расходы", 361, "expense/Расходы/Прочие расходы", is_locked=True)
    add("Амортизация", "expense", "Расходы", 362, "expense/Расходы/Прочие расходы", is_locked=True)
    add("Проценты по кредитам и займам", "expense", "Расходы", 363, "expense/Расходы/Прочие расходы", is_locked=True)
    add("Налог на прибыль (доходы)", "expense", "Расходы", 364, "expense/Расходы/Прочие расходы", is_locked=True)

    # Capital tab
    add("Дивиденды", "equity", "Капитал", 510, "equity/Капитал")

    return nodes


def ensure_schema(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS dim_planfact_accounting_articles (
            id BIGSERIAL PRIMARY KEY,
            article_code TEXT NOT NULL UNIQUE,
            article_name TEXT NOT NULL,
            tab_code TEXT NOT NULL,
            tab_name TEXT NOT NULL,
            path TEXT NOT NULL UNIQUE,
            parent_article_id BIGINT REFERENCES dim_planfact_accounting_articles(id),
            depth INTEGER NOT NULL,
            sort_order INTEGER NOT NULL,
            is_group BOOLEAN NOT NULL DEFAULT FALSE,
            is_locked BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            notes TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS dim_planfact_accounting_articles_parent_name_unique
        ON dim_planfact_accounting_articles
        (COALESCE(parent_article_id, 0), tab_code, article_name);
        """
    )


def upsert_nodes(cur, nodes: List[ArticleNode]) -> List[Dict[str, object]]:
    path_to_id: Dict[str, int] = {}
    inserted: List[Dict[str, object]] = []

    for node in nodes:
        if node.parent_path:
            if node.parent_path not in path_to_id:
                raise RuntimeError(f"Parent path not found for {node.name}: {node.parent_path}")
            parent_id = path_to_id[node.parent_path]
            depth = node.parent_path.count("/") + 1
            path = f"{node.parent_path}/{node.name}"
        else:
            parent_id = None
            depth = 0
            path = f"{node.tab_code}/{node.name}"

        article_code = slugify(path)
        cur.execute(
            """
            INSERT INTO dim_planfact_accounting_articles (
                article_code,
                article_name,
                tab_code,
                tab_name,
                path,
                parent_article_id,
                depth,
                sort_order,
                is_group,
                is_locked,
                is_active,
                notes,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, NOW())
            ON CONFLICT (path) DO UPDATE
            SET
                article_code = EXCLUDED.article_code,
                article_name = EXCLUDED.article_name,
                tab_code = EXCLUDED.tab_code,
                tab_name = EXCLUDED.tab_name,
                parent_article_id = EXCLUDED.parent_article_id,
                depth = EXCLUDED.depth,
                sort_order = EXCLUDED.sort_order,
                is_group = EXCLUDED.is_group,
                is_locked = EXCLUDED.is_locked,
                is_active = TRUE,
                notes = EXCLUDED.notes,
                updated_at = NOW()
            RETURNING id, path, article_name, tab_code, depth, sort_order, is_group, is_locked;
            """,
            (
                article_code,
                node.name,
                node.tab_code,
                node.tab_name,
                path,
                parent_id,
                depth,
                node.sort_order,
                node.is_group,
                node.is_locked,
                node.notes,
            ),
        )
        row = cur.fetchone()
        path_to_id[path] = row["id"]
        inserted.append(
            {
                "id": row["id"],
                "path": row["path"],
                "article_name": row["article_name"],
                "tab_code": row["tab_code"],
                "depth": row["depth"],
                "sort_order": row["sort_order"],
                "is_group": row["is_group"],
                "is_locked": row["is_locked"],
            }
        )

    return inserted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    nodes = build_seed_nodes()
    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                ensure_schema(cur)
                inserted = upsert_nodes(cur, nodes)

                cur.execute(
                    """
                    SELECT
                        tab_code,
                        COUNT(*) AS article_count,
                        COUNT(*) FILTER (WHERE is_group) AS group_count
                    FROM dim_planfact_accounting_articles
                    GROUP BY tab_code
                    ORDER BY MIN(sort_order);
                    """
                )
                summary = cur.fetchall()

        print(
            json.dumps(
                {
                    "seeded_nodes": len(inserted),
                    "summary": summary,
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
