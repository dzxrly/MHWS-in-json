"""The committed website JSON is what the generator writes from the repo today."""

import json
from pathlib import Path
import tempfile
import unittest

from config import BASE_DIR, NATIVES_DIR
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource
from src.processed_data.enemy_battle_logic.definitions import (
    EXPECTED_ENEMY_IDS,
    read_models,
)
from src.processed_data.enemy_battle_logic.model_io import load_model
from src.site_data import (
    DEFAULT_DIR,
    RELEASE_NAMES,
    export_release_files,
    export_site_data,
    output_names,
)


def _files(folder):
    return {
        path.relative_to(folder).as_posix(): path
        for path in folder.rglob("*")
        if path.is_file()
    }


class CommittedSiteDataTests(unittest.TestCase):
    def test_committed_data_is_current(self):
        scratch = BASE_DIR / ".tmp" / "test-runs"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            fresh = Path(directory) / "data"
            export_site_data(
                fresh,
                SourceRepository(NATIVES_DIR),
                TextSource.from_natives(NATIVES_DIR),
            )
            expected, committed = _files(fresh), _files(DEFAULT_DIR)
            self.assertEqual(
                set(committed),
                set(expected),
                "网站数据已过期：运行 python -m src.site_data 后提交",
            )
            for name, path in expected.items():
                with self.subTest(file=name):
                    self.assertEqual(
                        json.loads(committed[name].read_text(encoding="utf-8")),
                        json.loads(path.read_text(encoding="utf-8")),
                        "网站数据已过期：运行 python -m src.site_data 后提交",
                    )
        self.assertEqual(set(committed), set(output_names()))
        # GitHub warns above 50 MB per file and rejects 100 MB.
        largest = max(path.stat().st_size for path in committed.values())
        self.assertLess(largest, 25 * 2**20)

    def test_release_has_complete_single_files(self):
        scratch = BASE_DIR / ".tmp" / "test-runs"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            paths = export_release_files(
                Path(directory),
                SourceRepository(NATIVES_DIR),
                TextSource.from_natives(NATIVES_DIR),
            )
            self.assertEqual([p.name for p in paths], list(RELEASE_NAMES))
            battle = json.loads(paths[0].read_text(encoding="utf-8"))
            skills = json.loads(paths[1].read_text(encoding="utf-8"))
        ids = [m["enemyId"] for m in battle["monsters"]]
        self.assertEqual(set(ids), set(EXPECTED_ENEMY_IDS))
        # Full graphs, not the website's trimmed pages.
        first = read_models()[0]
        self.assertEqual(battle["monsters"][0]["graph"], load_model(first.path))
        committed = DEFAULT_DIR / "skill_details/skills.json"
        self.assertEqual(skills, json.loads(committed.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
