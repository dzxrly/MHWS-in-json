from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .models import ActionGuide, ActionSeed

_ACTION_ENUM = re.compile(r"^\[(-?\d+)\]\s*(.*)$")
_INT_MAX = 2_147_483_647


class ActionDataCatalog:
    def __init__(
        self,
        natives_directory: Path,
        actions: list[ActionSeed],
        guides: list[ActionGuide] | None = None,
    ) -> None:
        self.natives_directory = natives_directory
        self.actions = actions
        self.guides = guides if guides is not None else []

    @classmethod
    def load(cls, mhws_json_root: Path) -> "ActionDataCatalog":
        natives = resolve_natives_directory(mhws_json_root)
        action_data = natives / "STM" / "GameDesign" / "Player" / "ActionData"
        guide_data = (
            natives / "STM" / "GameDesign" / "Common" / "Player" / "ActionGuide"
        )
        if not action_data.is_dir():
            raise FileNotFoundError(f"ActionData 目录不存在: {action_data}")

        actions: list[ActionSeed] = []
        action_guides: list[ActionGuide] = []
        for weapon_index in range(14):
            scope = f"Wp{weapon_index:02d}"
            guides = _load_guides(
                guide_data / f"ActionGuideData_{scope}Name.user.3.json"
            )
            localized_names = _load_japanese_names(
                natives
                / "STM"
                / "GameDesign"
                / "Text"
                / "Excel_Action"
                / f"ActionGuideDataNameText_{scope}.msg.23.json"
            )
            action_guides.extend(
                ActionGuide(
                    scope,
                    guide_id,
                    order,
                    name,
                    guid,
                    localized_names.get(guid.casefold(), ""),
                )
                for guide_id, (order, name, guid) in sorted(guides.items())
            )
            source_map: dict[tuple[str, int], set[str]] = {}
            action_directory = action_data / scope / "Action"
            if action_directory.is_dir():
                paths = sorted(
                    action_directory.glob("*ActionParam.user.3.json"),
                    key=lambda path: str(path).casefold(),
                )
                for path in paths:
                    document = json.loads(path.read_text(encoding="utf-8"))
                    found: list[tuple[str, int]] = []
                    _find_action_classes(document, scope, found)
                    relative = path.relative_to(natives).as_posix()
                    for item in found:
                        source_map.setdefault(item, set()).add(relative)

            for (class_name, guide_id), sources in sorted(
                source_map.items(), key=lambda item: (item[0][0], item[0][1])
            ):
                guide = guides.get(guide_id)
                name_guid = guide[2] if guide else ""
                actions.append(
                    ActionSeed(
                        scope=scope,
                        class_name=class_name,
                        guide_id=guide_id,
                        guide_order=guide[0] if guide else _INT_MAX,
                        internal_name=(
                            guide[1] if guide else class_name.rsplit(".", 1)[-1]
                        ),
                        name_guid=name_guid,
                        japanese_name=localized_names.get(name_guid.casefold(), ""),
                        source_files=tuple(
                            sorted(sources, key=lambda value: value.casefold())
                        ),
                        guided=guide is not None,
                    )
                )

        actions.sort(
            key=lambda action: (
                action.scope,
                action.guide_order,
                action.guide_id,
                action.class_name,
            )
        )
        return cls(natives, actions, action_guides)


def resolve_natives_directory(root: Path) -> Path:
    absolute = root.expanduser().resolve()
    if (absolute / "STM").is_dir():
        return absolute
    nested = absolute / "natives"
    if (nested / "STM").is_dir():
        return nested
    raise FileNotFoundError(f"预期在 {absolute} 或 {nested} 下找到 STM 目录")


def _load_guides(path: Path) -> dict[int, tuple[int, str, str]]:
    if not path.is_file():
        return {}
    output: dict[int, tuple[int, str, str]] = {}
    _find_guide_rows(json.loads(path.read_text(encoding="utf-8")), output)
    return output


def _load_japanese_names(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    root = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(root, dict) or not isinstance(root.get("entries"), list):
        return {}
    japanese_index = 0
    languages = root.get("languages")
    if isinstance(languages, list):
        try:
            japanese_index = languages.index(0)
        except ValueError:
            return {}
    names: dict[str, str] = {}
    for entry in root["entries"]:
        if not isinstance(entry, dict):
            continue
        guid = entry.get("guid")
        content = entry.get("content")
        if (
            isinstance(guid, str)
            and guid.strip()
            and isinstance(content, list)
            and len(content) > japanese_index
            and isinstance(content[japanese_index], str)
        ):
            names[guid.casefold()] = content[japanese_index]
    return names


def _find_guide_rows(
    element: Any,
    output: dict[int, tuple[int, str, str]],
) -> None:
    if isinstance(element, dict):
        action = element.get("_Action")
        if isinstance(action, str):
            match = _ACTION_ENUM.match(action)
            if match:
                guide_id = int(match.group(1))
                order = element.get("_Index", _INT_MAX)
                if isinstance(order, bool) or not isinstance(order, int):
                    order = _INT_MAX
                name_guid = element.get("_ActionName", "")
                output[guide_id] = (
                    order,
                    match.group(2).strip(),
                    name_guid if isinstance(name_guid, str) else "",
                )
        for value in element.values():
            _find_guide_rows(value, output)
    elif isinstance(element, list):
        for value in element:
            _find_guide_rows(value, output)


def _find_action_classes(
    element: Any,
    scope: str,
    output: list[tuple[str, int]],
) -> None:
    if isinstance(element, dict):
        for name, value in element.items():
            if isinstance(value, dict) and _is_weapon_action_class(name, scope):
                guide_id = value.get("_ActionGuideID")
                if isinstance(guide_id, int) and not isinstance(guide_id, bool):
                    output.append((name, guide_id))
            _find_action_classes(value, scope, output)
    elif isinstance(element, list):
        for value in element:
            _find_action_classes(value, scope, output)


def _is_weapon_action_class(value: str, scope: str) -> bool:
    return value.startswith(f"app.{scope}Action.") or value.startswith(
        f"app.{scope}SubAction."
    )
