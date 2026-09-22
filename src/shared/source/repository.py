"""One normalized source read per path, with owned copies for each consumer."""

from copy import deepcopy
from pathlib import Path

from src.shared.source.user3 import GUID_RE, load_user3_table
from src.shared.text.values import TextRef


# Common-table message fields. Other GUIDs remain structural identifiers.
MESSAGE_FIELDS = frozenset({
    "Name", "Explain", "RawName", "RawExplain", "skillName", "skillExplain",
    "JpEnemyName", "EnemyName", "EnemyExp", "EnemyExtraName", "EnemyBossExp",
    "EnemyFrenzyName", "EnemyLegendaryName", "EnemyLegendaryKingName",
    "EnemyFeatures", "EnemyTips", "FirstCapture", "Memo", "Grammar",
})


class SourceRepository:
    def __init__(self, natives_dir: Path):
        self.root = Path(natives_dir)
        self._tables: dict[str, list[dict]] = {}

    @property
    def loaded_paths(self) -> tuple[str, ...]:
        return tuple(self._tables)

    def table(self, relative_path: str) -> list[dict]:
        if relative_path not in self._tables:
            self._tables[relative_path] = load_user3_table(self.root / relative_path)
        return deepcopy(self._tables[relative_path])

    def referenced_table(self, relative_path: str) -> list[dict]:
        rows = self.table(relative_path)
        for row in rows:
            for field in MESSAGE_FIELDS & row.keys():
                value = row[field]
                if isinstance(value, str) and GUID_RE.fullmatch(value):
                    row[field] = TextRef(value)
        return rows
