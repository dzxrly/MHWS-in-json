from typing import Callable
from src.shared.amulets import AmuletCatalog

LocalizedNameResolver = Callable[[str | None], str]


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


def _slot_text(levels) -> str:
    return ", ".join(f"Lv.{level}" for level in (levels or []) if level)


def _rare_level(value) -> int:
    if isinstance(value, str) and value.startswith("RARE"):
        return int(value[4:]) + 1
    raise ValueError(f"Invalid amulet rarity: {value!r}")


def _localized_name(
    guid: str | None,
    resolver: LocalizedNameResolver,
) -> str:
    if not guid:
        return ""
    return resolver(guid) or ""
