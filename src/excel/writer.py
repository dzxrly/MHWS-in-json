from pathlib import Path
from typing import Any

from openpyxl import Workbook

from src.excel.style import style_workbook

INVALID_SHEET_CHARS = str.maketrans({c: "_" for c in r'[]:*?/\\'})


def write_workbook(path: Path, sheets: dict[str, list[dict]], max_width: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    first = True
    for sheet_name, rows in sheets.items():
        sheet = workbook.active if first else workbook.create_sheet()
        first = False
        sheet.title = _sheet_name(sheet_name)
        columns = _columns(rows)
        sheet.append(columns)
        for row in rows:
            sheet.append([_cell(row.get(column)) for column in columns])
    style_workbook(workbook, max_width)
    workbook.save(path)
    return path


def _sheet_name(name: str) -> str:
    return name.translate(INVALID_SHEET_CHARS)[:31] or "Sheet"


def _columns(rows: list[dict]) -> list[str]:
    columns = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                columns.append(key)
                seen.add(key)
    return columns


def _cell(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return str(value)
    if isinstance(value, str) and value.startswith("="):
        return "'" + value
    return value
