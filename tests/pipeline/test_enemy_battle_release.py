"""Validate offline HTML export, graph structure and archive contents."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from src.pipeline.package import zip_processed_output
from src.processed_data.enemy_battle_logic.definitions import (
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

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = (
    ROOT / "tests/fixtures/enemy_battle_logic/em0001.upstream.reference.v1.json"
)


def _is_research_input(path, root):
    path = path.resolve()
    root = root.resolve()
    return (
        path.suffix.lower() == ".exe"
        or path.name == "il2cpp_dump.json"
        or path.is_relative_to(root / "sdk")
        or path.is_relative_to(root / "MHWS-in-json")
    )


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
            if "r" in mode and _is_research_input(path, ROOT):
                raise AssertionError(f"Production export read a research input: {path}")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", json_only):
            cls.paths = export_battle_logic(
                cls.processed,
                template_path=DEFAULT_TEMPLATE,
            )
        cls.html = (cls.processed / "enemy_battle_logic/EM0001_00_0.html").read_text(
            encoding="utf-8"
        )
        cls.graph = embedded_data(cls.html)["graph"]

    def test_research_guard_ignores_checkout_ancestor_names(self):
        for checkout_name in ("MHWS-in-json", "sdk"):
            root = self.stage / checkout_name / checkout_name
            for relative in (
                "tests/fixtures/enemy_battle_logic/em0001.upstream.reference.v1.json",
                "src/processed_data/enemy_battle_logic/models/em0001.v1.json",
                "sdk-preview/graph.json",
                "MHWS-in-json-preview/graph.json",
            ):
                with self.subTest(checkout=checkout_name, path=relative):
                    self.assertFalse(_is_research_input(root / relative, root))
            for relative in (
                "sdk/data/models/em0001.v1.json",
                "MHWS-in-json/em0001.user.3.json",
                "MonsterHunterWilds.exe",
                "src/data/il2cpp_dump.json",
            ):
                with self.subTest(checkout=checkout_name, path=relative):
                    self.assertTrue(_is_research_input(root / relative, root))

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

    def test_independent_candidate_slots_validate_their_actual_call_targets(self):
        from sdk.enemy_logic_exporter.shared.models.validation import (
            validate_graph as sdk_validate,
        )

        changed = deepcopy(self.graph)
        node = next(
            n
            for t in changed["tables"]
            for n in t["nodes"]
            if n["kind"] == "weighted_random"
        )
        original = deepcopy(node["candidates"][0])
        node["candidates"] = [
            dict(
                original, id=f"slot:{i}", nodeId=original["id"], nativeCandidateIndex=i
            )
            for i in range(2)
        ]
        for validate in (sdk_validate, validate_graph):
            validate(changed)
            node["candidates"][1]["nativeCandidateIndex"] = 0
            with self.assertRaisesRegex(ValueError, "槽位身份"):
                validate(changed)
            node["candidates"][1]["nativeCandidateIndex"] = 1
            node["candidates"][1]["nodeId"] = node["id"]
            with self.assertRaisesRegex(ValueError, "调用连接"):
                validate(changed)
            node["candidates"][1]["nodeId"] = original["id"]

    def test_known_non_dispatch_records_cannot_invent_a_table_entry(self):
        from sdk.enemy_logic_exporter.shared.models.validation import (
            validate_graph as sdk_validate,
        )

        changed = deepcopy(self.graph)
        proof = dict(
            type="Owner",
            method="updateTableInpl123",
            address="0x1000",
            end="0x1001",
            nativeSha256="a" * 64,
        )
        record = dict(
            resource=next(iter(changed["sourceHashes"])),
            nativeType="Owner",
            status="native_no_dispatch_verified",
            evidence=proof,
            entryInstruction=dict(address="0x1000", bytes="c3", mnemonic="ret"),
            metadataTypeSha256="b" * 64,
        )
        changed["resourceNonDispatchEntries"] = [record]
        for validate in (sdk_validate, validate_graph):
            validate(changed)
            record["tableGuid"] = changed["entry"]
            with self.assertRaisesRegex(ValueError, "空调度"):
                validate(changed)
            del record["tableGuid"]
            record["entryInstruction"]["bytes"] = "90"
            with self.assertRaisesRegex(ValueError, "空调度"):
                validate(changed)
            record["entryInstruction"]["bytes"] = "c3"

    def test_missing_monsters_reject_before_any_output(self):
        incomplete = read_models(template_path=DEFAULT_TEMPLATE)
        target = self.stage / "rejected"
        with patch(
            "src.processed_data.enemy_battle_logic.exporter.read_models",
            return_value=incomplete,
        ):
            with self.assertRaisesRegex(ValueError, "缺少已恢复"):
                export_battle_logic(target)
        self.assertFalse(target.exists())
        self.assertEqual(len(EXPECTED_ENEMY_IDS), 34)
        self.assertNotIn("EM0165_00_0", EXPECTED_ENEMY_IDS)
        self.assertEqual(len(output_names()), 35)

    def test_zip_preserves_html_bytes(self):
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
        changed["metadataVerification"] = (
            "not_supplied"
            if self.graph["metadataVerification"] == "matched"
            else "matched"
        )
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
