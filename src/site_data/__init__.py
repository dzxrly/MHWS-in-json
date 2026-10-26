"""JSON read by the website; the only interface between src and web/.

The web app imports nothing from src or sdk and runs no Python. It reads the
committed folder src/site_data/data:

  site.json                                  schema version and preview flag
  enemy_battle_logic/index.json              monster list of the overview page
  enemy_battle_logic/<enemyId>/tree.json     decision tree and names
  enemy_battle_logic/<enemyId>/tables.json   behaviour table nodes (raw data)
  enemy_battle_logic/<enemyId>/flow.json     technical flow chart
  skill_details/skills.json                  skill effect values and meanings

Regenerate it offline with ``python -m src.site_data`` after the models or the
skill links change, and commit it; a test fails while it is out of date. The
release's PROCESSED_DATA carries the same data as two complete single files,
enemy_battle_logic.json and skill_details.json (export_release_files).
"""

import json
from pathlib import Path
import shutil

from src.processed_data.enemy_battle_logic.definitions import (
    EXPECTED_ENEMY_IDS,
    MODEL_DIR,
)

from .enemy_battle_logic import (
    INDEX_NAME,
    export_battle_data,
    export_battle_release,
    page_names,
)
from .skill_details import OUTPUT_NAME as SKILLS_NAME, export_skill_data

DEFAULT_DIR = Path(__file__).with_name("data")
RELEASE_NAMES = ("enemy_battle_logic.json", "skill_details.json")
SITE_NAME = "site.json"


def output_names():
    """Release file set, for the full 34-monster data."""
    return (
        SITE_NAME,
        SKILLS_NAME,
        INDEX_NAME,
        *(name for enemy_id in EXPECTED_ENEMY_IDS for name in page_names(enemy_id)),
    )


def export_site_data(
    output_dir,
    repository,
    text_source,
    *,
    models_dir=MODEL_DIR,
    template_path=None,
    preview=False,
):
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        # Only replace a folder this step wrote, never an arbitrary one.
        if not (output_dir / SITE_NAME).is_file():
            raise ValueError(f"输出目录不是网站数据目录，拒绝覆盖：{output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    export_skill_data(output_dir, repository, text_source)
    export_battle_data(
        output_dir,
        models_dir=models_dir,
        template_path=template_path,
        research_preview=preview,
    )
    index = json.loads((output_dir / INDEX_NAME).read_text(encoding="utf-8"))
    # Only content-derived fields: the committed data must not change between
    # runs. The web build adds its own date and commit.
    site = {"schemaVersion": 1, "preview": not index["releaseReady"]}
    (output_dir / SITE_NAME).write_text(
        json.dumps(site, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return site


def export_release_files(output_dir, repository, text_source):
    """The release's PROCESSED_DATA carries the complete data as two single
    files, not the website's split copies."""
    output_dir = Path(output_dir)
    export_battle_release(output_dir / RELEASE_NAMES[0])
    export_skill_data(output_dir, repository, text_source, name=RELEASE_NAMES[1])
    return [output_dir / name for name in RELEASE_NAMES]
