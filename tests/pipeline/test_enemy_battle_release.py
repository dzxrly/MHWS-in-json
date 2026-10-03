"""Exercise the JSON-only battle export and release rejection boundaries."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from src.pipeline.package import zip_processed_output
from src.pipeline.validation import validate_outputs
from src.processed_data.enemy_battle_logic.definitions import MODEL_DIR, read_models
from src.processed_data.enemy_battle_logic.exporter import (
    OUTPUT_NAMES,
    export_battle_logic,
)
from src.processed_data.enemy_battle_logic.validation import (
    validate_graph,
    validate_html,
)

ROOT = Path(__file__).resolve().parents[2]


class BattleReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.stage = Path(cls.temp.name)
        cls.processed = cls.stage / "processed_data"
        original_open = Path.open

        def json_only(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            if "r" in mode and (
                path.suffix.lower() == ".exe"
                or path.name == "il2cpp_dump.json"
                or "sdk" in path.parts
                or (".agents" in path.parts and not path.is_relative_to(cls.stage))
            ):
                raise AssertionError(f"Production export read a research input: {path}")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", json_only):
            export_battle_logic(cls.processed, ROOT / "MHWS-in-json/natives")
        cls.json_path = cls.processed / "enemy_battle_logic/EM0001_00_0.json"
        cls.html = (cls.processed / "enemy_battle_logic/EM0001_00_0.html").read_text(
            encoding="utf-8"
        )
        cls.graph = json.loads(cls.json_path.read_text(encoding="utf-8"))

    def test_default_release_uses_upstream_model_without_native_inputs(self):
        self.assertEqual(self.graph["coverage"]["localTables"], 11)
        self.assertEqual(self.graph["coverage"]["nodes"], 79)
        self.assertNotEqual(self.graph["entry"], self.graph["localEntry"])
        self.assertEqual(self.graph["metadataVerification"], "not_supplied")
        self.assertGreater(self.graph["coverage"]["unknownFlowNodes"], 0)

    def test_release_validation_and_zip_include_the_whole_battle_bundle(self):
        archive = zip_processed_output(
            self.processed, self.stage, "test", "PROCESSED_DATA"
        )
        expected = {f"processed_data/{name}" for name in OUTPUT_NAMES}
        records = validate_outputs(self.stage, expected, {archive.name: self.processed})
        self.assertEqual(len(records), len(OUTPUT_NAMES) + 1)
        with ZipFile(archive) as bundle:
            self.assertEqual(set(bundle.namelist()), set(OUTPUT_NAMES))
            self.assertEqual(
                bundle.read("enemy_battle_logic/EM0001_00_0.html"),
                (self.processed / "enemy_battle_logic/EM0001_00_0.html").read_bytes(),
            )

    def test_broken_continuation_and_coverage_cannot_be_released(self):
        broken = deepcopy(self.graph)
        node = next(
            n for t in broken["tables"] for n in t["nodes"] if n["kind"] == "call"
        )
        node["resume"] = "missing-node"
        with self.assertRaisesRegex(ValueError, "缺失节点"):
            validate_graph(broken)
        incorrect = deepcopy(self.graph)
        incorrect["coverage"]["nodes"] += 1
        with self.assertRaises(ValueError):
            validate_graph(incorrect)

    def test_html_must_embed_the_same_graph_without_external_scripts(self):
        changed = deepcopy(self.graph)
        changed["metadataVerification"] = "matched"
        with self.assertRaises(ValueError):
            validate_html(self.html, changed)
        with self.assertRaises(ValueError):
            validate_html(
                self.html + '<script src="https://example.test/layout.js"></script>',
                self.graph,
            )

    def test_two_active_versions_for_one_monster_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            content = (MODEL_DIR / "em0001.upstream.v1.json").read_bytes()
            (folder / "em0001.upstream.v1.json").write_bytes(content)
            (folder / "em0001.upstream.v2.json").write_bytes(content)
            with self.assertRaises(ValueError):
                read_models(models_dir=folder)


if __name__ == "__main__":
    unittest.main()
