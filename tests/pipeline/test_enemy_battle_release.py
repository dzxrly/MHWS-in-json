"""Validate semantic preview boundaries and reject incomplete releases."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from src.pipeline.package import zip_processed_output
from src.pipeline.validation import validate_outputs
from src.processed_data.enemy_battle_logic.definitions import (
    DEFAULT_TEMPLATE,
    EXPECTED_ENEMY_IDS,
    read_models,
    output_names,
)
from src.processed_data.enemy_battle_logic.exporter import export_battle_logic
from src.processed_data.enemy_battle_logic.validation import (
    validate_graph,
    validate_html,
    validate_bundle,
    embedded_data,
)
from src.processed_data.enemy_battle_logic.audit import validate_release_graph

ROOT = Path(__file__).resolve().parents[2]


class BattleReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = ROOT / ".agents" / "test-runs"
        scratch.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=scratch)
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
            ):
                raise AssertionError(f"Production export read a research input: {path}")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", json_only):
            cls.paths = export_battle_logic(
                cls.processed,
                ROOT / "MHWS-in-json/natives",
                template_path=DEFAULT_TEMPLATE,
            )
        cls.html = (cls.processed / "enemy_battle_logic/EM0001_00_0.html").read_text(
            encoding="utf-8"
        )
        cls.graph = embedded_data(cls.html)["graph"]

    def test_preview_is_html_only_and_keeps_actual_flow(self):
        index = validate_bundle(self.processed, require_release=False)
        self.assertFalse(index["releaseReady"])
        self.assertEqual({p.suffix for p in self.paths}, {".html"})
        self.assertEqual(self.graph["coverage"]["localTables"], 46)
        self.assertEqual(self.graph["coverage"]["nodes"], 408)
        self.assertEqual(self.graph["coverage"]["unknownFlowNodes"], 41)
        self.assertEqual(len(index["monsters"]), 1)
        self.assertNotIn("enemy_native_model", self.html)
        self.assertNotIn("行动逻辑待核实", self.html)

    def test_missing_monsters_reject_before_any_output(self):
        incomplete = read_models(template_path=DEFAULT_TEMPLATE)
        target = self.stage / "rejected"
        with patch(
            "src.processed_data.enemy_battle_logic.exporter.read_models",
            return_value=incomplete,
        ):
            with self.assertRaisesRegex(ValueError, "缺少已恢复"):
                export_battle_logic(target, ROOT / "MHWS-in-json/natives")
        self.assertFalse(target.exists())
        self.assertEqual(len(EXPECTED_ENEMY_IDS), 34)
        self.assertNotIn("EM0165_00_0", EXPECTED_ENEMY_IDS)
        self.assertEqual(len(output_names()), 35)

    def test_local_entry_cannot_be_called_global_combat_entry(self):
        with self.assertRaisesRegex(ValueError, "战斗总入口"):
            validate_release_graph(self.graph)
        changed = deepcopy(self.graph)
        changed["coverage"]["globalCombatEntryRecovered"] = True
        with self.assertRaisesRegex(ValueError, "入口恢复标志"):
            validate_graph(changed)

    def test_preview_cannot_be_published_as_pages(self):
        spec = importlib.util.spec_from_file_location(
            "battle_pages", ROOT / ".github/scripts/build_pages.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        destination = self.stage / "pages"
        with self.assertRaisesRegex(ValueError, "战斗总入口"):
            module.build_pages(
                self.processed,
                destination,
                version="test",
                repository="dzxrly/MHWS-in-json",
            )
        self.assertFalse(destination.exists())

    def test_zip_preserves_preview_bytes_but_release_gate_rejects_it(self):
        archive = zip_processed_output(
            self.processed, self.stage, "test", "PROCESSED_DATA"
        )
        relative = {p.relative_to(self.processed).as_posix() for p in self.paths}
        with ZipFile(archive) as bundle:
            self.assertEqual(set(bundle.namelist()), relative)
            self.assertEqual(
                bundle.read("enemy_battle_logic/EM0001_00_0.html"),
                (self.processed / "enemy_battle_logic/EM0001_00_0.html").read_bytes(),
            )
        with self.assertRaisesRegex(ValueError, "战斗总入口"):
            validate_outputs(
                self.stage,
                {f"processed_data/{name}" for name in relative},
                {archive.name: self.processed},
            )

    def test_broken_continuation_and_coverage_cannot_be_released(self):
        broken = deepcopy(self.graph)
        next(n for t in broken["tables"] for n in t["nodes"] if n["kind"] == "call")[
            "resume"
        ] = "missing-node"
        with self.assertRaisesRegex(ValueError, "缺失节点"):
            validate_graph(broken)
        incorrect = deepcopy(self.graph)
        incorrect["coverage"]["nodes"] += 1
        with self.assertRaises(ValueError):
            validate_graph(incorrect)

    def test_html_must_embed_same_graph_without_external_scripts(self):
        changed = deepcopy(self.graph)
        changed["metadataVerification"] = "matched"
        with self.assertRaises(ValueError):
            validate_html(self.html, changed)
        with self.assertRaises(ValueError):
            validate_html(
                self.html + '<script src="https://example.test/layout.js"></script>',
                self.graph,
            )

    def test_native_index_and_duplicate_models_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.stage) as directory:
            folder = Path(directory)
            (folder / "em0002.native.v1.json").write_text(
                json.dumps(dict(documentType="enemy_native_model")), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "原生索引"):
                read_models(folder)
        with tempfile.TemporaryDirectory(dir=self.stage) as directory:
            folder = Path(directory)
            content = DEFAULT_TEMPLATE.read_bytes()
            (folder / "em0001.v1.json").write_bytes(content)
            (folder / "em0001.v2.json").write_bytes(content)
            with self.assertRaisesRegex(ValueError, "同一怪物"):
                read_models(folder)


if __name__ == "__main__":
    unittest.main()
