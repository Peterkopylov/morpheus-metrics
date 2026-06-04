#!/usr/bin/env python3
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


DEFAULT_BASE_URL = "https://morpheusshow.amocrm.ru"
DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env.amocrm"
DEFAULT_TIMEZONE = "Europe/Moscow"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_date(value: str, tz_name: str, end_of_day: bool) -> int:
    tz = ZoneInfo(tz_name)
    dt = datetime.strptime(value, "%Y-%m-%d")
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59, tzinfo=tz)
    else:
        dt = dt.replace(hour=0, minute=0, second=0, tzinfo=tz)
    return int(dt.timestamp())


def custom_field_value(lead: dict[str, Any], field_name: str) -> str:
    for field in lead.get("custom_fields_values", []) or []:
        if field.get("field_name") == field_name:
            values = field.get("values") or []
            return ", ".join(str(v.get("value")) for v in values if v.get("value") is not None)
    return ""


def build_url(base_url: str, pipeline_id: int, created_from: int, created_to: int, limit: int) -> str:
    query = urlencode(
        [
            ("filter[pipeline_id][0]", str(pipeline_id)),
            ("filter[created_at][from]", str(created_from)),
            ("filter[created_at][to]", str(created_to)),
            ("limit", str(limit)),
        ]
    )
    return f"{base_url.rstrip('/')}/api/v4/leads?{query}"


def fetch_json(url: str, token: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    with urlopen(request) as response:
        return json.load(response)


def print_summary(leads: list[dict[str, Any]]) -> None:
    print(f"count\t{len(leads)}")


def print_table(leads: list[dict[str, Any]]) -> None:
    status_map = {
        71461318: "Неразобранное",
        71461322: "Первичный контакт",
        71461326: "Концепт отправлен",
        71461330: "Назначена креативная встреча",
        71461334: "Проведена креативная встреча",
        71054854: "Договор отправлен",
        142: "Отзыв получен",
        143: "Закрыто и не реализовано",
    }
    headers = [
        "id",
        "name",
        "status",
        "need",
        "source",
        "loss_reason",
        "other_pipeline_flag",
        "city",
        "event_date",
        "participants",
    ]
    print("\t".join(headers))
    for lead in leads:
        print(
            "\t".join(
                [
                    str(lead.get("id", "")),
                    lead.get("name", ""),
                    status_map.get(lead.get("status_id"), str(lead.get("status_id", ""))),
                    custom_field_value(lead, "Потребность"),
                    custom_field_value(lead, "Источник"),
                    custom_field_value(lead, "Причина отказа"),
                    custom_field_value(lead, "Другая воронка (тех. поле)"),
                    custom_field_value(lead, "Город"),
                    custom_field_value(lead, "Дата мероприятия"),
                    custom_field_value(lead, "Количество участников")
                    or custom_field_value(lead, "Кол-во участников"),
                ]
            )
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safe amoCRM leads query helper with proper timezone and filter handling."
    )
    parser.add_argument("--date-from", required=True, help="Start date in YYYY-MM-DD")
    parser.add_argument("--date-to", required=True, help="End date in YYYY-MM-DD")
    parser.add_argument("--pipeline-id", type=int, required=True, help="amoCRM pipeline id")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="Timezone for date boundaries")
    parser.add_argument("--limit", type=int, default=250, help="Records per page")
    parser.add_argument("--base-url", default=os.environ.get("AMOCRM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--count-only", action="store_true", help="Print only lead count")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env_file(Path(args.env_file))

    token = os.environ.get("AMOCRM_LONG_LIVED_TOKEN")
    if not token:
        print(
            "AMOCRM_LONG_LIVED_TOKEN is missing. Put it into .env.amocrm or export it in the shell.",
            file=sys.stderr,
        )
        return 1

    created_from = parse_date(args.date_from, args.timezone, end_of_day=False)
    created_to = parse_date(args.date_to, args.timezone, end_of_day=True)
    url = build_url(args.base_url, args.pipeline_id, created_from, created_to, args.limit)
    payload = fetch_json(url, token)
    leads = payload.get("_embedded", {}).get("leads", [])

    if args.count_only:
        print_summary(leads)
    else:
        print_table(leads)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
