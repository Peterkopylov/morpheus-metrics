#!/usr/bin/env python3
import argparse
from pathlib import Path

import psycopg2


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
SQL_PATH = ROOT / "sql" / "create_weekly_marketing_operational_view.sql"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()

    sql = SQL_PATH.read_text(encoding="utf-8")
    conn = psycopg2.connect(args.database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
