from __future__ import annotations

from src.shared.excel.cells import safe_cell as _safe_cell, text_width as _text_width
from pathlib import Path
import math

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from src.shared.excel.palette import StylePalette

from src.database.action_values.build import (
    ActionValueWorkbookData, LEADING_COLUMNS, RowGroup,
)


HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
MAPPED_FILLS = (
    PatternFill("solid", fgColor="EAF2F8"),
    PatternFill("solid", fgColor="EDF7ED"),
)
MAPPED_ACTION_FILLS = (
    PatternFill("solid", fgColor="D6E4F0"),
    PatternFill("solid", fgColor="DDEEDC"),
)
UNMAPPED_FILL = PatternFill("solid", fgColor="FCE4D6")
UNMAPPED_ACTION_FILL = PatternFill("solid", fgColor="F4B183")

HEADER_BORDER = Border(bottom=Side(style="medium", color="17365D"))
VERTICAL_SIDE = Side(style="thin", color="D9E2F3")
GROUP_SIDE = Side(style="medium", color="7F8C8D")

CENTER_COLUMNS = {
    "MappingKind",
    "ResourceRole",
    "MappingConfidence",
    "sourceRequestSetOrdinal",
    "requestSetID",
    "groupIndex",
    "status",
    "requestSetIndex",
    "keyHash",
    "KeyNameMMHash",
    "userDataType",
}

FIXED_WIDTHS = {
    "MappingName": 34.0,
    "MappingKind": 12.0,
    "MappingIdentity": 42.0,
    "MappingInternalName": 28.0,
    "MappingNameSource": 24.0,
    "ResourceRole": 16.0,
    "MappingConfidence": 16.0,
    "MappingCondition": 38.0,
    "MappingSource": 36.0,
    "sourceRequestSetOrdinal": 14.0,
    "requestSetID": 14.0,
    "groupIndex": 12.0,
    "status": 10.0,
    "requestSetIndex": 14.0,
    "keyHash": 14.0,
    "KeyNameMMHash": 16.0,
    "name": 14.0,
    "keyName": 18.0,
    "userDataType": 22.0,
}

WRAPPED_COLUMNS = {
    "MappingName", "MappingIdentity", "MappingInternalName", "MappingCondition",
    "MappingSource", "name", "keyName",
}


