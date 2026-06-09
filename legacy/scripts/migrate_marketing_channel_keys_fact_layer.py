#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import psycopg2


CHANNEL_REMAP = {
    "direct": "perfomance",
    "smm": "social",
    "pos": "other",
}


def fetch_counts(conn, table_name: str) -> list[tuple[str, int]]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT channel_name, COUNT(*)
            FROM {table_name}
            WHERE channel_name = ANY(%s)
            GROUP BY channel_name
            ORDER BY channel_name
            """,
            (list(CHANNEL_REMAP.keys()),),
        )
        return [(str(channel_name), int(count)) for channel_name, count in cur.fetchall()]


def migrate_fact_metric_observation(conn) -> int:
    total = 0
    with conn.cursor() as cur:
        for old_key, new_key in CHANNEL_REMAP.items():
            cur.execute(
                """
                UPDATE fact_metric_observation
                SET channel_name = %s
                WHERE channel_name = %s
                """,
                (new_key, old_key),
            )
            total += cur.rowcount
    return total


def migrate_calculated_metric_value(conn) -> int:
    total = 0
    with conn.cursor() as cur:
        for old_key, new_key in CHANNEL_REMAP.items():
            cur.execute(
                """
                UPDATE calculated_metric_value
                SET channel_name = %s
                WHERE channel_name = %s
                """,
                (new_key, old_key),
            )
            total += cur.rowcount
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(args.database_url)
    try:
        before_fact = fetch_counts(conn, "fact_metric_observation")
        before_calc = fetch_counts(conn, "calculated_metric_value")

        migrated_fact = 0
        migrated_calc = 0
        if not args.dry_run:
            with conn:
                migrated_fact = migrate_fact_metric_observation(conn)
                migrated_calc = migrate_calculated_metric_value(conn)

        after_fact = fetch_counts(conn, "fact_metric_observation")
        after_calc = fetch_counts(conn, "calculated_metric_value")

        print(
            json.dumps(
                {
                    "mode": "dry_run" if args.dry_run else "apply",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "channel_remap": CHANNEL_REMAP,
                    "before_fact_metric_observation": before_fact,
                    "before_calculated_metric_value": before_calc,
                    "migrated_fact_metric_observation_rows": migrated_fact,
                    "migrated_calculated_metric_value_rows": migrated_calc,
                    "after_fact_metric_observation": after_fact,
                    "after_calculated_metric_value": after_calc,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
