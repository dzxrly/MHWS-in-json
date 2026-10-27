from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .models import AmmoNameRecord, ShellCollisionReference, ShellEntryRecord
from .collision_references import additional_collision_references
from .utils import murmur3_utf16

_ENUM_PATTERN = re.compile(r"^\[(-?\d+)\]\s*(.*)$")
_LEVEL_PATTERN = re.compile(r"(?:^|_)LV(\d+)(?:_|$)", re.IGNORECASE)
_PLAYER_MINI_PARAM_PREFIX = "app.cShellminiParamPl"
_TARGET_SCOPE = re.compile(r"/(Wp(?:0[0-9]|1[0-3]))/", re.IGNORECASE)
_INT_MAX = 2_147_483_647


class AmmoNameCatalog:
    def __init__(self, names: list[AmmoNameRecord]) -> None:
        self.names = names

    def match(self, key_hash: int, fixed_name: str) -> AmmoNameRecord | None:
        level_match = _LEVEL_PATTERN.search(fixed_name)
        level = level_match.group(1) if level_match else None
        matches = [
            name for name in self.names if key_hash in _candidate_hashes(name, level)
        ]
        return matches[0] if len(matches) == 1 else None


class ShellCatalog:
    def __init__(
        self,
        entries: list[ShellEntryRecord],
        ammo_names: AmmoNameCatalog,
        core_ammo_types: dict[int, str],
    ) -> None:
        self.entries = entries
        self.ammo_names = ammo_names
        self.core_ammo_types = core_ammo_types
        self.core_ammo_type_names = {
            name.casefold(): name for name in core_ammo_types.values()
        }

    @classmethod
    def load(cls, mhws_json_root: Path, natives_directory: Path) -> "ShellCatalog":
        enum_maps = _load_enum_maps(
            _resolve_enums_path(mhws_json_root, natives_directory)
        )
        action_data = natives_directory / "STM" / "GameDesign" / "Player" / "ActionData"
        entries: list[ShellEntryRecord] = []
        for weapon_index in range(14):
            source_scope = f"Wp{weapon_index:02d}"
            path = (
                action_data
                / source_scope
                / "Shell"
                / f"{source_scope}ShellList.user.3.json"
            )
            if not path.is_file():
                continue
            rows: list[dict[str, Any]] = []
            _find_shell_rows(json.loads(path.read_text(encoding="utf-8")), rows)
            for entry_index, row in enumerate(rows):
                package = _find_object_with_property(row, "_AttackCollisionID")
                if package is None:
                    continue
                prefab_path = _find_string(package, "v1", ".pfb")
                target_scope = _get_target_scope(prefab_path) or source_scope
                main_param_path = _find_string(package, "path", ".user")
                collision_ids: set[int] = set()
                collision_references: list[ShellCollisionReference] = []
                collision_id = _get_int(package, "_AttackCollisionID", -1)
                if collision_id >= 0:
                    collision_ids.add(collision_id)
                    collision_references.append(
                        ShellCollisionReference(
                            collision_id,
                            "primary",
                            "_AttackCollisionID",
                            path.relative_to(natives_directory).as_posix(),
                        )
                    )
                ammo_type_name = ""
                mini_param_fields: tuple[tuple[str, str, object], ...] = ()
                if main_param_path.strip():
                    main_path = (
                        natives_directory
                        / "STM"
                        / Path(main_param_path.replace("/", "\\") + ".3.json")
                    )
                    if main_path.is_file():
                        main_document = json.loads(
                            main_path.read_text(encoding="utf-8")
                        )
                        additional = additional_collision_references(
                            main_document, main_param_path
                        )
                        collision_references.extend(additional)
                        collision_ids.update(ref.collision_id for ref in additional)
                        ammo_type_name = _find_enum_name(main_document, "_ShellType")
                        mini_param_fields = _player_mini_param_fields(main_document)

                fixed_id = _get_int(row, "_FixedID", -1)
                fixed_name = _resolve_fixed_name(
                    enum_maps, source_scope, target_scope, fixed_id
                )
                shell_name_hash = _get_int(package, "_ShellNameHash", -1)
                if shell_name_hash >= 0 and (
                    not fixed_name.strip()
                    or murmur3_utf16(fixed_name) != shell_name_hash
                ):
                    hashed_name = _resolve_name_hash(
                        enum_maps, source_scope, target_scope, shell_name_hash
                    )
                    if hashed_name.strip():
                        fixed_name = hashed_name
                level = _LEVEL_PATTERN.search(fixed_name)
                entries.append(
                    ShellEntryRecord(
                        source_scope=source_scope,
                        shell_list_path=path.relative_to(natives_directory).as_posix(),
                        entry_index=entry_index,
                        target_scope=target_scope,
                        fixed_id=fixed_id,
                        fixed_name=fixed_name,
                        shell_name_hash=shell_name_hash,
                        ammo_type_name=ammo_type_name,
                        prefab_path=prefab_path.replace("\\", "/"),
                        main_param_path=main_param_path.replace("\\", "/"),
                        collision_ids=tuple(sorted(collision_ids)),
                        collision_references=tuple(collision_references),
                        ammo_level=int(level.group(1)) if level else None,
                        mini_param_fields=mini_param_fields,
                    )
                )
        entries.sort(key=lambda entry: (entry.source_scope, entry.entry_index))
        return cls(
            entries,
            _load_ammo_names(natives_directory, enum_maps),
            _load_core_ammo_types(enum_maps),
        )

    def get_core_ammo_type_name(self, fixed_name: str) -> str | None:
        folded = fixed_name.casefold()
        matches = [
            original
            for key, original in self.core_ammo_type_names.items()
            if folded == key or folded.startswith(key + "_")
        ]
        return max(matches, key=len) if matches else None


