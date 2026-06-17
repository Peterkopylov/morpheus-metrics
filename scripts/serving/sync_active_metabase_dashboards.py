#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
REGISTRY_PATH = ROOT / "serving" / "dashboard_registry.csv"
SERVING_DIR = ROOT / "scripts" / "serving"
SCRIPTS_DIR = ROOT / "scripts"


@dataclass
class MetabaseConfig:
    base_url: str
    api_key: str


def api_request(config: MetabaseConfig, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    url = f"{config.base_url.rstrip('/')}{path}"
    headers = {
        "x-api-key": config.api_key,
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else None
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc


def rebuild_script(script_name: str, database_url: str) -> dict[str, str]:
    script_path = SERVING_DIR / script_name
    subprocess.run(
        ["python3", str(script_path), "--database-url", database_url],
        check=True,
        capture_output=True,
        text=True,
    )
    return {"script": script_name, "status": "success"}


def run_script(script_path: Path, database_url: str, extra_args: list[str] | None = None) -> dict[str, str]:
    cmd = ["python3", str(script_path), "--database-url", database_url]
    if extra_args:
        cmd.extend(extra_args)
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
    )
    return {"script": script_path.name, "status": "success"}


def refresh_show_slot_attendance_snapshot(database_url: str) -> dict[str, str]:
    script_path = SCRIPTS_DIR / "refresh_erp_show_slot_attendance_snapshot.py"
    return run_script(script_path, database_url)


def active_dashboard_rows() -> list[dict[str, str]]:
    with REGISTRY_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    result = []
    for row in rows:
        if row.get("tool") != "metabase":
            continue
        if row.get("status") != "active":
            continue
        if not (row.get("dashboard_id") or "").strip():
            continue
        result.append(row)
    return result


def dashboards_for_scope(scope: str) -> list[dict[str, str]]:
    rows = active_dashboard_rows()
    if scope == "all":
        return rows
    if scope == "weekly":
        keys = {
            "weekly-metrics-latest-comparison",
            "weekly-metrics-yoy-fact",
            "moscow-weekly-metrics-charts-fact",
            "spb-weekly-metrics-charts-fact",
            "fact-ingestion-technical-monitor",
            "weekly-marketing-operational-monitor",
            "show-performance",
            "moscow-show-slot-attendance",
            "spb-show-slot-attendance",
            "moscow-show-slot-average-guests",
            "spb-show-slot-average-guests",
        }
        return [row for row in rows if row["dashboard_key"] in keys]
    if scope == "monthly_kpi":
        keys = {
            "monthly-marketing-operational-monitor",
            "fact-ingestion-technical-monitor",
            "moscow-show-slot-attendance",
            "spb-show-slot-attendance",
            "moscow-show-slot-average-guests",
            "spb-show-slot-average-guests",
        }
        return [row for row in rows if row["dashboard_key"] in keys]
    if scope == "monthly_pnl":
        keys = {
            "monthly-marketing-operational-monitor",
            "monthly-pnl-city-analytics",
            "fact-ingestion-technical-monitor",
            "moscow-show-slot-attendance",
            "spb-show-slot-attendance",
            "moscow-show-slot-average-guests",
            "spb-show-slot-average-guests",
        }
        return [row for row in rows if row["dashboard_key"] in keys]
    raise ValueError(f"Unsupported scope: {scope}")


def rebuilds_for_scope(scope: str) -> list[str]:
    if scope == "weekly":
        return [
            "refresh_erp_show_slot_attendance_snapshot.py",
            "rebuild_show_slot_attendance_dashboard_base.py",
            "rebuild_weekly_fact_metrics_yoy_views.py",
            "rebuild_weekly_marketing_operational_view.py",
            "rebuild_show_performance_dashboard_base.py",
            "rebuild_fact_ingestion_technical_monitor_view.py",
        ]
    if scope == "monthly_kpi":
        return [
            "refresh_erp_show_slot_attendance_snapshot.py",
            "rebuild_show_slot_attendance_dashboard_base.py",
            "rebuild_monthly_marketing_operational_view.py",
            "rebuild_fact_ingestion_technical_monitor_view.py",
        ]
    if scope == "monthly_pnl":
        return [
            "refresh_erp_show_slot_attendance_snapshot.py",
            "rebuild_show_slot_attendance_dashboard_base.py",
            "rebuild_monthly_marketing_operational_view.py",
            "rebuild_monthly_pnl_city_analytics_view.py",
            "rebuild_fact_ingestion_technical_monitor_view.py",
        ]
    if scope == "all":
        return [
            "refresh_erp_show_slot_attendance_snapshot.py",
            "rebuild_show_slot_attendance_dashboard_base.py",
            "rebuild_weekly_fact_metrics_yoy_views.py",
            "rebuild_weekly_marketing_operational_view.py",
            "rebuild_monthly_marketing_operational_view.py",
            "rebuild_show_performance_dashboard_base.py",
            "rebuild_monthly_pnl_city_analytics_view.py",
            "rebuild_fact_ingestion_technical_monitor_view.py",
        ]
    raise ValueError(f"Unsupported scope: {scope}")


def touch_dashboard_and_cards(config: MetabaseConfig, dashboard_id: int) -> dict[str, Any]:
    dashboard = api_request(config, "GET", f"/api/dashboard/{dashboard_id}")
    api_request(
        config,
        "PUT",
        f"/api/dashboard/{dashboard_id}",
        {
            "name": dashboard["name"],
            "description": dashboard.get("description") or "",
            "collection_id": dashboard.get("collection_id"),
            "parameters": dashboard.get("parameters") or [],
            "points_of_interest": dashboard.get("points_of_interest") or None,
            "caveats": dashboard.get("caveats") or None,
            "width": dashboard.get("width", 24),
        },
    )

    touched_cards: list[int] = []
    for dashcard in dashboard.get("dashcards") or []:
        card = dashcard.get("card") or {}
        card_id = card.get("id")
        if not card_id:
            continue
        api_request(
            config,
            "PUT",
            f"/api/card/{card_id}",
            {
                "name": card.get("name"),
                "description": card.get("description") or None,
                "display": card.get("display"),
                "dataset_query": card.get("dataset_query"),
                "visualization_settings": card.get("visualization_settings") or {},
                "collection_id": card.get("collection_id"),
                "cache_ttl": card.get("cache_ttl"),
            },
        )
        touched_cards.append(card_id)
    return {
        "dashboard_id": dashboard_id,
        "dashboard_name": dashboard["name"],
        "touched_card_count": len(touched_cards),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--metabase-url", required=True)
    parser.add_argument("--metabase-api-key", required=True)
    parser.add_argument(
        "--scope",
        choices=["weekly", "monthly_kpi", "monthly_pnl", "all"],
        default="all",
    )
    args = parser.parse_args()

    config = MetabaseConfig(args.metabase_url, args.metabase_api_key)
    rebuild_results = []
    for script_name in rebuilds_for_scope(args.scope):
        if script_name == "refresh_erp_show_slot_attendance_snapshot.py":
            rebuild_results.append(refresh_show_slot_attendance_snapshot(args.database_url))
        else:
            rebuild_results.append(rebuild_script(script_name, args.database_url))
    dashboards = dashboards_for_scope(args.scope)
    dashboard_results = [touch_dashboard_and_cards(config, int(row["dashboard_id"])) for row in dashboards]

    print(
        json.dumps(
            {
                "scope": args.scope,
                "rebuilds": rebuild_results,
                "dashboards": dashboard_results,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
