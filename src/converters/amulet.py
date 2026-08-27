import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from src.utils.log import file_size, info

Table = list[dict]
Loader = Callable[[str], Table | None]
NameResolver = Callable[[str | None], list[dict] | str]
LocalizedNameResolver = Callable[[str | None], str]

PATHS = {
    "skill_lot": "STM/GameDesign/Common/Equip/RandomAmuletLotSkillTable.user.3.json",
    "pt": "STM/GameDesign/Common/Equip/RandomAmuletPtTable.user.3.json",
    "slot": "STM/GameDesign/Common/Equip/RandomAmuletAccSlot.user.3.json",
    "skill": "STM/GameDesign/Common/Equip/SkillCommonData.user.3.json",
    "amulet": "STM/GameDesign/Common/Equip/AmuletData.user.3.json",
}

REQUIRED_COLUMNS = {
    "skill_lot": {"SkillType", "SkillLv", "SkillPt"},
    "pt": {"Index", "AmuletType", "SkillPt_01", "SkillPt_02", "SkillPt_03", "SlotPt"},
    "slot": {
        "SlotPt",
        "SlotType01",
        "SlotLevel01",
        "SlotType02",
        "SlotLevel02",
        "SlotType03",
        "SlotLevel03",
    },
    "skill": {"skillId", "skillName"},
    "amulet": {"AmuletType", "Name", "Rare"},
}


@dataclass(frozen=True, slots=True)
class AmuletTypeInfo:
    id: str
    name_guid: str | None
    rare: object


@dataclass(frozen=True, slots=True)
class AmuletCatalog:
    skill_lot: tuple[dict, ...]
    pt_table: tuple[dict, ...]
    skill_name_guids: dict[object, str | None]
    amulet_types: dict[str, AmuletTypeInfo]
    slots: dict[object, dict]
    missing_amulet_types: tuple[str, ...]
    missing_amulet_rows: int


def load_amulet_catalog(load: Loader) -> AmuletCatalog:
    info("    Loading amulet source tables")
    tables = {key: load(path) or [] for key, path in PATHS.items()}
    info(
        "    Loaded amulet tables: "
        f"skill_lot={len(tables['skill_lot'])}, pt={len(tables['pt'])}, "
        f"slot={len(tables['slot'])}, skill={len(tables['skill'])}, "
        f"amulet={len(tables['amulet'])}"
    )
    for name, required in REQUIRED_COLUMNS.items():
        _require_columns(name, tables[name], required)

    skill_name_guids = {
        row.get("skillId"): row.get("skillName")
        for row in tables["skill"]
    }
    amulet_types = {
        row["AmuletType"]: AmuletTypeInfo(
            id=row["AmuletType"],
            name_guid=row.get("Name"),
            rare=row.get("Rare"),
        )
        for row in tables["amulet"]
        if row.get("AmuletType")
    }
    slots = {row.get("SlotPt"): _slot(row) for row in tables["slot"]}

    missing_rows = [
        row
        for row in tables["pt"]
        if row.get("AmuletType") not in amulet_types
    ]
    missing_types = tuple(
        sorted({str(row.get("AmuletType")) for row in missing_rows})
    )
    if missing_rows:
        info(
            "    Skipping amulet combinations without AmuletData definitions: "
            f"{len(missing_rows)} row(s), type(s)={', '.join(missing_types)}"
        )

    valid_rows = [
        row
        for row in tables["pt"]
        if row.get("AmuletType") in amulet_types
    ]
    missing_slot_points = sorted(
        {
            row.get("SlotPt")
            for row in valid_rows
            if row.get("SlotPt") not in slots
        },
        key=str,
    )
    if missing_slot_points:
        joined = ", ".join(str(value) for value in missing_slot_points)
        raise ValueError(f"Missing amulet slot definition(s): {joined}")

    return AmuletCatalog(
        skill_lot=tuple(tables["skill_lot"]),
        pt_table=tuple(tables["pt"]),
        skill_name_guids=skill_name_guids,
        amulet_types=amulet_types,
        slots=slots,
        missing_amulet_types=missing_types,
        missing_amulet_rows=len(missing_rows),
    )


def export_amulet_pools(
    output_dir: Path,
    source: AmuletCatalog | Loader,
    name_for_guid: NameResolver | None = None,
) -> None:
    catalog = source if isinstance(source, AmuletCatalog) else load_amulet_catalog(source)
    skill_pool, amulet_pool = build_amulet_pools(catalog, name_for_guid)
    _write_json(output_dir / "skill_pool.json", skill_pool)
    _write_json(output_dir / "amulet_pool.json", amulet_pool)


