from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path("/Users/Peter/Documents/Morpheus Metrics")
DEFAULT_INPUT = Path("/Users/Peter/Downloads/Метрики - План - Sources - Metrika.csv")
DEFAULT_MAIN_OUTPUT = ROOT / "generated" / "metric_sources_v2.csv"
DEFAULT_DICT_OUTPUT = ROOT / "generated" / "legacy_seed" / "metric_dimension_dictionaries_v2.csv"


def norm_business_unit(value: str) -> str:
    mapping = {
        "b2c Moscow": "b2c_moscow",
        "b2c SPB": "b2c_spb",
        "b2b": "b2b",
        "Franchise": "franchise",
        "Immersivny": "immersivny",
        "general": "general",
        "": "",
    }
    return mapping.get(value, value.strip().lower().replace(" ", "_"))


def norm_scope(value: str, kind: str) -> str:
    if not value:
        return ""

    value = value.strip()
    if value in {"general", "General"}:
        return "general"

    mapping = {
        ("b2c shows names", "show"): "b2c_show_names",
        ("b2b shows names", "show"): "b2b_show_names",
        ("b2c agents names", "partner"): "b2c_partner_names",
        ("b2b agents names", "partner"): "b2b_partner_names",
        ("marketing channels names", "channel"): "marketing_channel_names",
    }
    return mapping.get((value, kind), value.strip().lower().replace(" ", "_"))


def split_csvish(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def build_outputs(
    src: Path = DEFAULT_INPUT,
    main_out: Path = DEFAULT_MAIN_OUTPUT,
    dict_out: Path = DEFAULT_DICT_OUTPUT,
) -> tuple[int, int]:
    source_map = {
        "Яндекс.Метрика": "yandex_metrica",
        "Яндекс.Директ": "yandex_direct",
        "PlanFact": "planfact",
        "ERP": "erp",
        "Таблица": "manual_table",
        "Агрегат": "aggregate",
        "Airtable": "airtable",
        "AMOCRM": "amocrm",
        "пока нет": "not_available_yet",
        "": "",
    }

    with src.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    result: list[dict[str, str | int]] = []
    for idx, row in enumerate(rows, start=2):
        sources = split_csvish(row["Source"]) or [""]
        frequencies = split_csvish(row["Frequency minimal"])

        for i, source_label in enumerate(sources):
            if not frequencies:
                frequency = ""
            elif len(frequencies) == len(sources):
                frequency = frequencies[i]
            elif len(frequencies) == 1:
                frequency = frequencies[0]
            else:
                frequency = frequencies[min(i, len(frequencies) - 1)]

            source_system = source_map.get(
                source_label, source_label.strip().lower().replace(" ", "_")
            )

            if source_label == "пока нет":
                availability_status = "not_available_yet"
            elif source_label == "":
                availability_status = "unspecified"
            else:
                availability_status = "available"

            result.append(
                {
                    "metric_name": row["Metric name"].strip(),
                    "business_unit_scope": norm_business_unit(row["Business unit"].strip()),
                    "show_scope": norm_scope(row["Show"].strip(), "show"),
                    "partner_scope": norm_scope(row["Agent"].strip(), "partner"),
                    "channel_scope": norm_scope(row["Channel"].strip(), "channel"),
                    "source_system": source_system,
                    "source_label": source_label,
                    "minimal_frequency": frequency,
                    "availability_status": availability_status,
                    "credibility": row["Credibility"].strip(),
                    "source_row_ref": idx,
                }
            )

    main_out.parent.mkdir(parents=True, exist_ok=True)
    main_fields = [
        "metric_name",
        "business_unit_scope",
        "show_scope",
        "partner_scope",
        "channel_scope",
        "source_system",
        "source_label",
        "minimal_frequency",
        "availability_status",
        "credibility",
        "source_row_ref",
    ]
    with main_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=main_fields)
        writer.writeheader()
        writer.writerows(result)

    known = defaultdict(list)
    known["business_unit_scope"] = [
        ("b2c_moscow", "B2C Moscow"),
        ("b2c_spb", "B2C SPB"),
        ("b2b", "B2B"),
        ("franchise", "Franchise"),
        ("immersivny", "Immersivny"),
        ("general", "General aggregate"),
    ]
    known["show_scope"] = [
        ("b2c_show_names", "Expand into all B2C show names"),
        ("b2b_show_names", "Expand into all B2B show names"),
        ("general", "General aggregate"),
    ]
    known["partner_scope"] = [
        ("b2c_partner_names", "Expand into all B2C partners/distributors"),
        ("b2b_partner_names", "Expand into all B2B partner/agent names"),
    ]
    known["channel_scope"] = [
        ("marketing_channel_names", "Expand into all marketing channel names"),
    ]

    dictionary_rows: list[dict[str, str]] = []

    def add(group: str, key: str, label: str, note: str = "") -> None:
        dictionary_rows.append(
            {
                "dictionary_group": group,
                "dictionary_key": key,
                "value_key": label,
                "value_label": label,
                "note": note,
            }
        )

    for key, label in known["business_unit_scope"]:
        add("business_unit_scope", key, key, label)
    for key, label in known["show_scope"]:
        add("show_scope", key, key, label)
    for key, label in known["partner_scope"]:
        add("partner_scope", key, key, label)
    for key, label in known["channel_scope"]:
        add("channel_scope", key, key, label)

    for show in [
        "Ответ Гиппократа",
        "До свадьбы доживёт",
        "22'07",
        "ВДОХ",
        "Иное место",
        "Загадка амулета",
        "Судный день",
    ]:
        add("scope_values", "b2c_show_names", show)

    for partner in ["кассир", "яндекс.афиша", "афиша.ру", "тикетлэнд", "others"]:
        add("scope_values", "b2c_partner_names", partner)

    for channel in ["direct", "organic", "social", "partners", "referral", "email", "other"]:
        add("scope_values", "marketing_channel_names", channel)

    for placeholder in ["<fill_b2b_show_names>", "<fill_b2b_partner_names>"]:
        dictionary_key = "b2b_show_names" if "show" in placeholder else "b2b_partner_names"
        add("scope_values", dictionary_key, placeholder, "Placeholder: fill with actual values")

    with dict_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "dictionary_group",
                "dictionary_key",
                "value_key",
                "value_label",
                "note",
            ],
        )
        writer.writeheader()
        writer.writerows(dictionary_rows)

    return len(result), len(dictionary_rows)


if __name__ == "__main__":
    main_rows, dictionary_rows = build_outputs()
    print(f"metric rows: {main_rows}")
    print(f"dictionary rows: {dictionary_rows}")
    print(f"main: {DEFAULT_MAIN_OUTPUT}")
    print(f"dictionaries: {DEFAULT_DICT_OUTPUT}")
