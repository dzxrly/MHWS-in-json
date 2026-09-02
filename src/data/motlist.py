from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


MOTLIST_JSON_FORMAT = "re_engine_motlist_action_tracks_v1"
MOTLIST_JSON_RE = re.compile(r"\.motlist(?:\.\d+)?\.json$", re.IGNORECASE)
WEAPON_SCOPE_RE = re.compile(r"^wp(\d{2})$", re.IGNORECASE)
WEAPON_MOTION_RE = re.compile(r"^wp(\d{2})_", re.IGNORECASE)
PLAYER_MOTION_PREFIX = "stm/motion/player/"


@dataclass(frozen=True, slots=True)
class MotlistRequestSetRelation:
    scope: str
    request_set_id: int
    motion_name: str
    motion_id: int
    source_path: str
    source_json: str

    @property
    def sort_key(self) -> tuple[str, int, str, int, str, str]:
        return (
            self.scope,
            self.request_set_id,
            self.motion_name.casefold(),
            self.motion_id,
            self.source_path.casefold(),
            self.source_json.casefold(),
        )


@dataclass(frozen=True, slots=True)
class MotlistRelationCatalog:
    root: Path
    documents: int
    documents_with_mappings: int
    source_mappings: int
    unnamed_mappings: int
    unscoped_mappings: int
    relations: tuple[MotlistRequestSetRelation, ...]


def load_motlist_request_set_relations(root: Path) -> MotlistRelationCatalog:
    root = Path(root)
    if not root.exists():
        return MotlistRelationCatalog(root, 0, 0, 0, 0, 0, ())
    if not root.is_dir():
        raise NotADirectoryError(f"Motlist JSON root is not a directory: {root}")

    documents = 0
    documents_with_mappings = 0
    source_mappings = 0
    unnamed_mappings = 0
    unscoped_mappings = 0
    relations_by_identity: dict[
        tuple[str, int, str],
        MotlistRequestSetRelation,
    ] = {}

    paths = sorted(
        (
            path
            for path in root.rglob("*.json")
            if MOTLIST_JSON_RE.search(path.name)
        ),
        key=lambda path: path.as_posix().casefold(),
    )
    for path in paths:
        document = _load_json(path)
        if not isinstance(document, dict):
            raise ValueError(f"Motlist JSON root must be an object: {path}")
        format_name = document.get("_format")
        if format_name != MOTLIST_JSON_FORMAT:
            raise ValueError(
                f"Unsupported motlist JSON format {format_name!r}: {path}"
            )

        source_path = str(document.get("sourcePath") or "").replace("\\", "/")
        if not source_path:
            raise ValueError(f"Motlist JSON has no sourcePath: {path}")
        mappings = document.get("requestSetMappings")
        if not isinstance(mappings, list):
            raise ValueError(f"Motlist JSON has invalid requestSetMappings: {path}")

        documents += 1
        if mappings:
            documents_with_mappings += 1
        source_json = path.relative_to(root).as_posix()
        for index, mapping in enumerate(mappings):
            if not isinstance(mapping, dict):
                raise ValueError(
                    f"Invalid requestSetMappings[{index}] in {path}"
                )
            source_mappings += 1
            request_set_id = _nonnegative_int(
                mapping.get("requestSetId"),
                f"requestSetMappings[{index}].requestSetId",
                path,
            )
            motion_id = _nonnegative_int(
                mapping.get("motionId"),
                f"requestSetMappings[{index}].motionId",
                path,
            )
            motion_name = str(mapping.get("motionName") or "").strip()
            if not motion_name:
                unnamed_mappings += 1
                continue
            scope = infer_weapon_scope(source_path, motion_name)
            if not scope:
                unscoped_mappings += 1
                continue

            relation = MotlistRequestSetRelation(
                scope=scope,
                request_set_id=request_set_id,
                motion_name=motion_name,
                motion_id=motion_id,
                source_path=source_path,
                source_json=source_json,
            )
            identity = (scope, request_set_id, motion_name)
            current = relations_by_identity.get(identity)
            if current is None or relation.sort_key < current.sort_key:
                relations_by_identity[identity] = relation

    return MotlistRelationCatalog(
        root=root,
        documents=documents,
        documents_with_mappings=documents_with_mappings,
        source_mappings=source_mappings,
        unnamed_mappings=unnamed_mappings,
        unscoped_mappings=unscoped_mappings,
        relations=tuple(
            sorted(relations_by_identity.values(), key=lambda item: item.sort_key)
        ),
    )


def infer_weapon_scope(source_path: str, motion_name: str) -> str:
    normalized_path = source_path.replace("\\", "/").strip("/")
    for part in normalized_path.split("/"):
        match = WEAPON_SCOPE_RE.fullmatch(part)
        if match and int(match.group(1)) < 14:
            return f"Wp{int(match.group(1)):02d}"

    if normalized_path.casefold().startswith(PLAYER_MOTION_PREFIX):
        match = WEAPON_MOTION_RE.match(motion_name)
        if match and int(match.group(1)) < 14:
            return f"Wp{int(match.group(1)):02d}"
    return ""


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as exception:
        raise ValueError(f"Failed to read motlist JSON {path}: {exception}") from exception


def _nonnegative_int(value: Any, field: str, path: Path) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative integer: {path}")
    try:
        number = int(value)
    except (TypeError, ValueError) as exception:
        raise ValueError(
            f"{field} must be a non-negative integer: {path}"
        ) from exception
    if number < 0:
        raise ValueError(f"{field} must be a non-negative integer: {path}")
    return number
