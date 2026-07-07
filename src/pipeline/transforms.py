from collections.abc import Callable
import re

from config import SUPPORT_FILES, WEAPON_TYPES

Table = list[dict]
FrameLoader = Callable[[str], Table | None]
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


def transform_workbook(name: str, sheets: dict[str, Table], load: FrameLoader) -> dict[str, Table]:
    if name == "ItemDataCollection.xlsx":
        return _items(sheets)
    if name == "SkillCollection.xlsx":
        return _skills(sheets)
    if name == "EquipCollection.xlsx":
        return _equip(sheets, load)
    if name == "EquipRecipeCollection.xlsx":
        return _recipes(sheets, load)
    return sheets


def _items(sheets: dict[str, Table]) -> dict[str, Table]:
    item_map = _map(sheets["ItemData"], "ItemId", "RawName")
    recipe = sheets.get("ItemRecipeData")
    if recipe is not None:
        for col in ("ResultItem", "Item"):
            _map_column(recipe, col, item_map)
    return sheets


def _skills(sheets: dict[str, Table]) -> dict[str, Table]:
    skill_map = _map(sheets["SkillCommonData"], "skillId", "skillName")
    skill_map.pop("NONE", None)
    _map_column(sheets.get("SkillData"), "openSkill", skill_map)
    _map_column(sheets.get("AccessoryData"), "Skill", skill_map)
    return sheets


def _equip(sheets: dict[str, Table], load: FrameLoader) -> dict[str, Table]:
    skill_map = _support_map(load, "skill_common", "skillId", "skillName")
    skill_map.pop("NONE", None)
    series_map = _support_map(load, "armor_series", "Series", "Name")

    armor = sheets.get("Armor")
    if armor is not None:
        _map_column(armor, "Series", series_map)
        _merge_skill_columns(armor, skill_map)

    for sheet_name, frame in sheets.items():
        if sheet_name.startswith("Wp_"):
            _weapon(frame, sheet_name[3:], skill_map)
    return sheets


def _recipes(sheets: dict[str, Table], load: FrameLoader) -> dict[str, Table]:
    item_map = _support_map(load, "item", "ItemId", "RawName")
    enemy_map = _support_map(load, "enemy", "enemyId", "EnemyName")
    series_map = _support_map(load, "armor_series", "Series", "Name")
    armor_name_map = _armor_name_map(load)
    weapon_name_maps = {name: _weapon_name_map(load, name) for name in WEAPON_TYPES}

    armor = sheets.get("Armor")
    if armor is not None:
        if _has_columns(armor, "SeriesId", "PartsType"):
            _insert_after(
                armor,
                "PartsType",
                "Name",
                [armor_name_map.get((row.get("SeriesId"), row.get("PartsType")), "") for row in armor],
            )
        _map_column(armor, "SeriesId", series_map)
        _recipe_common(armor, item_map, enemy_map)

    for sheet_name, frame in sheets.items():
        if not sheet_name.startswith("Wp_"):
            continue
        weapon_type = sheet_name[3:]
        id_col = WEAPON_ID_COLUMNS[weapon_type]
        if _has_columns(frame, id_col):
            _rename(frame, id_col, "Name")
            _map_column(frame, "Name", weapon_name_maps[weapon_type])
        _drop(frame, list(WEAPON_ID_COLUMNS.values()))
        _recipe_common(frame, item_map, enemy_map)
    return sheets


def _weapon(frame: Table, weapon_type: str, skill_map: dict) -> None:
    weapon_id = WEAPON_TYPES.index(weapon_type)
    id_col = WEAPON_ID_COLUMNS[weapon_type]
    if _has_columns(frame, id_col):
        _rename(frame, id_col, "Id")
    _drop(frame, list(WEAPON_ID_COLUMNS.values()))
    _drop(frame, [c for c in _columns(frame) if _other_weapon_column(c, weapon_id)])
    if weapon_type != "Rod":
        _drop(frame, ["RodInsectLv"])
    if weapon_type not in {"HeavyBowgun", "LightBowgun"}:
        _drop(frame, list(SHELL_COLUMNS))
    if weapon_type != "HeavyBowgun":
        _drop(frame, list(HEAVY_ONLY))
    if weapon_type != "LightBowgun":
        _drop(frame, list(LIGHT_ONLY))
    if weapon_type != "Bow":
        _drop(frame, ["isLoadingBin"])
    if weapon_type in {"HeavyBowgun", "LightBowgun", "Bow"}:
        _drop(frame, ["SharpnessValList", "TakumiValList"])
    _merge_skill_columns(frame, skill_map)
    _move_to_end(frame, ["ModelId", "CustomModelId"])