def _candidate_hashes(name: AmmoNameRecord, level: str | None) -> set[int]:
    candidates = {name.japanese_name}
    if level is not None:
        candidates.update(
            {
                f"{name.japanese_name}Lv{level}",
                f"{name.japanese_name}LV{level}",
                f"{name.japanese_name}Lv.{level}",
                f"{name.japanese_name} Lv{level}",
            }
        )
    return {murmur3_utf16(value) for value in candidates}


def _load_enum_maps(path: Path) -> dict[str, dict[int, str]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    maps: dict[str, dict[int, str]] = {}
    for type_name, values in document.items():
        if not isinstance(values, dict) or not (
            type_name.endswith("Shell.FixedID")
            or type_name == "app.WeaponGunDef.SHELL_TYPE"
            or type_name == "app.ItemDef.ID"
        ):
            continue
        maps[type_name] = {
            value: name
            for name, value in values.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
    return maps


def _load_core_ammo_types(maps: dict[str, dict[int, str]]) -> dict[int, str]:
    values = maps.get("app.WeaponGunDef.SHELL_TYPE", {})
    maximum = next((key for key, value in values.items() if value == "MAX"), 0)
    return {key: value for key, value in values.items() if 0 <= key < maximum}


def _enum_types(source_scope: str, target_scope: str) -> tuple[str, ...]:
    base = (
        f"app.{source_scope}Shell.FixedID",
        f"ace.{source_scope}Shell.FixedID",
    )
    return (*base, "app.WpGunShell.FixedID") if target_scope == "Ammo" else base


def _resolve_fixed_name(
    maps: dict[str, dict[int, str]],
    source_scope: str,
    target_scope: str,
    fixed_id: int,
) -> str:
    for type_name in _enum_types(source_scope, target_scope):
        name = maps.get(type_name, {}).get(fixed_id)
        if name is not None:
            return name
    return ""


def _resolve_name_hash(
    maps: dict[str, dict[int, str]],
    source_scope: str,
    target_scope: str,
    name_hash: int,
) -> str:
    seen: set[str] = set()
    for type_name in _enum_types(source_scope, target_scope):
        for name in maps.get(type_name, {}).values():
            if name in seen:
                continue
            seen.add(name)
            if murmur3_utf16(name) == name_hash:
                return name
    return ""


def _load_ammo_names(
    natives_directory: Path,
    enum_maps: dict[str, dict[int, str]],
) -> AmmoNameCatalog:
    messages = _load_japanese_message_names(
        natives_directory
        / "STM"
        / "GameDesign"
        / "Text"
        / "Excel_Data"
        / "Item.msg.23.json"
    )
    item_path = (
        natives_directory
        / "STM"
        / "GameDesign"
        / "Common"
        / "Item"
        / "itemData.user.3.json"
    )
    if not item_path.is_file():
        return AmmoNameCatalog([])
    item_values = {
        name: value for value, name in enum_maps.get("app.ItemDef.ID", {}).items()
    }
    rows: list[dict[str, Any]] = []
    _find_objects_with_property(
        json.loads(item_path.read_text(encoding="utf-8")), "_ItemId", rows
    )
    names: list[AmmoNameRecord] = []
    for row in rows:
        if _find_enum_name(row, "_Type") != "SHELL":
            continue
        item_id = _find_enum_name(row, "_ItemId")
        name_guid = row.get("_RawName", "")
        japanese_name = messages.get(str(name_guid).casefold(), "")
        if (
            not item_id.strip()
            or not isinstance(name_guid, str)
            or not name_guid.strip()
            or item_id not in item_values
            or not japanese_name.strip()
        ):
            continue
        names.append(
            AmmoNameRecord(
                item_id=item_id,
                item_value=item_values[item_id],
                order=_get_int(row, "_SortId", _INT_MAX),
                name_guid=name_guid,
                japanese_name=japanese_name,
                japanese_name_hash=murmur3_utf16(japanese_name),
            )
        )
    distinct: dict[str, AmmoNameRecord] = {}
    for name in names:
        distinct.setdefault(name.name_guid.casefold(), name)
    return AmmoNameCatalog(
        sorted(distinct.values(), key=lambda item: (item.order, item.item_id))
    )


def _load_japanese_message_names(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    root = json.loads(path.read_text(encoding="utf-8"))
    entries = root.get("entries") if isinstance(root, dict) else None
    if not isinstance(entries, list):
        return {}
    language_index = 0
    languages = root.get("languages")
    if isinstance(languages, list):
        try:
            language_index = languages.index(0)
        except ValueError:
            return {}
    names: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        guid = entry.get("guid")
        content = entry.get("content")
        if (
            isinstance(guid, str)
            and guid.strip()
            and isinstance(content, list)
            and len(content) > language_index
            and isinstance(content[language_index], str)
        ):
            names[guid.casefold()] = content[language_index]
    return names


def _find_shell_rows(element: Any, output: list[dict[str, Any]]) -> None:
    if isinstance(element, dict):
        if "_ShellPackage" in element and "_FixedID" in element:
            output.append(element)
        for value in element.values():
            _find_shell_rows(value, output)
    elif isinstance(element, list):
        for value in element:
            _find_shell_rows(value, output)


def _find_objects_with_property(
    element: Any,
    property_name: str,
    output: list[dict[str, Any]],
) -> None:
    if isinstance(element, dict):
        if property_name in element:
            output.append(element)
        for value in element.values():
            _find_objects_with_property(value, property_name, output)
    elif isinstance(element, list):
        for value in element:
            _find_objects_with_property(value, property_name, output)


def _find_object_with_property(
    element: Any,
    property_name: str,
) -> dict[str, Any] | None:
    if isinstance(element, dict):
        if property_name in element:
            return element
        for value in element.values():
            found = _find_object_with_property(value, property_name)
            if found is not None:
                return found
    elif isinstance(element, list):
        for value in element:
            found = _find_object_with_property(value, property_name)
            if found is not None:
                return found
    return None


def _find_string(element: Any, property_name: str, suffix: str) -> str:
    if isinstance(element, dict):
        value = element.get(property_name)
        if isinstance(value, str) and value.casefold().endswith(suffix.casefold()):
            return value
        for child in element.values():
            found = _find_string(child, property_name, suffix)
            if found:
                return found
    elif isinstance(element, list):
        for child in element:
            found = _find_string(child, property_name, suffix)
            if found:
                return found
    return ""


def _player_mini_param_fields(
    element: Any,
) -> tuple[tuple[str, str, object], ...]:
    output: list[tuple[str, str, object]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.startswith(_PLAYER_MINI_PARAM_PREFIX) and isinstance(
                    child, dict
                ):
                    output.extend(
                        (key, name, field)
                        for name, field in child.items()
                        if isinstance(field, (str, int, float, bool))
                    )
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(element)
    return tuple(output)


def enum_name(value: object) -> str:
    """'[24] DASH_CLIMB' -> 'DASH_CLIMB'; other values -> ''."""
    if not isinstance(value, str):
        return ""
    match = _ENUM_PATTERN.match(value)
    return match.group(2).strip() if match else value


def _find_enum_name(element: Any, property_name: str) -> str:
    if isinstance(element, dict):
        value = element.get(property_name)
        if isinstance(value, str):
            match = _ENUM_PATTERN.match(value)
            return match.group(2).strip() if match else value
        for child in element.values():
            found = _find_enum_name(child, property_name)
            if found:
                return found
    elif isinstance(element, list):
        for child in element:
            found = _find_enum_name(child, property_name)
            if found:
                return found
    return ""


def _get_target_scope(prefab_path: str) -> str | None:
    normalized = prefab_path.replace("\\", "/")
    if "/wpguncommon/" in normalized.casefold():
        return "Ammo"
    match = _TARGET_SCOPE.search(normalized)
    return f"Wp{int(match.group(1)[2:]):02d}" if match else None


def _resolve_enums_path(root: Path, natives_directory: Path) -> Path:
    candidates = [
        root.expanduser().resolve() / "Enums_Internal.json",
        natives_directory.parent / "Enums_Internal.json",
    ]
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise FileNotFoundError("在输出根目录下未找到 Enums_Internal.json")
    return path


def _get_int(element: dict[str, Any], name: str, fallback: int) -> int:
    value = element.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else fallback
