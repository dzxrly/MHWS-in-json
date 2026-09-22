"""Common Excel-safe values and the database's width measurement policy."""

import re
from typing import Any

HAN_RE = re.compile(r"[\u4e00-\u9fff]")
INVALID_SHEET_CHARS = str.maketrans({c: "_" for c in r'[]:*?/\\'})


def safe_cell(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        value = str(value)
    if isinstance(value, str) and value.startswith("="):
        return "'" + value
    return value


def sheet_name(name: str) -> str:
    return name.translate(INVALID_SHEET_CHARS)[:31] or "Sheet"


def text_width(value: Any) -> float:
    if value is None:
        return 0.0
    width = 0.0
    for char in str(value):
        width += 1.2 if char.isascii() and char.isalnum() else 2.0 if HAN_RE.search(char) else 1.0
    return width