def build_amulet_pools(
    catalog: AmuletCatalog,
    name_for_guid: NameResolver | None = None,
) -> tuple[list[dict], list[dict]]:
    skill_map = {
        skill_id: _name(guid, name_for_guid)
        for skill_id, guid in catalog.skill_name_guids.items()
    }
    amulet_map = {
        amulet_type: {
            "id": info.id,
            "name": _name(info.name_guid, name_for_guid),
            "rare": _rare(info.rare),
        }
        for amulet_type, info in catalog.amulet_types.items()
    }
    return (
        _skill_pool(catalog.skill_lot, skill_map),
        _amulet_pool(catalog.pt_table, amulet_map, catalog.slots),
    )


def build_amulet_workbook_sheets(
    catalog: AmuletCatalog,
    name_for_guid: LocalizedNameResolver,
) -> dict[str, list[dict]]:
    valid_rows = [
        row
        for row in catalog.pt_table
        if row.get("AmuletType") in catalog.amulet_types
    ]

    amulet_rows = []
    for row in valid_rows:
        amulet_type = row.get("AmuletType")
        info = catalog.amulet_types[amulet_type]
        slot = catalog.slots[row.get("SlotPt")]
        amulet_rows.append(
            {
                "Index": row.get("Index"),
                "AmuletType": info.id,
                "AmuletName": _localized_name(info.name_guid, name_for_guid),
                "Rarity": _rare_level(info.rare),
                "SkillPt1": row.get("SkillPt_01", 0),
                "SkillPt2": row.get("SkillPt_02", 0),
                "SkillPt3": row.get("SkillPt_03", 0),
                "SlotPt": row.get("SlotPt"),
                "WeaponSlots": _slot_text(slot.get("weaponSlot")),
                "ArmorSlots": _slot_text(slot.get("equipmentSlot")),
            }
        )

    skill_pools: dict[object, list[str]] = {}
    for row in catalog.skill_lot:
        skill_id = row.get("SkillType")
        skill_name = _localized_name(
            catalog.skill_name_guids.get(skill_id),
            name_for_guid,
        )
        skill_pools.setdefault(row.get("SkillPt"), []).append(
            f"{skill_name} Lv.{row.get('SkillLv')}"
        )
    skill_rows = _skill_pool_sheet_rows(skill_pools)

    slot_points = sorted(
        slot_point
        for slot_point in catalog.slots
        if slot_point not in {None, 0, "0"}
    )
    slot_rows = []
    for slot_point in slot_points:
        slot = catalog.slots[slot_point]
        slot_rows.append(
            {
                "SlotPt": slot_point,
                "WeaponSlots": _slot_text(slot.get("weaponSlot")),
                "ArmorSlots": _slot_text(slot.get("equipmentSlot")),
            }
        )

    return {
        "AmuletPool": amulet_rows,
        "SkillPool": skill_rows,
        "SlotPool": slot_rows,
    }


def _skill_pool_sheet_rows(
    pools: dict[object, list[str]],
) -> list[dict[object, object]]:
    pool_points = sorted(pools, key=int)
    row_count = max((len(pools[point]) for point in pool_points), default=0)
    rows = []
    for row_index in range(row_count):
        row: dict[object, object] = {
            "SkillPt": "Skill / Level" if row_index == 0 else None,
        }
        for point in pool_points:
            values = pools[point]
            row[point] = values[row_index] if row_index < len(values) else None
        rows.append(row)
    return rows


def _skill_pool(rows, skill_map: dict) -> list[dict]:
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


def _amulet_pool(pt_table, amulet_map: dict, slot_map: dict) -> list[dict]:
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


def _slot_text(levels) -> str:
    return ", ".join(f"Lv.{level}" for level in (levels or []) if level)


def _level(value) -> int:
    if isinstance(value, str) and value.startswith("Lv"):
        return int(value[2:])
    return 0


def _rare_level(value) -> int:
    if isinstance(value, str) and value.startswith("RARE"):
        return int(value[4:]) + 1
    raise ValueError(f"Invalid amulet rarity: {value!r}")


def _rare(value) -> str:
    if isinstance(value, str) and value.startswith("RARE"):
        return f"Rare {int(value[4:])}"
    return str(value)


def _name(guid: str | None, resolver: NameResolver | None):
    if resolver is None:
        return guid or ""
    return resolver(guid)


def _localized_name(
    guid: str | None,
    resolver: LocalizedNameResolver,
) -> str:
    if not guid:
        return ""
    return resolver(guid) or ""


def _require_columns(name: str, rows: Table, required: set[str]) -> None:
    if not rows:
        raise ValueError(f"Required amulet table is empty: {name}")
    available = {column for row in rows for column in row}
    missing = sorted(required - available)
    if missing:
        raise ValueError(
            f"Missing required column(s) in amulet table {name}: {', '.join(missing)}"
        )


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    info(f"    Saved JSON: {path} ({file_size(path)})")
