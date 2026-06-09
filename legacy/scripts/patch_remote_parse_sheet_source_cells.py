#!/usr/bin/env python3
from pathlib import Path


path = Path("/opt/analytics/parser/parse_sheet.py")
text = path.read_text(encoding="utf-8")

old = """def get_cell(row: Sequence[str], idx: int) -> str:
    return row[idx] if 0 <= idx < len(row) else ""


def detect_layout_and_date_row(data: Sequence[Sequence[str]]) -> Tuple[int, Layout]:
"""
new = """def get_cell(row: Sequence[str], idx: int) -> str:
    return row[idx] if 0 <= idx < len(row) else ""


def col_to_a1(col_number_1_based: int) -> str:
    result = ""
    num = col_number_1_based
    while num > 0:
        num, rem = divmod(num - 1, 26)
        result = chr(65 + rem) + result
    return result


def build_sheet_cell_a1(row_number_1_based: int, col_number_1_based: int) -> str:
    return f"{col_to_a1(col_number_1_based)}{row_number_1_based}"


def build_sheet_cell_url(sheet_id: str, gid: str, source_tab: str, row_number_1_based: int, col_number_1_based: int) -> str:
    a1 = build_sheet_cell_a1(row_number_1_based, col_number_1_based)
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit?gid={gid}#gid={gid}&range={source_tab}!{a1}"


def detect_layout_and_date_row(data: Sequence[Sequence[str]]) -> Tuple[int, Layout]:
"""

if old not in text:
    raise SystemExit("helper anchor not found")
text = text.replace(old, new, 1)

replacements = [
    (
        """        row_order,
        col_order
    ) VALUES (
""",
        """        row_order,
        col_order,
        source_cell_a1,
        source_cell_url
    ) VALUES (
""",
    ),
    (
        """        %(row_order)s,
        %(col_order)s
    )
""",
        """        %(row_order)s,
        %(col_order)s,
        %(source_cell_a1)s,
        %(source_cell_url)s
    )
""",
    ),
    (
        """        value_type = EXCLUDED.value_type,
        row_order = EXCLUDED.row_order,
        col_order = EXCLUDED.col_order,
        loaded_at = NOW()
""",
        """        value_type = EXCLUDED.value_type,
        row_order = EXCLUDED.row_order,
        col_order = EXCLUDED.col_order,
        source_cell_a1 = EXCLUDED.source_cell_a1,
        source_cell_url = EXCLUDED.source_cell_url,
        loaded_at = NOW()
""",
    ),
    (
        """                    "row_order": metric_row.row_idx,
                    "col_order": period.col_idx + 1,
                })
""",
        """                    "row_order": metric_row.row_idx,
                    "col_order": period.col_idx + 1,
                    "source_cell_a1": build_sheet_cell_a1(metric_row.row_idx, period.col_idx + 1),
                    "source_cell_url": build_sheet_cell_url(args.sheet_id, args.gid, source_tab, metric_row.row_idx, period.col_idx + 1),
                })
""",
    ),
]

for old_snippet, new_snippet in replacements:
    if old_snippet not in text:
        raise SystemExit(f"replacement anchor not found:\\n{old_snippet}")
    text = text.replace(old_snippet, new_snippet, 1)

path.write_text(text, encoding="utf-8")
print("patched remote parse_sheet.py")
