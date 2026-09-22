"""Prepare DATABASE inputs once, then render each language independently."""

from dataclasses import dataclass
from pathlib import Path

from config import ACTION_VALUE_WORKBOOK, AMULET_WORKBOOK, FULL_TEXT_WORKBOOK, MAX_COLUMN_WIDTH, MISSION_WORKBOOK
from src.database.action_values.build import ActionValueCatalog, build_action_value_workbook, load_action_value_catalog
from src.database.action_values.excel import write_action_value_workbook
from src.database.amulets.build import build_amulet_workbook_sheets
from src.database.amulets.excel import style_amulet_workbook
from src.database.equipment import build as equipment
from src.database.equipment_recipes import build as equipment_recipes
from src.database.full_text.exporter import export_full_text
from src.database.items import build as items
from src.database.missions.build import MissionCatalog, build_mission_workbook_data, load_mission_catalog
from src.database.missions.excel import write_mission_workbook
from src.database.skills import build as skills
from src.database.table import TableWorkbook
from src.shared.amulets import AmuletCatalog
from src.shared.excel.writer import write_workbook
from src.shared.log import info
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextDB, TextSource
from src.shared.timing import Timings

WORKBOOK_NAMES = (
    FULL_TEXT_WORKBOOK, "ItemDataCollection.xlsx", "SkillCollection.xlsx", "EquipCollection.xlsx",
    "EquipRecipeCollection.xlsx", AMULET_WORKBOOK, MISSION_WORKBOOK, ACTION_VALUE_WORKBOOK,
)


@dataclass(frozen=True, slots=True)
class DatabaseCatalog:
    tables: tuple[TableWorkbook, ...]
    amulets: AmuletCatalog
    missions: MissionCatalog
    actions: ActionValueCatalog


def prepare_database(repository: SourceRepository, amulets: AmuletCatalog,
                     enums_path: Path, action_map_path: Path) -> DatabaseCatalog:
    tables = tuple(feature.prepare_workbook(repository) for feature in (items, skills, equipment, equipment_recipes))
    missions = load_mission_catalog(repository.root, enums_path, repository)
    actions = load_action_value_catalog(repository.root, action_map_path)
    audit = actions.action_map_audit
    info(f"Static ActionMap: {audit.bound_request_sets} mapped requestSets, {audit.bindings} exact bindings")
    return DatabaseCatalog(tables, amulets, missions, actions)


def export_language(output_dir: Path, catalog: DatabaseCatalog, text_source: TextSource,
                    text_db: TextDB, language_id: int, timings: Timings) -> list[Path]:
    outputs = []

    def export(name, write):
        with timings.measure(f"{output_dir.name}/{name}"):
            outputs.append(write())

    export(FULL_TEXT_WORKBOOK, lambda: export_full_text(output_dir, text_db))
    for table in catalog.tables:
        export(table.name, lambda table=table: table.write(output_dir, text_db))
    export(AMULET_WORKBOOK, lambda: write_workbook(
        output_dir / AMULET_WORKBOOK,
        build_amulet_workbook_sheets(catalog.amulets, lambda guid: text_db.get(guid) or ""),
        MAX_COLUMN_WIDTH, style_amulet_workbook,
    ))
    export(MISSION_WORKBOOK, lambda: write_mission_workbook(
        output_dir / MISSION_WORKBOOK,
        build_mission_workbook_data(catalog.missions, text_source, language_id),
    ))
    export(ACTION_VALUE_WORKBOOK, lambda: write_action_value_workbook(
        output_dir / ACTION_VALUE_WORKBOOK,
        build_action_value_workbook(catalog.actions, lambda guid: text_db.get(guid) or ""),
    ))
    return outputs
