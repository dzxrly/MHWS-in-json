"""Register a small, reusable set of complete cell styles per workbook."""

from copy import copy
from openpyxl.styles import NamedStyle
from openpyxl.styles.fonts import DEFAULT_FONT


class StylePalette:
    def __init__(self, workbook, prefix: str):
        self.workbook = workbook
        self.prefix = prefix
        self.styles = {}
        self.default_font = copy(DEFAULT_FONT)

    def get(self, key, **components) -> str:
        if key not in self.styles:
            components.setdefault("font", self.default_font)
            style = NamedStyle(name=f"{self.prefix}_{len(self.styles)}", **components)
            self.workbook.add_named_style(style)
            # Assign by registered name: passing NamedStyle objects makes openpyxl
            # compare complete styles against its list for every cell assignment.
            self.styles[key] = style.name
        return self.styles[key]
