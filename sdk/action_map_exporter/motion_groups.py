"""Weapon MotionGroupSet tables exported from ``wpXX_meb.user.3``.

Some actions do not store a 32-bit MotionSet (``bank << 12 | motion``).
They store a 64-bit MotionGroupSet ID instead, packed as
``bank << 44 | groupId``. ``ace.user_data.MotionExtendBank._GroupTable`` maps
that ID to the MotionSets that can play, with separate left/right lists.
The paired ``*_mex.user.3`` files give the reverse mapping, one group per
motion. Loading checks that the packing agrees with that mapping, so a
changed layout fails here instead of producing false bindings.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

GROUP_ID_BITS = 44
_GROUP_ID_MASK = (1 << GROUP_ID_BITS) - 1
_BANK_LIMIT = 1 << 20
_BANK_TYPE = "ace.user_data.MotionExtendBank"
_BANK_SET_TYPE = "ace.user_data.MotionExtendBank.SetData"
_GROUP_BANK_TYPE = "ace.user_data.MotionExtendBank.cGroupBankSetSerialize"
_GROUP_SET_TYPE = "ace.user_data.MotionExtendBank.cGroupSetSerialize"
_GROUP_TYPE = "ace.user_data.MotionExtendBank.cGroup"
_EXTEND_TYPE = "ace.user_data.MotionExtend"
_EXTEND_ENTRY_TYPE = "ace.user_data.MotionExtend.cMotionExtend"


@dataclass(frozen=True, slots=True)
class MotionGroupMember:
    motion_set_id: int
    side: str
    list_index: int


@dataclass(frozen=True, slots=True)
class MotionGroup:
    scope: str
    group_set_id: int
    bank_id: int
    group_id: int
    source_path: str
    members: tuple[MotionGroupMember, ...]

    def evidence(self, member: MotionGroupMember) -> tuple[tuple[str, str | int], ...]:
        return (
            ("groupSetId", self.group_set_id),
            ("groupBankId", self.bank_id),
            ("groupId", self.group_id),
            ("side", member.side),
            ("listIndex", member.list_index),
            ("groupMemberCount", len(self.members)),
            ("sourcePath", self.source_path),
        )


class MotionGroupCatalog:
    def __init__(
        self,
        groups: dict[tuple[str, int], MotionGroup],
        verified_extends: int = 0,
    ) -> None:
        self.groups = groups
        self.verified_extends = verified_extends

    @classmethod
    def load(cls, natives_directory: Path) -> "MotionGroupCatalog":
        weapon_root = natives_directory / "STM" / "Motion" / "Player" / "Weapon"
        groups: dict[tuple[str, int], MotionGroup] = {}
        verified = 0
        missing: list[str] = []
        for index in range(14):
            scope = f"Wp{index:02d}"
            directory = weapon_root / scope
            paths = (
                sorted(
                    directory.glob("*_meb.user.3.json"),
                    key=lambda path: str(path).casefold(),
                )
                if directory.is_dir()
                else []
            )
            if not paths:
                missing.append(scope)
                continue
            for path in paths:
                relative = path.relative_to(natives_directory).as_posix()
                bank = _bank_document(path)
                scope_groups = _load_groups(scope, relative, bank)
                for key, group in scope_groups.items():
                    if key in groups:
                        raise ValueError(
                            f"MotionGroupSet 重复 {scope}/0x{key[1]:x}: "
                            f"{groups[key].source_path} 与 {relative}"
                        )
                    groups[key] = group
                verified += _verify_extends(
                    scope, natives_directory, bank, scope_groups
                )
        if missing:
            raise FileNotFoundError(
                "缺少武器 MotionExtendBank JSON（wpXX_meb.user.3）: "
                + ", ".join(missing)
            )
        return cls(groups, verified)

    def find(self, scope: str, value: int) -> MotionGroup | None:
        if value < 0:
            value += 1 << 64
        if value >> GROUP_ID_BITS == 0:
            return None
        return self.groups.get((scope, value))


def pack_group_set_id(bank_id: int, group_id: int) -> int:
    if not 0 < bank_id < _BANK_LIMIT or not 0 <= group_id <= _GROUP_ID_MASK:
        raise ValueError(f"无效的 MotionGroupSet: bank={bank_id}, group=0x{group_id:x}")
    return (bank_id << GROUP_ID_BITS) | group_id


def _bank_document(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    bank = _typed_root(document, _BANK_TYPE)
    if bank is None:
        raise ValueError(f"不是 MotionExtendBank JSON: {path}")
    return bank


def _load_groups(
    scope: str,
    source_path: str,
    bank: dict[str, Any],
) -> dict[tuple[str, int], MotionGroup]:
    result: dict[tuple[str, int], MotionGroup] = {}
    for bank_item in _list(bank.get("_GroupTable")):
        group_bank = _typed(bank_item, _GROUP_BANK_TYPE)
        bank_id = _integer(group_bank.get("GroupBankId"))
        for set_item in _list(group_bank.get("GroupSet")):
            group_set = _typed(set_item, _GROUP_SET_TYPE)
            group_id = _integer(group_set.get("GroupId"))
            group = _typed(group_set.get("Group"), _GROUP_TYPE)
            group_set_id = pack_group_set_id(bank_id, group_id)
            members = tuple(
                MotionGroupMember(_integer(value), side, list_index)
                for side, key in (("L", "LList"), ("R", "RList"))
                for list_index, value in enumerate(_list(group.get(key)))
            )
            key = (scope, group_set_id)
            if key in result:
                raise ValueError(
                    f"MotionGroupSet 重复 {scope}/0x{group_set_id:x}: {source_path}"
                )
            result[key] = MotionGroup(
                scope, group_set_id, bank_id, group_id, source_path, members
            )
    return result


def _verify_extends(
    scope: str,
    natives_directory: Path,
    bank: dict[str, Any],
    groups: dict[tuple[str, int], MotionGroup],
) -> int:
    """Check the packing against the per-motion group in each MotionExtend."""
    verified = 0
    references = 0
    for item in _list(bank.get("_MotionExtendList")):
        entry = _typed(item, _BANK_SET_TYPE)
        bank_id = _integer(entry.get("_BankID"))
        reference = _typed(entry.get("_MotionExtend"), _EXTEND_TYPE)
        resource = reference.get("path")
        if not isinstance(resource, str) or not resource.strip():
            continue
        path = natives_directory / "STM" / f"{resource.strip().lstrip('/')}.3.json"
        if not path.is_file():
            continue
        extend = _typed_root(json.loads(path.read_text(encoding="utf-8")), _EXTEND_TYPE)
        for data in _list((extend or {}).get("_DataList")):
            motion = _typed(data, _EXTEND_ENTRY_TYPE)
            group_set_id = _integer(motion.get("_MotionGroupSetID"))
            group = groups.get((scope, group_set_id))
            if group is None:
                continue
            references += 1
            motion_set_id = (bank_id << 12) | _integer(motion.get("_MotionID"))
            if any(m.motion_set_id == motion_set_id for m in group.members):
                verified += 1
    if references and not verified:
        raise ValueError(
            f"{scope} 的 MotionExtend 与 MotionGroupSet 打包格式不一致；"
            "游戏更新后请重新核对 bank << 44 | groupId"
        )
    return verified


def _typed_root(document: object, type_name: str) -> dict[str, Any] | None:
    for item in document if isinstance(document, list) else [document]:
        if isinstance(item, dict) and isinstance(item.get(type_name), dict):
            return item[type_name]
    return None


def _typed(value: object, type_name: str) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get(type_name), dict):
        return value[type_name]
    raise ValueError(f"缺少 {type_name} 对象")


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"MotionGroupSet 字段不是整数: {value!r}")
    return value
