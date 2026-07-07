import json
import re
from pathlib import Path
from typing import Any

from src.data.text_db import ILLEGAL_CHARS_RE, TextDB

GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
ENUM_RE = re.compile(r"^\[[-\d]+\]\s*(.*)$")


def load_user3_table(path: Path, text_db: TextDB | None = None) -> list[dict]:
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    for record in _records(data):
        raw_row = _row_data(record)
        row = {}
        for key, value in raw_row.items():
            row[_clean_key(key)] = normalize(value, text_db)
        rows.append(row)
    return rows


def normalize(value: Any, text_db: TextDB | None = None) -> Any:
    if isinstance(value, dict):
        if len(value) == 1:
            inner = next(iter(value.values()))
            if isinstance(inner, dict) and "_Value" in inner:
                return normalize(inner["_Value"], text_db)
        return {_clean_key(k): normalize(v, text_db) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v, text_db) for v in value]
    if isinstance(value, str):
        value = ILLEGAL_CHARS_RE.sub("", value)
        match = ENUM_RE.match(value)
        if match:
            value = match.group(1)
        if value == "INVALID":
            return ""
        if text_db and GUID_RE.match(value):
            return text_db.get(value) or ""
    return value


def _records(data: Any) -> list:
    root = data[0] if isinstance(data, list) and data else data
    if not isinstance(root, dict):
        return []
    payload = root[next(iter(root))] if len(root) == 1 else root
    if not isinstance(payload, dict):
        return []
    for key in ("_Values", "_DataList"):
        if isinstance(payload.get(key), list):
            return payload[key]
    for value in payload.values():
        if isinstance(value, list):
            return value
    return []


def _row_data(record: Any) -> dict:
    if not isinstance(record, dict):
        return {"Value": record}
    for key, value in record.items():
        if key.endswith(".cData") and isinstance(value, dict):
            return value
    if len(record) == 1 and isinstance(next(iter(record.values())), dict):
        return next(iter(record.values()))
    return record


def _clean_key(key: str) -> str:
    key = str(key)
    return key[1:] if key.startswith("_") else key
