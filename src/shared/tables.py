"""Ordered table operations used while preparing owned output rows."""

from collections.abc import Callable

Table = list[dict]
FrameLoader = Callable[[str], Table | None]


def index_by(frame: Table, key: str, value: str) -> dict:
    return {row.get(key): row.get(value) for row in frame if row.get(key) is not None and value in row}


def map_column(frame: Table | None, column: str, mapping: dict) -> None:
    if frame is None or not mapping:
        return
    for row in frame:
        if column in row:
            row[column] = mapped(row[column], mapping)


def mapped(value, mapping: dict):
    if isinstance(value, list):
        return [mapping.get(v, v) for v in value if v]
    return mapping.get(value, value)


def as_list(value) -> list:
    if isinstance(value, list):
        return value
    return [] if value is None or value == "" else [value]


def move_after(frame: Table, column: str, after: str) -> None:
    for row in frame:
        if column not in row or after not in row:
            continue
        value = row.pop(column)
        insert_key_after(row, after, column, value)


def move_to_end(frame: Table, columns: list[str]) -> None:
    for row in frame:
        for column in columns:
            if column in row:
                row[column] = row.pop(column)


def columns(frame: Table) -> list[str]:
    columns = []
    seen = set()
    for row in frame:
        for column in row:
            if column not in seen:
                columns.append(column)
                seen.add(column)
    return columns


def has_columns(frame: Table, *required: str) -> bool:
    return set(required).issubset(columns(frame))


def drop(frame: Table, columns: list[str]) -> None:
    for row in frame:
        for column in columns:
            row.pop(column, None)


def rename(frame: Table, old: str, new: str) -> None:
    for row in frame:
        if old not in row:
            continue
        rebuilt = {}
        for key, value in row.items():
            rebuilt[new if key == old else key] = value
        row.clear()
        row.update(rebuilt)


def insert_after(frame: Table, after: str, column: str, values: list) -> None:
    for row, value in zip(frame, values):
        row.pop(column, None)
        if after in row:
            insert_key_after(row, after, column, value)
        else:
            row[column] = value


def insert_key_after(row: dict, after: str, key: str, value) -> None:
    rebuilt = {}
    for old_key, old_value in row.items():
        rebuilt[old_key] = old_value
        if old_key == after:
            rebuilt[key] = value
    row.clear()
    row.update(rebuilt)
