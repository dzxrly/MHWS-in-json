"""JSON read by the website; the only interface between src and web/.

The web app imports nothing from src or sdk. It reads this folder:

  site.json                          build date, commit and preview flag
  enemy_battle_logic/index.json      monster list of the overview page
  enemy_battle_logic/<enemyId>.json  one monster: graph and technical diagram
  skill_details/skills.json          skill effect values and their meanings

``python -m src.site_data`` writes it to src/site_data/data, which the web
build copies into the site's data/ folder; the release export also ships it
in PROCESSED_DATA under ``website/``.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess

from config import BASE_DIR
from src.processed_data.enemy_battle_logic.definitions import (
    EXPECTED_ENEMY_IDS,
    MODEL_DIR,
)

from .enemy_battle_logic import BUNDLE_DIR, INDEX_NAME, export_battle_data
from .skill_details import OUTPUT_NAME as SKILLS_NAME, export_skill_data

DEFAULT_DIR = Path(__file__).with_name("data")
PROCESSED_FOLDER = "website"
SITE_NAME = "site.json"
REPOSITORY = "dzxrly/MHWS-in-json"


def output_names():
    """Release file set, for the full 34-monster data."""
    return (
        SITE_NAME,
        SKILLS_NAME,
        INDEX_NAME,
        *(f"{BUNDLE_DIR}/{enemy_id}.json" for enemy_id in EXPECTED_ENEMY_IDS),
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
    commit = (
        os.environ.get("CF_PAGES_COMMIT_SHA")
        or os.environ.get("GITHUB_SHA")
        or subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=BASE_DIR, text=True
        ).strip()
    )
    site = {
        "schemaVersion": 1,
        "builtOn": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "commit": commit,
        "repository": os.environ.get("GITHUB_REPOSITORY") or REPOSITORY,
        "preview": not index["releaseReady"],
    }
    (output_dir / SITE_NAME).write_text(
        json.dumps(site, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return site
