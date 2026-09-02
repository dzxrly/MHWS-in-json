from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


ACTION_VALUE_USER_DATA_TYPES = {
    "app.col_user_data.AttackParamPl",
    "app.col_user_data.AttackParamPlShell",
}

RCOL_FILE_RE = re.compile(r"\.rcol\.\d+\.json$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RequestSetKey:
    scope: str
    rcol: str
    request_set_id: int
    key_hash: int
    source_ordinal: int


@dataclass(frozen=True, slots=True)
class RequestSetRecord:
    key: RequestSetKey
    user_data_type: str
    properties: dict[str, Any]

    @property
    def sort_key(self) -> tuple[str, int, int, int]:
        return (
            self.key.rcol.casefold(),
            self.key.request_set_id,
            self.key.key_hash,
            self.key.source_ordinal,
        )


def load_action_value_request_sets(
    action_data_dir: Path,
) -> dict[str, tuple[RequestSetRecord, ...]]:
    action_data_dir = Path(action_data_dir)
    records: dict[str, list[RequestSetRecord]] = {
        **{f"Wp{index:02d}": [] for index in range(14)},
        "Ammo": [],
    }

    for scope in tuple(records):
        source_scope = "WpGunCommon" if scope == "Ammo" else scope
        source_dir = action_data_dir / source_scope
        if not source_dir.exists():
            continue
        for path in sorted(source_dir.rglob("*.rcol.*.json")):
            records[scope].extend(
                _load_rcol(path, action_data_dir, scope)
            )

    return {
        scope: tuple(sorted(scope_records, key=lambda record: record.sort_key))
        for scope, scope_records in records.items()
    }


def flatten_request_set(request_set: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    user_data = request_set.get("userData")
    if not isinstance(user_data, dict):
        return None

    user_data_type = next(
        (
            key
            for key in user_data
            if key in ACTION_VALUE_USER_DATA_TYPES
        ),
        None,
    )
    if user_data_type is None:
        return None
    payload = user_data.get(user_data_type)
    if not isinstance(payload, dict):
        return None

    flattened: dict[str, Any] = {}
    for key, value in request_set.items():
        if key == "nativeShapeColliders":
            continue
        if key == "userData":
            flattened["userDataType"] = user_data_type.rsplit(".", 1)[-1]
            for payload_key, payload_value in payload.items():
                _flatten(payload_value, payload_key, flattened)
            continue
        _flatten(value, key, flattened)
    return user_data_type, flattened


def rcol_logical_name(path: str | Path) -> str:
    return RCOL_FILE_RE.sub("", Path(path).name)


def normalized_rcol_name(path: str | Path) -> str:
    return re.sub(r"[^a-z0-9]", "", rcol_logical_name(path).casefold())


def _load_rcol(
    path: Path,
    action_data_dir: Path,
    scope: str,
) -> list[RequestSetRecord]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        return []

    relative_path = path.relative_to(action_data_dir).as_posix()
    records = []
    for source_ordinal, request_set in enumerate(data.get("requestSets", [])):
        if not isinstance(request_set, dict):
            continue
        flattened = flatten_request_set(request_set)
        if flattened is None:
            continue
        user_data_type, flattened_properties = flattened
        properties = {
            "sourceRequestSetOrdinal": source_ordinal,
            **flattened_properties,
        }
        records.append(
            RequestSetRecord(
                key=RequestSetKey(
                    scope=scope,
                    rcol=relative_path,
                    request_set_id=_int(request_set.get("requestSetID")),
                    key_hash=_int(request_set.get("keyHash")),
                    source_ordinal=source_ordinal,
                ),
                user_data_type=user_data_type,
                properties=properties,
            )
        )
    return records


def _flatten(value: Any, prefix: str, output: dict[str, Any]) -> None:
    if isinstance(value, dict):
        if len(value) == 1:
            wrapper_key, wrapper_value = next(iter(value.items()))
            if isinstance(wrapper_value, dict) and _is_type_wrapper(wrapper_key):
                _flatten(wrapper_value, prefix, output)
                return
        if not value:
            output[prefix] = "{}"
            return
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix and key else prefix or str(key)
            _flatten(child, child_prefix, output)
        return

    if isinstance(value, list):
        if not value or all(not isinstance(item, (dict, list)) for item in value):
            output[prefix] = json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            return
        for index, child in enumerate(value):
            _flatten(child, f"{prefix}[{index}]", output)
        return

    output[prefix] = value


def _is_type_wrapper(key: Any) -> bool:
    text = str(key)
    return not text or "." in text or "`" in text or "<" in text


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
