"""Equipment projection shared by DATABASE and processed bowguns."""

import re
from config import SUPPORT_FILES, WEAPON_TYPES
from src.shared.text.values import TextParts
from src.shared.tables import (Table, FrameLoader, index_by, map_column, as_list, move_after, move_to_end, columns, has_columns, drop, rename, insert_after)

WEAPON_ID_COLUMNS = {name: ("GunLance" if name == "Gunlance" else name) for name in WEAPON_TYPES}
SHELL_COLUMNS = {
    "MainShell",
    "ShellLv",
    "ShellNum",
    "CustomizePattern",
    "DispSilencer",
    "DispBarrel",
}
HEAVY_ONLY = {"EnergyEfficiency", "AmmoStrength", "EnergyShellTypeNormal", "EnergyShellTypePower", "EnergyShellTypeWeak"}
LIGHT_ONLY = {"RapidShellNum", "IsRappid"}
WP_COLUMN_RE = re.compile(r"wp(\d{2})", re.IGNORECASE)


def prepare_equipment(sheets: dict[str, Table], load: FrameLoader) -> dict[str, Table]:
    skill_map = support_map(load, "skill_common", "skillId", "skillName")
    skill_map.pop("NONE", None)
    series_map = support_map(load, "armor_series", "Series", "Name")

    armor = sheets.get("Armor")
    if armor is not None:
        map_column(armor, "Series", series_map)
        _merge_skill_columns(armor, skill_map)

    for sheet_name, frame in sheets.items():
        if sheet_name.startswith("Wp_"):
            _weapon(frame, sheet_name[3:], skill_map)
    return sheets

def _weapon(frame: Table, weapon_type: str, skill_map: dict) -> None:
    weapon_id = WEAPON_TYPES.index(weapon_type)
    id_col = WEAPON_ID_COLUMNS[weapon_type]
    if has_columns(frame, id_col):
        rename(frame, id_col, "Id")
    drop(frame, list(WEAPON_ID_COLUMNS.values()))
    drop(frame, [c for c in columns(frame) if _other_weapon_column(c, weapon_id)])
    if weapon_type != "Rod":
        drop(frame, ["RodInsectLv"])
    if weapon_type not in {"HeavyBowgun", "LightBowgun"}:
        drop(frame, list(SHELL_COLUMNS))
    if weapon_type != "HeavyBowgun":
        drop(frame, list(HEAVY_ONLY))
    if weapon_type != "LightBowgun":
        drop(frame, list(LIGHT_ONLY))
    if weapon_type != "Bow":
        drop(frame, ["isLoadingBin"])
    if weapon_type in {"HeavyBowgun", "LightBowgun", "Bow"}:
        drop(frame, ["SharpnessValList", "TakumiValList"])
    _merge_skill_columns(frame, skill_map)
    move_to_end(frame, ["ModelId", "CustomModelId"])

def _other_weapon_column(column: str, weapon_id: int) -> bool:
    match = WP_COLUMN_RE.search(str(column))
    return bool(match and int(match.group(1)) != weapon_id)

def _merge_skill_columns(frame: Table, skill_map: dict) -> None:
    if not has_columns(frame, "Skill", "SkillLevel"):
        return
    merged = []
    for row_data in frame:
        row = []
        for skill, level in zip(as_list(row_data.get("Skill")), as_list(row_data.get("SkillLevel"))):
            skill = skill_map.get(skill, skill)
            if skill == "NONE" or level in {0, "0", None, "NONE"}:
                continue
            row.append(TextParts((skill, ": ", level)))
        merged.append(row)
    insert_after(frame, "SkillLevel", "SkillAndLevel", merged)
    drop(frame, ["Skill", "SkillLevel"])
    move_after(frame, "SkillAndLevel", "SlotLevel")

def support_map(load: FrameLoader, key: str, id_col: str, name_col: str) -> dict:
    frame = load(SUPPORT_FILES[key])
    if frame is None:
        return {}
    return index_by(frame, id_col, name_col)
