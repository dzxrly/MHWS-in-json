"""Explicit database rarity values; presentation never changes business data."""

from dataclasses import dataclass
import re

RARE_RE = re.compile(r"^RARE(\d+)$")


@dataclass(frozen=True, slots=True)
class Rarity:
    index: int

    @property
    def level(self) -> int:
        return self.index + 1

    def __str__(self) -> str:
        return f"RARE{self.index}"


def prepare_rarities(sheets: dict[str, list[dict]]) -> dict[str, list[dict]]:
    for rows in sheets.values():
        for row in rows:
            for key, value in row.items():
                if isinstance(value, str) and (match := RARE_RE.fullmatch(value)):
                    row[key] = Rarity(int(match.group(1)))
    return sheets
