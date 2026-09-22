"""A prepared workbook owns language-neutral rows with explicit text references."""

from dataclasses import dataclass
from pathlib import Path

from config import MAX_COLUMN_WIDTH
from src.shared.excel.writer import write_workbook
from src.shared.rarity import prepare_rarities
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextDB
from src.shared.text.values import localize


@dataclass(frozen=True, slots=True)
class TableWorkbook:
    name: str
    sheets: dict[str, list[dict]]

    def write(self, output_dir: Path, text_db: TextDB) -> Path:
        return write_workbook(output_dir / self.name, localize(self.sheets, text_db.get), MAX_COLUMN_WIDTH)


def prepare_table(name: str, specs: list[tuple[str, str]], repository: SourceRepository, transform) -> TableWorkbook:
    sheets = {sheet: repository.referenced_table(path) for sheet, path in specs}
    return TableWorkbook(name, prepare_rarities(transform(sheets, repository.referenced_table)))
