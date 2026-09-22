from dataclasses import dataclass
from typing import Callable
from src.shared.log import info

Table = list[dict]
Loader = Callable[[str], Table | None]

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

def _require_columns(name: str, rows: Table, required: set[str]) -> None:
    if not rows:
        raise ValueError(f"Required amulet table is empty: {name}")
    available = {column for row in rows for column in row}
    missing = sorted(required - available)
    if missing:
        raise ValueError(
            f"Missing required column(s) in amulet table {name}: {', '.join(missing)}"
        )
