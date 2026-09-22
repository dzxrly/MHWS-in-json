"""Stream the flat text database after measuring its two columns."""

from pathlib import Path
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font

from config import FULL_TEXT_MAX_COLUMN_WIDTH, FULL_TEXT_WORKBOOK
from src.shared.excel.cells import safe_cell, text_width
from src.shared.excel.palette import StylePalette
from src.shared.text.catalog import TextDB

REJECTED_TEXT_PREFIX = "[#Rejected#]"


def text_rows(text_db: TextDB) -> list[tuple[str, str]]:
    available, rejected, empty = [], [], []
    for guid, text in text_db.guid_text.items():
        if text_db.is_rejected(guid):
            text = f"{REJECTED_TEXT_PREFIX} {text}" if text.strip() else REJECTED_TEXT_PREFIX
            rejected.append((guid, text))
        elif not text.strip():
            empty.append((guid, text))
        else:
            available.append((guid, text))
    return available + rejected + empty


def export_full_text(output_dir: Path, text_db: TextDB) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [(safe_cell(guid), safe_cell(text)) for guid, text in text_rows(text_db)]
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("FullText")
    palette = StylePalette(workbook, "text")
    alignment = Alignment(horizontal="left", vertical="center")
    header = palette.get("header", font=Font(bold=True), alignment=alignment)
    body = palette.get("body", alignment=alignment)
    for index, letter in enumerate(("A", "B")):
        sheet.column_dimensions[letter].width = min(
            max(6.0, max((text_width(row[index]) for row in rows), default=0.0)), FULL_TEXT_MAX_COLUMN_WIDTH,
        )
    header_cells = [WriteOnlyCell(sheet, value=value) for value in ("guid", "text")]
    for cell in header_cells:
        cell.style = header
    sheet.append(header_cells)
    for values in rows:
        cells = [WriteOnlyCell(sheet, value=value) for value in values]
        for cell in cells:
            cell.style = body
        sheet.append(cells)
    path = output_dir / FULL_TEXT_WORKBOOK
    workbook.save(path)
    return path
