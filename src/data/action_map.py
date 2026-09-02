from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


ACTION_MAP_FORMAT = "mhws_static_action_request_set_map_v1"
ACTION_MAP_SCOPES = {
    **{f"Wp{index:02d}": None for index in range(14)},
    "Ammo": None,
}


@dataclass(frozen=True, slots=True)
class ActionMapRelation:
    scope: str
    action_identity: str
    action_guide_id: int | None
    action_order: int
    action_internal_name: str
    action_name_guid: str
    action_japanese_name: str
    fallback_name: str
    source: str
    resolution_methods: tuple[str, ...]
    rcol: str
    request_set_id: int
    key_hash: int
    source_request_set_ordinal: int

    @property
    def request_set_identity(self) -> tuple[str, str, int, int, int]:
        return (
            self.scope,
            self.rcol,
            self.request_set_id,
            self.key_hash,
            self.source_request_set_ordinal,
        )


@dataclass(frozen=True, slots=True)
class ActionMapDocument:
    path: Path
    relations: tuple[ActionMapRelation, ...]


def load_action_map(path: Path) -> ActionMapDocument:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Static ActionMap was not found: {path}. "
            "Generate it locally with motlist-to-json and copy it into MHWS-in-json."
        )
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"ActionMap root must be an object: {path}")
    if data.get("_format") != ACTION_MAP_FORMAT:
        raise ValueError(
            f"Unsupported ActionMap _format in {path}: {data.get('_format')!r}"
        )
    raw_relations = data.get("relations")
    if not isinstance(raw_relations, list):
        raise ValueError(f"ActionMap relations must be an array: {path}")

    relations = tuple(
        _parse_relation(value, index, path)
        for index, value in enumerate(raw_relations)
    )
    return ActionMapDocument(path=path, relations=relations)


def _parse_relation(value: Any, index: int, path: Path) -> ActionMapRelation:
    where = f"{path} relation #{index}"
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object")
    scope = _required_string(value, "scope", where)
    if scope not in ACTION_MAP_SCOPES:
        raise ValueError(f"{where} has unsupported scope: {scope!r}")
    action_guide_id = value.get("actionGuideId")
    if action_guide_id is not None:
        action_guide_id = _required_int(value, "actionGuideId", where)
    methods = value.get("resolutionMethods")
    if not isinstance(methods, list) or not all(
        isinstance(method, str) and method.strip() for method in methods
    ):
        raise ValueError(f"{where}.resolutionMethods must be a non-empty string array")
    rcol = _required_string(value, "rcol", where).replace("\\", "/")
    return ActionMapRelation(
        scope=scope,
        action_identity=_required_string(value, "actionIdentity", where),
        action_guide_id=action_guide_id,
        action_order=_required_int(value, "actionOrder", where),
        action_internal_name=_optional_string(value, "actionInternalName", where),
        action_name_guid=_optional_string(value, "actionNameGuid", where),
        action_japanese_name=_optional_string(value, "actionJapaneseName", where),
        fallback_name=_required_string(value, "fallbackName", where),
        source=_required_string(value, "source", where),
        resolution_methods=tuple(method.strip() for method in methods),
        rcol=rcol,
        request_set_id=_required_int(value, "requestSetId", where),
        key_hash=_required_int(value, "keyHash", where),
        source_request_set_ordinal=_required_int(
            value,
            "sourceRequestSetOrdinal",
            where,
        ),
    )


def _required_string(value: dict[str, Any], key: str, where: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{where}.{key} must be a non-empty string")
    return result.strip()


def _optional_string(value: dict[str, Any], key: str, where: str) -> str:
    result = value.get(key, "")
    if not isinstance(result, str):
        raise ValueError(f"{where}.{key} must be a string")
    return result.strip()


def _required_int(value: dict[str, Any], key: str, where: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise ValueError(f"{where}.{key} must be an integer")
    return result
