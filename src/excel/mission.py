"""Layout for the localized MissionData workbook."""

from math import ceil
from pathlib import Path
from unicodedata import east_asian_width

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from src.converters.mission import MISSION_COLUMNS, TARGET_COLUMNS, MissionWorkbookData
from src.excel.writer import write_workbook


HEADER_FILL = PatternFill("solid", fgColor="23466D")
GROUP_FILLS = (
    PatternFill("solid", fgColor="FFFFFF"),
    PatternFill("solid", fgColor="EAF1F7"),
)
GROUP_BORDER = Border(bottom=Side(style="thin", color="A8BACB"))
WRAPPED_COLUMNS = {"_TitleMsg", "MonsterName", "_DetailMsg", "_SubBossInfoArray"}
CENTERED_COLUMNS = {
    "_Version", "_QuestType", "_QuestAttribute", "_QuestLv", "_TargetType",
    "_LegendaryID", "_MaxPlayerNum", "_OrderHR", "_OrderMR", "_TimeLimit",
    "_RemMoney", "_HRPoint", "_AddPoint", "_EnableGuestNpc", "_Stage",
    "_BattleBGM", "_ClearBGM",
}
COLUMN_WIDTHS = {
    "_MissionId": 20,
    "_Version": 19,
    "_QuestType": 15,
    "_QuestAttribute": 19,
    "_QuestLv": 10,
    "_TitleMsg": 37,
    "_TargetType": 23,
    "_LegendaryID": 15,
    "MonsterName": 23,
    "_DetailMsg": 75,
    "_SubBossInfoArray": 28,
}


def write_mission_workbook(path: Path, data: MissionWorkbookData) -> Path:
    return write_workbook(
        path,
        {"MissionData": data.rows},
        80.0,
        lambda workbook: style_mission_workbook(workbook, data),
    )


def style_mission_workbook(workbook, data: MissionWorkbookData) -> None:
    sheet = workbook["MissionData"]
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 85
    sheet.freeze_panes = "B2"
    sheet.auto_filter.ref = None  # Excel cannot sort merged mission groups reliably.
    sheet.row_dimensions[1].height = 29

    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for index, column in enumerate(MISSION_COLUMNS, start=1):
        letter = get_column_letter(index)
        sheet.column_dimensions[letter].width = COLUMN_WIDTHS.get(column, 14)

    for group_index, (first_row, last_row) in enumerate(data.groups):
        row_count = last_row - first_row + 1
        first = data.rows[first_row - 2]
        needed_lines = max(
            _wrapped_line_count(first[column], COLUMN_WIDTHS[column] - 5)
            for column in ("_TitleMsg", "_DetailMsg", "_SubBossInfoArray")
        )
        height = min(120, max(24, ceil(needed_lines * 15 / row_count)))
        for row_index in range(first_row, last_row + 1):
            sheet.row_dimensions[row_index].height = height
            for column_index, column in enumerate(MISSION_COLUMNS, start=1):
                cell = sheet.cell(row_index, column_index)
                cell.fill = GROUP_FILLS[group_index % len(GROUP_FILLS)]
                cell.border = GROUP_BORDER if row_index == last_row else Border()
                cell.alignment = Alignment(
                    horizontal="center" if column in CENTERED_COLUMNS else "left",
                    vertical="center",
                    wrap_text=column in WRAPPED_COLUMNS,
                )
        if row_count > 1:
            for column_index, column in enumerate(MISSION_COLUMNS, start=1):
                if column not in TARGET_COLUMNS:
                    sheet.merge_cells(
                        start_row=first_row,
                        start_column=column_index,
                        end_row=last_row,
                        end_column=column_index,
                    )


def _wrapped_line_count(value: str, width: int) -> int:
    return sum(
        max(1, ceil(sum(2 if east_asian_width(char) in "WF" else 1 for char in line) / width))
        for line in value.split("\n")
    )
