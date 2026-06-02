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
class MonthlyKpiIngestionStep:
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


def monthly_kpi_steps() -> Sequence[MonthlyKpiIngestionStep]:
    return (
        MonthlyKpiIngestionStep(
            key="erp_monthly_core",
            label="ERP monthly core",
            source_system="erp",
            script_path=SCRIPTS_DIR / "import_erp_monthly_to_fact.py",
            source_run_id="erp_monthly_v1",
            report_path=GENERATED_DIR / "erp_monthly_to_fact_import_report.csv",
            implemented=True,
            description="ERP base monthly layer: shows, visitors, primary ticket sales.",
        ),
        MonthlyKpiIngestionStep(
            key="erp_salary_variable_monthly",
            label="ERP salary variable monthly",
            source_system="erp",
            script_path=SCRIPTS_DIR / "import_erp_salary_variable_monthly_to_fact.py",
            source_run_id="erp_salary_variable_monthly_v1",
            report_path=GENERATED_DIR / "erp_salary_variable_monthly_to_fact_import_report.csv",
            implemented=True,
            description="ERP monthly variable salaries + bonuses.",
        ),
        MonthlyKpiIngestionStep(
            key="erp_survey_satisfaction_monthly",
            label="ERP survey satisfaction monthly",
            source_system="erp",
            script_path=SCRIPTS_DIR / "import_erp_survey_satisfaction_monthly_to_fact.py",
            source_run_id="erp_survey_satisfaction_monthly_v1",
            report_path=GENERATED_DIR / "erp_survey_satisfaction_monthly_to_fact_import_report.csv",
            implemented=True,
            description="ERP monthly post-show survey metrics.",
        ),
        MonthlyKpiIngestionStep(
            key="amocrm_monthly",
            label="amoCRM monthly",
            source_system="amocrm",
            script_path=SCRIPTS_DIR / "import_amocrm_monthly_to_fact.py",
            source_run_id="amocrm_monthly_v1",
            report_path=GENERATED_DIR / "amocrm_monthly_to_fact_import_report.csv",
            implemented=True,
            description="B2B monthly leads / creative meetings / orders from amoCRM.",
        ),
        MonthlyKpiIngestionStep(
            key="yandex_metrica_monthly",
            label="Yandex Metrica monthly",
            source_system="yandex_metrica",
            script_path=SCRIPTS_DIR / "import_yandex_metrica_monthly_to_fact.py",
            source_run_id="yandex_metrica_monthly_v1",
            report_path=GENERATED_DIR / "yandex_metrica_monthly_to_fact_import_report.csv",
            implemented=True,
            description="Monthly website visits by channel and show pages from Yandex Metrica.",
        ),
        MonthlyKpiIngestionStep(
            key="yandex_metrica_tracked_purchase_visits_monthly",
            label="Yandex Metrica tracked purchase visits monthly",
            source_system="yandex_metrica",
            script_path=SCRIPTS_DIR / "import_yandex_metrica_tracked_purchase_visits_monthly_to_fact.py",
            source_run_id="yandex_metrica_tracked_purchase_visits_monthly_v1",
            report_path=GENERATED_DIR / "yandex_metrica_tracked_purchase_visits_monthly_to_fact_import_report.csv",
            implemented=True,
            description="Monthly purchase-converted visits by channel and performance revenue from Yandex Metrica goals.",
        ),
        MonthlyKpiIngestionStep(
            key="yandex_direct_monthly",
            label="Yandex Direct monthly",
            source_system="yandex_direct",
            script_path=SCRIPTS_DIR / "import_yandex_direct_monthly_to_fact.py",
            source_run_id="yandex_direct_monthly_v1",
            report_path=GENERATED_DIR / "yandex_direct_monthly_to_fact_import_report.csv",
            implemented=True,
            description="Primary monthly marketing costs from Yandex Direct; revenue is sourced from Yandex Metrica.",
        ),
    )
