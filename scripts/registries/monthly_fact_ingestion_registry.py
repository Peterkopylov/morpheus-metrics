#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
IMPORTERS_DIR = ROOT / "scripts" / "importers" / "monthly_pnl"
REPORTS_DIR = ROOT / "artifacts" / "run_reports"
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
            key="planfact_monthly_pnl",
            label="PlanFact monthly P&L",
            source_system="planfact",
            script_path=IMPORTERS_DIR / "import_planfact_monthly_pnl_report_to_fact.py",
            source_run_id="planfact_monthly_pnl_v1",
            report_path=REPORTS_DIR / "planfact_monthly_pnl_report_to_fact_import_report.csv",
            implemented=True,
            description="Observed monthly PlanFact P&L import from the current Excel workbook contour.",
        ),
        MonthlyIngestionStep(
            key="monthly_pnl_calculated_rollups",
            label="Monthly P&L calculated rollups",
            source_system="monthly_pnl_calculated_rollup",
            script_path=IMPORTERS_DIR / "import_monthly_pnl_calculated_rollups_to_fact.py",
            source_run_id="monthly_pnl_calculated_rollup_v1",
            report_path=REPORTS_DIR / "monthly_pnl_calculated_rollups_to_fact_import_report.csv",
            implemented=True,
            description="Materialize calculated monthly P&L rollups and formula nodes back into fact.",
        ),
    )
