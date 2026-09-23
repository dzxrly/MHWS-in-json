"""Exports owned by PROCESSED_DATA, independent of DATABASE renderers."""

from pathlib import Path
from src.processed_data.amulet_pools.exporter import export_amulet_pools
from src.processed_data.bowguns.exporter import export_bowgun_workbooks
from src.processed_data.enemy_actions.exporter import export_enemy_action_workbook
from src.processed_data.damage_calculator.exporter import OUTPUT_NAME as DAMAGE_OUTPUT_NAME, export_damage_calculator
from src.processed_data.skill_effects.exporter import OUTPUT_NAME as SKILL_EFFECTS_OUTPUT_NAME, export_skill_effects
from src.processed_data.graphics.exporter import export_graphic_preset
from src.shared.amulets import AmuletCatalog
from src.shared.languages import language_code
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextDB, TextSource
from src.shared.timing import Timings

OUTPUT_NAMES = (
    "skill_pool.json", "amulet_pool.json", "graphic_preset.xlsx", "Bowgun_Custom.xlsx",
    "HeavyBowgun.xlsx", "LightBowgun.xlsx", "EnemyActionNames.xlsx", DAMAGE_OUTPUT_NAME,
    SKILL_EFFECTS_OUTPUT_NAME,
)


class PoolNames:
    """Retain only pool name GUIDs, rather than every complete language database."""

    def __init__(self, catalog: AmuletCatalog):
        guids = {*catalog.skill_name_guids.values(), *(info.name_guid for info in catalog.amulet_types.values())}
        self.names = {guid: [] for guid in guids if guid}

    def add_language(self, language_id: int, text_db: TextDB) -> None:
        for guid, names in self.names.items():
            names.append({"languageCode": language_code(language_id),
                          "languageIndexInGame": str(language_id), "name": text_db.get(guid) or ""})

    def resolve(self, guid: str | None) -> list[dict]:
        return self.names.get(guid, [])


def export_processed(output_dir: Path, repository: SourceRepository, text_source: TextSource,
                     amulets: AmuletCatalog, names: PoolNames, timings: Timings) -> list[Path]:
    with timings.measure("processed/amulet_pools"):
        export_amulet_pools(output_dir, amulets, names.resolve)
    with timings.measure("processed/graphics"):
        export_graphic_preset(output_dir, repository.root)
    with timings.measure("processed/bowguns"):
        export_bowgun_workbooks(output_dir, repository.root, text_source, repository)
    with timings.measure("processed/enemy_actions"):
        export_enemy_action_workbook(output_dir, repository.root, text_source, repository)
    with timings.measure("processed/damage_calculator"):
        export_damage_calculator(output_dir / DAMAGE_OUTPUT_NAME, repository, text_source)
    with timings.measure("processed/skill_effects"):
        export_skill_effects(output_dir / SKILL_EFFECTS_OUTPUT_NAME, repository, text_source)
    return [output_dir / name for name in OUTPUT_NAMES]
