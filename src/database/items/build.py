from src.shared.tables import Table, index_by, map_column


def prepare(sheets: dict[str, Table]) -> dict[str, Table]:
    item_map = index_by(sheets["ItemData"], "ItemId", "RawName")
    recipe = sheets.get("ItemRecipeData")
    if recipe is not None:
        for col in ("ResultItem", "Item"):
            map_column(recipe, col, item_map)
    return sheets


def prepare_workbook(repository):
    from src.database.items.specs import WORKBOOK_NAME, SHEETS
    from src.database.table import prepare_table

    return prepare_table(WORKBOOK_NAME, SHEETS, repository, lambda sheets, load: prepare(sheets))
