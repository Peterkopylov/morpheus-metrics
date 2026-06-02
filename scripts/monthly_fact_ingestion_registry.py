#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
SCRIPTS_DIR = ROOT / "scripts"
GENERATED_DIR = ROOT / "generated"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class MonthlyIngestionStep:
    key: str
    label: str
    source_system: str
    script_path: Path | None
    source_run_id: str
    report_path: Path
    implemented: bool
    description: str
    extra_args: tuple[str, ...] = field(default_factory=tuple)


def current_month_start(today: date | None = None) -> date:
    current = today or datetime.now(MOSCOW_TZ).date()
    return current.replace(day=1)


def monthly_steps() -> Sequence[MonthlyIngestionStep]:
    return (
        MonthlyIngestionStep(
            key="historical_monthly_economics",
            label="Historical monthly economics sheet",
            source_system="google_sheets_monthly_economics_historical",
            script_path=SCRIPTS_DIR / "import_historical_monthly_economics_sheet_to_fact.py",
            source_run_id="historical_monthly_economics_sheet_v1",
            report_path=GENERATED_DIR / "historical_monthly_economics_sheet_to_fact_import_report.csv",
            implemented=True,
            description="Main historical monthly P&L leaf-only import from Google Sheets.",
        ),
        MonthlyIngestionStep(
            key="historical_monthly_economics_prototype_extension",
            label="Historical monthly prototype extension",
            source_system="google_sheets_monthly_economics_historical",
            script_path=SCRIPTS_DIR / "import_historical_monthly_economics_prototype_extension_to_fact.py",
            source_run_id="historical_monthly_economics_prototype_extension_v1",
            report_path=GENERATED_DIR / "historical_monthly_economics_new_prototype_import_report.csv",
            implemented=True,
            description="Supplemental historical monthly backfill for missing prototype months.",
        ),
        MonthlyIngestionStep(
            key="planfact_monthly_pnl",
            label="PlanFact monthly P&L",
            source_system="planfact",
            script_path=SCRIPTS_DIR / "import_planfact_monthly_pnl_report_to_fact.py",
            source_run_id="planfact_monthly_pnl_v1",
            report_path=GENERATED_DIR / "planfact_monthly_pnl_report_to_fact_import_report.csv",
            implemented=True,
            description="Observed monthly PlanFact P&L import by business unit and total workbook.",
        ),
        MonthlyIngestionStep(
            key="manual_dividends_total_history",
            label="Manual dividends total history",
            source_system="manual_dividends_total_history",
            script_path=SCRIPTS_DIR / "import_manual_dividends_total_history_to_fact.py",
            source_run_id="manual_dividends_total_history_v1",
            report_path=GENERATED_DIR / "manual_dividends_total_history_import_report.csv",
            implemented=True,
            description="Patch missing total-month dividends from curated manual history.",
        ),
        MonthlyIngestionStep(
            key="historical_pnl_rollup_backfill",
            label="Historical P&L rollup backfill",
            source_system="historical_leaf_rollup_backfill",
            script_path=SCRIPTS_DIR / "import_historical_pnl_rollup_backfill_to_fact.py",
            source_run_id="historical_leaf_rollup_backfill_v1",
            report_path=GENERATED_DIR / "historical_leaf_rollup_backfill_import_report.csv",
            implemented=True,
            description="Synthetic monthly rollups for historical Variable costs and Fixed costs gaps.",
        ),
    )