def _other_weapon_column(column: str, weapon_id: int) -> bool:
    match = WP_COLUMN_RE.search(str(column))
    return bool(match and int(match.group(1)) != weapon_id)


def _recipe_common(frame: Table, item_map: dict, enemy_map: dict) -> None:
    _map_column(frame, "KeyItemId", item_map)
    _map_column(frame, "KeyEnemyId", enemy_map)
    _map_column(frame, "Item", item_map)
    if _has_columns(frame, "Item", "ItemNum"):
        _insert_after(frame, "ItemNum", "ItemAndNum", _merge_item_nums(frame))
        _drop(frame, ["Item", "ItemNum"])
    _rename(frame, "KeyItemId", "KeyItem")
    _rename(frame, "KeyEnemyId", "KeyEnemy")


def _merge_skill_columns(frame: Table, skill_map: dict) -> None:
    if not _has_columns(frame, "Skill", "SkillLevel"):
        return
    merged = []
    for row_data in frame:
        row = []
        for skill, level in zip(_as_list(row_data.get("Skill")), _as_list(row_data.get("SkillLevel"))):
            skill = skill_map.get(skill, skill)
            if skill == "NONE" or level in {0, "0", None, "NONE"}:
                continue
            row.append(f"{skill}: {level}")
        merged.append(row)
    _insert_after(frame, "SkillLevel", "SkillAndLevel", merged)
    _drop(frame, ["Skill", "SkillLevel"])
    _move_after(frame, "SkillAndLevel", "SlotLevel")


def _merge_item_nums(frame: Table) -> list[list[str]]:
    rows = []
    for row in frame:
        rows.append([f"{item} x{num}" for item, num in zip(_as_list(row.get("Item")), _as_list(row.get("ItemNum"))) if num])
    return rows


def _armor_name_map(load: FrameLoader) -> dict[tuple[str, str], str]:
    armor = load(SUPPORT_FILES["armor"])
    if armor is None or not _has_columns(armor, "Series", "PartsType", "Name"):
        return {}
    return {(row.get("Series"), row.get("PartsType")): row.get("Name") for row in armor}


def _weapon_name_map(load: FrameLoader, weapon_type: str) -> dict:
    frame = load(f"STM/GameDesign/Common/Weapon/{weapon_type}.user.3.json")
    id_col = WEAPON_ID_COLUMNS[weapon_type]
    if frame is None or not _has_columns(frame, id_col, "Name"):
        return {}
    return _map(frame, id_col, "Name")


def _support_map(load: FrameLoader, key: str, id_col: str, name_col: str) -> dict:
    frame = load(SUPPORT_FILES[key])
    if frame is None:
        return {}
    return _map(frame, id_col, name_col)


def _map(frame: Table, key: str, value: str) -> dict:
    return {row.get(key): row.get(value) for row in frame if row.get(key) is not None and value in row}


def _map_column(frame: Table | None, column: str, mapping: dict) -> None:
    if frame is None or not mapping:
        return
    for row in frame:
        if column in row:
            row[column] = _mapped(row[column], mapping)


def _mapped(value, mapping: dict):
    if isinstance(value, list):
        return [mapping.get(v, v) for v in value if v]
    return mapping.get(value, value)


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    return [] if value is None or value == "" else [value]


def _move_after(frame: Table, column: str, after: str) -> None:
    for row in frame:
        if column not in row or after not in row:
            continue
        value = row.pop(column)
        _insert_key_after(row, after, column, value)


def _move_to_end(frame: Table, columns: list[str]) -> None:
    for row in frame:
        for column in columns:
            if column in row:
                row[column] = row.pop(column)


def _columns(frame: Table) -> list[str]:
    columns = []
    for row in frame:
        for column in row:
            if column not in columns:
                columns.append(column)
    return columns


def _has_columns(frame: Table, *columns: str) -> bool:
    available = set(_columns(frame))
    return set(columns).issubset(available)


def _drop(frame: Table, columns: list[str]) -> None:
    for row in frame:
        for column in columns:
            row.pop(column, None)


def _rename(frame: Table, old: str, new: str) -> None:
    for row in frame:
        if old not in row:
            continue
        rebuilt = {}
        for key, value in row.items():
            rebuilt[new if key == old else key] = value
        row.clear()
        row.update(rebuilt)


def _insert_after(frame: Table, after: str, column: str, values: list) -> None:
    for row, value in zip(frame, values):
        row.pop(column, None)
        if after in row:
            _insert_key_after(row, after, column, value)
        else:
            row[column] = value


def _insert_key_after(row: dict, after: str, key: str, value) -> None:
    rebuilt = {}
    for old_key, old_value in row.items():
        rebuilt[old_key] = old_value
        if old_key == after:
            rebuilt[key] = value
    row.clear()
    row.update(rebuilt)
