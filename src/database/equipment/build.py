from src.database.equipment.specs import SHEETS, WORKBOOK_NAME
from src.database.table import prepare_table
from src.shared.equipment import prepare_equipment
from src.shared.source.repository import SourceRepository


def prepare_workbook(repository: SourceRepository):
    return prepare_table(WORKBOOK_NAME, SHEETS, repository, prepare_equipment)
