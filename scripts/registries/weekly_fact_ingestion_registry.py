#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
SCRIPTS_DIR = ROOT / "scripts"
IMPORTERS_DIR = SCRIPTS_DIR / "importers" / "weekly"
REPORTS_DIR = ROOT / "artifacts" / "run_reports"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class WeeklyIngestionStep:
    key: str
    label: str
    source_system: str
    script_path: Path | None
    source_run_id: str
    report_path: Path
    implemented: bool
    description: str
    extra_args: tuple[str, ...] = field(default_factory=tuple)


def last_full_week_start(today: date | None = None) -> date:
    current = today or datetime.now(MOSCOW_TZ).date()
    current_week_start = current - timedelta(days=current.weekday())
    return current_week_start - timedelta(days=7)


def weekly_steps() -> Sequence[WeeklyIngestionStep]:
    return (
        WeeklyIngestionStep(
            key="manual_weekly",
            label="Manual weekly tables",
            source_system="manual_table",
            script_path=IMPORTERS_DIR / "import_live_weekly_manual_to_fact.py",
            source_run_id="weekly_manual_live_v3",
            report_path=REPORTS_DIR / "live_weekly_manual_to_fact_import_report.csv",
            implemented=True,
            description="Google Sheets / fact_metrics weekly manual layer",
        ),
        WeeklyIngestionStep(
            key="erp_weekly_core",
            label="ERP weekly core",
            source_system="erp",
            script_path=IMPORTERS_DIR / "import_erp_weekly_to_fact.py",
            source_run_id="erp_weekly_v1",
            report_path=REPORTS_DIR / "erp_weekly_to_fact_import_report.csv",
            implemented=True,
            description="ERP base weekly layer: shows, visitors, primary ticket sales",
        ),
        WeeklyIngestionStep(
            key="erp_salary_variable_weekly",
            label="ERP salary variable weekly",
            source_system="erp",
            script_path=IMPORTERS_DIR / "import_erp_salary_variable_weekly_to_fact.py",
            source_run_id="erp_salary_variable_weekly_v1",
            report_path=REPORTS_DIR / "erp_salary_variable_weekly_to_fact_import_report.csv",
            implemented=True,
            description="ERP variable salaries + bonuses",
        ),
        WeeklyIngestionStep(
            key="erp_survey_satisfaction_weekly",
            label="ERP survey satisfaction weekly",
            source_system="erp",
            script_path=IMPORTERS_DIR / "import_erp_survey_satisfaction_weekly_to_fact.py",
            source_run_id="erp_survey_satisfaction_weekly_v1",
            report_path=REPORTS_DIR / "erp_survey_satisfaction_weekly_to_fact_import_report.csv",
            implemented=True,
            description="ERP post-show survey metrics",
        ),
        WeeklyIngestionStep(
            key="amocrm_weekly",
            label="amoCRM weekly",
            source_system="amocrm",
            script_path=IMPORTERS_DIR / "import_amocrm_weekly_to_fact.py",
            source_run_id="amocrm_weekly_v1",
            report_path=REPORTS_DIR / "amocrm_weekly_to_fact_import_report.csv",
            implemented=True,
            description="B2B leads / creative meetings / orders from amoCRM",
        ),
        WeeklyIngestionStep(
            key="yandex_metrica_weekly",
            label="Yandex Metrica weekly",
            source_system="yandex_metrica",
            script_path=IMPORTERS_DIR / "import_yandex_metrica_weekly_to_fact.py",
            source_run_id="yandex_metrica_weekly_v1",
            report_path=REPORTS_DIR / "yandex_metrica_weekly_to_fact_import_report.csv",
            implemented=True,
            description="Website visits by channel and show pages",
        ),
        WeeklyIngestionStep(
            key="yandex_metrica_tracked_purchase_visits_weekly",
            label="Yandex Metrica tracked purchase visits weekly",
            source_system="yandex_metrica",
            script_path=IMPORTERS_DIR / "import_yandex_metrica_tracked_purchase_visits_weekly_to_fact.py",
            source_run_id="yandex_metrica_tracked_purchase_visits_weekly_v1",
            report_path=REPORTS_DIR / "yandex_metrica_tracked_purchase_visits_weekly_to_fact_import_report.csv",
            implemented=True,
            description="Purchase-converted visits by channel and performance revenue from Yandex Metrica goals",
        ),
        WeeklyIngestionStep(
            key="yandex_direct_weekly",
            label="Yandex Direct weekly",
            source_system="yandex_direct",
            script_path=IMPORTERS_DIR / "import_yandex_direct_weekly_to_fact.py",
            source_run_id="yandex_direct_weekly_v1",
            report_path=REPORTS_DIR / "yandex_direct_weekly_to_fact_import_report.csv",
            implemented=True,
            description="Primary weekly marketing costs from Yandex Direct; revenue is sourced from Yandex Metrica",
        ),
    )
