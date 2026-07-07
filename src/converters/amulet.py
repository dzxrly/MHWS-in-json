import json
from pathlib import Path
from typing import Callable

Table = list[dict]
Loader = Callable[[str], Table | None]
NameResolver = Callable[[str | None], list[dict] | str]

PATHS = {
    "skill_lot": "STM/GameDesign/Common/Equip/RandomAmuletLotSkillTable.user.3.json",
    "pt": "STM/GameDesign/Common/Equip/RandomAmuletPtTable.user.3.json",
    "slot": "STM/GameDesign/Common/Equip/RandomAmuletAccSlot.user.3.json",
    "skill": "STM/GameDesign/Common/Equip/SkillCommonData.user.3.json",
    "amulet": "STM/GameDesign/Common/Equip/AmuletData.user.3.json",
}


def export_amulet_pools(
    output_dir: Path,
    load: Loader,
    name_for_guid: NameResolver | None = None,
) -> None:
    skill_lot = load(PATHS["skill_lot"]) or []
    pt_table = load(PATHS["pt"]) or []
    slot_table = load(PATHS["slot"]) or []
    skill_data = load(PATHS["skill"]) or []
    amulet_data = load(PATHS["amulet"]) or []

    skill_map = {
        row.get("skillId"): _name(row.get("skillName"), name_for_guid)
        for row in skill_data
    }
    amulet_map = {
        row.get("AmuletType"): {
            "id": row.get("AmuletType"),
            "name": _name(row.get("Name"), name_for_guid),
            "rare": _rare(row.get("Rare")),
        }
        for row in amulet_data
        if row.get("AmuletType")
    }
    slot_map = {row.get("SlotPt"): _slot(row) for row in slot_table}

    _write_json(output_dir / "skill_pool.json", _skill_pool(skill_lot, skill_map))
    _write_json(output_dir / "amulet_pool.json", _amulet_pool(pt_table, amulet_map, slot_map))


def _skill_pool(rows: Table, skill_map: dict) -> list[dict]:
    pools: dict[int, list[dict]] = {}
    for row in rows:
        pt = row.get("SkillPt")
        pools.setdefault(pt, []).append(
            {
                "id": row.get("SkillType"),
                "name": skill_map.get(row.get("SkillType"), row.get("SkillType")),
                "level": row.get("SkillLv"),
            }
        )
    return [{"skillPt": pt, "skillList": pools[pt]} for pt in sorted(pools)]


def _amulet_pool(pt_table: Table, amulet_map: dict, slot_map: dict) -> list[dict]:
    data = []
    for row in pt_table:
        amulet_type = row.get("AmuletType")
        if amulet_type not in amulet_map:
            continue
        entry = {
            "id": str(row.get("Index")),
            "rare": amulet_map[amulet_type],
            "slot": slot_map.get(row.get("SlotPt"), {"slotPt": str(row.get("SlotPt"))}),
        }
        for idx in range(1, 4):
            entry[f"skillPt{idx}"] = str(row.get(f"SkillPt_{idx:02d}", 0))
        data.append(entry)
    return data


def _slot(row: dict) -> dict:
    weapon, equipment = [], []
    for idx in range(1, 4):
        slot_type = row.get(f"SlotType{idx:02d}")
        level = _level(row.get(f"SlotLevel{idx:02d}"))
        weapon.append(level if slot_type == "ACC_TYPE_00" else 0)
        equipment.append(level if slot_type == "ACC_TYPE_01" else 0)
    return {
        "slotPt": str(row.get("SlotPt")),
        "weaponSlot": sorted(weapon, reverse=True),
        "equipmentSlot": sorted(equipment, reverse=True),
    }


def _level(value) -> int:
    if isinstance(value, str) and value.startswith("Lv"):
        return int(value[2:])
    return 0


def _rare(value) -> str:
    if isinstance(value, str) and value.startswith("RARE"):
        return f"Rare {int(value[4:])}"
    return str(value)


def _name(guid: str | None, resolver: NameResolver | None):
    if resolver is None:
        return guid or ""
    return resolver(guid)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