def write_action_value_workbook(
    path: Path,
    data: ActionValueWorkbookData,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    for sheet_index, (sheet_name, rows) in enumerate(data.sheets.items()):
        sheet = workbook.active if sheet_index == 0 else workbook.create_sheet()
        sheet.title = sheet_name
        columns = data.columns[sheet_name]
        sheet.append([_source_line(data.sources[sheet_name])])
        sheet.append(list(columns))
        for row in rows:
            sheet.append([_safe_cell(row.get(column)) for column in columns])

    style_action_value_workbook(workbook, data)
    workbook.save(path)
    return path


def style_action_value_workbook(
    workbook: Workbook,
    data: ActionValueWorkbookData,
) -> None:
    styles = _body_styles(StylePalette(workbook, "action"))
    for sheet in workbook.worksheets:
        _style_sheet(
            sheet,
            data.columns[sheet.title],
            data.groups[sheet.title],
            styles,
        )


def _style_sheet(
    sheet,
    columns: tuple[str, ...],
    groups: tuple[RowGroup, ...],
    styles: dict,
) -> None:
    sheet.freeze_panes = f"{get_column_letter(len(LEADING_COLUMNS) + 1)}3"
    name_column = columns.index("MappingName") + 1
    metadata_start = columns.index("MappingKind") + 1
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 85
    sheet.sheet_properties.tabColor = "ED7D31" if sheet.title == "Ammo" else "5B9BD5"
    sheet.row_dimensions[1].height = 30
    sheet.row_dimensions[2].height = 48

    if len(columns) > 1:
        sheet.merge_cells(
            start_row=1,
            start_column=1,
            end_row=1,
            end_column=len(columns),
        )
    source_cell = sheet.cell(1, 1)
    source_cell.fill = PatternFill("solid", fgColor="D9EAF7")
    source_cell.font = Font(italic=True, color="1F4E78")
    source_cell.alignment = Alignment(
        horizontal="left",
        vertical="center",
        wrap_text=True,
    )
    source_cell.border = Border(bottom=Side(style="thin", color="9EADBA"))

    for cell in sheet[2]:
        cell.fill = HEADER_FILL
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )
        cell.border = HEADER_BORDER

    wrapped_columns = [
        (columns.index(name) + 1, FIXED_WIDTHS[name] - 2.0)
        for name in ("MappingInternalName", "MappingCondition")
    ]
    for row_index in range(3, sheet.max_row + 1):
        wrapped_lines = max(
            sum(
                max(1, math.ceil(_text_width(line) / width))
                for line in str(sheet.cell(row_index, column).value or "").splitlines()
            )
            for column, width in wrapped_columns
        )
        sheet.row_dimensions[row_index].height = min(
            409.0, max(21.0, 15.0 * wrapped_lines + 6.0)
        )
    column_styles = [
        (index == name_column, header in CENTER_COLUMNS,
         header in WRAPPED_COLUMNS or index == metadata_start - 1)
        for index, header in enumerate(columns, start=1)
    ]
    mapped_index = 0
    for group in groups:
        if group.unmapped:
            color_index = 2
        else:
            color_index = mapped_index % len(MAPPED_FILLS)
            mapped_index += 1
        _style_group(sheet, group, styles, color_index, column_styles)

        if not group.unmapped and group.end_row > group.start_row:
            sheet.merge_cells(
                start_row=group.start_row,
                start_column=name_column,
                end_row=group.end_row,
                end_column=name_column,
            )
        action_cell = sheet.cell(group.start_row, name_column)
        action_cell.font = Font(bold=True, color="9C5700" if group.unmapped else "1F1F1F")
        action_cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

    _set_column_widths(sheet, columns)


def _style_group(
    sheet, group: RowGroup, styles: dict, color_index: int, column_styles: list,
) -> None:
    for row_index in range(group.start_row, group.end_row + 1):
        top, bottom = row_index == group.start_row, row_index == group.end_row
        for column_index, column_style in enumerate(column_styles, start=1):
            sheet.cell(row_index, column_index).style = styles[(color_index, top, bottom, *column_style)]


def _body_styles(palette: StylePalette) -> dict:
    styles = {}
    for color_index, (row_fill, action_fill) in enumerate(zip(
        (*MAPPED_FILLS, UNMAPPED_FILL), (*MAPPED_ACTION_FILLS, UNMAPPED_ACTION_FILL),
    )):
        for top in (False, True):
            for bottom in (False, True):
                border = Border(left=VERTICAL_SIDE, right=VERTICAL_SIDE,
                                top=GROUP_SIDE if top else Side(), bottom=GROUP_SIDE if bottom else Side())
                for highlighted, centered, wrapped in (
                    (False, False, False), (False, False, True),
                    (False, True, False), (False, True, True), (True, False, True),
                ):
                    key = (color_index, top, bottom, highlighted, centered, wrapped)
                    styles[key] = palette.get(
                        key, fill=action_fill if highlighted else row_fill, border=border,
                        alignment=Alignment(horizontal="center" if centered else "left",
                                            vertical="center", wrap_text=wrapped),
                    )
    return styles


def _set_column_widths(sheet, columns: tuple[str, ...]) -> None:
    last_sample_row = min(sheet.max_row, 251)
    for column_index, header in enumerate(columns, start=1):
        letter = get_column_letter(column_index)
        if header in FIXED_WIDTHS:
            sheet.column_dimensions[letter].width = FIXED_WIDTHS[header]
            continue

        width = max(10.0, _text_width(header) + 2.0)
        for row_index in range(3, last_sample_row + 1):
            width = max(width, _text_width(sheet.cell(row_index, column_index).value) + 2.0)
        sheet.column_dimensions[letter].width = min(width, 24.0)


def _source_line(sources: tuple[str, ...]) -> str:
    if not sources:
        return "RCOL sources: [none]"
    return f"RCOL sources ({len(sources)}): " + " | ".join(sources)
