from config import SUPPORT_FILES, WEAPON_TYPES
from src.shared.equipment import WEAPON_ID_COLUMNS, support_map
from src.shared.text.values import TextParts
from src.shared.tables import Table, FrameLoader, index_by, map_column, as_list, has_columns, drop, rename, insert_after


def prepare(sheets: dict[str, Table], load: FrameLoader) -> dict[str, Table]:
    item_map = support_map(load, "item", "ItemId", "RawName")
    enemy_map = support_map(load, "enemy", "enemyId", "EnemyName")
    series_map = support_map(load, "armor_series", "Series", "Name")
    armor_name_map = _armor_name_map(load)
    weapon_name_maps = {name: _weapon_name_map(load, name) for name in WEAPON_TYPES}

    armor = sheets.get("Armor")
    if armor is not None:
        if has_columns(armor, "SeriesId", "PartsType"):
            insert_after(
                armor,
                "PartsType",
                "Name",
                [armor_name_map.get((row.get("SeriesId"), row.get("PartsType")), "") for row in armor],
            )
        map_column(armor, "SeriesId", series_map)
        _recipe_common(armor, item_map, enemy_map)

    for sheet_name, frame in sheets.items():
        if not sheet_name.startswith("Wp_"):
            continue
        weapon_type = sheet_name[3:]
        id_col = WEAPON_ID_COLUMNS[weapon_type]
        if has_columns(frame, id_col):
            rename(frame, id_col, "Name")
            map_column(frame, "Name", weapon_name_maps[weapon_type])
        drop(frame, list(WEAPON_ID_COLUMNS.values()))
        _recipe_common(frame, item_map, enemy_map)
    return sheets


def _recipe_common(frame: Table, item_map: dict, enemy_map: dict) -> None:
    map_column(frame, "KeyItemId", item_map)
    map_column(frame, "KeyEnemyId", enemy_map)
    map_column(frame, "Item", item_map)
    if has_columns(frame, "Item", "ItemNum"):
        insert_after(frame, "ItemNum", "ItemAndNum", _merge_item_nums(frame))
        drop(frame, ["Item", "ItemNum"])
    rename(frame, "KeyItemId", "KeyItem")
    rename(frame, "KeyEnemyId", "KeyEnemy")


def _merge_item_nums(frame: Table) -> list[list[str]]:
    rows = []
    for row in frame:
        rows.append([TextParts((item, " x", num)) for item, num in zip(as_list(row.get("Item")), as_list(row.get("ItemNum"))) if num])
    return rows


def _armor_name_map(load: FrameLoader) -> dict[tuple[str, str], str]:
    armor = load(SUPPORT_FILES["armor"])
    if armor is None or not has_columns(armor, "Series", "PartsType", "Name"):
        return {}
    return {(row.get("Series"), row.get("PartsType")): row.get("Name") for row in armor}


def _weapon_name_map(load: FrameLoader, weapon_type: str) -> dict:
    frame = load(f"STM/GameDesign/Common/Weapon/{weapon_type}.user.3.json")
    id_col = WEAPON_ID_COLUMNS[weapon_type]
    if frame is None or not has_columns(frame, id_col, "Name"):
        return {}
    return index_by(frame, id_col, "Name")


def prepare_workbook(repository):
    from src.database.equipment_recipes.specs import WORKBOOK_NAME, SHEETS
    from src.database.table import prepare_table

    return prepare_table(WORKBOOK_NAME, SHEETS, repository, prepare)
