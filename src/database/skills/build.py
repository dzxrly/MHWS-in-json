from src.shared.tables import Table, index_by, map_column


def prepare(sheets: dict[str, Table]) -> dict[str, Table]:
    skill_map = index_by(sheets["SkillCommonData"], "skillId", "skillName")
    skill_map.pop("NONE", None)
    map_column(sheets.get("SkillData"), "openSkill", skill_map)
    map_column(sheets.get("AccessoryData"), "Skill", skill_map)
    return sheets


def prepare_workbook(repository):
    from src.database.skills.specs import WORKBOOK_NAME, SHEETS
    from src.database.table import prepare_table

    return prepare_table(WORKBOOK_NAME, SHEETS, repository, lambda sheets, load: prepare(sheets))
