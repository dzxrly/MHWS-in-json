"""Validate the site's monster data: graph structure and the split page files."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.processed_data.enemy_battle_logic.definitions import (
    EXPECTED_ENEMY_IDS,
    read_models,
)
from src.processed_data.enemy_battle_logic.diagram import combined_diagram
from src.processed_data.enemy_battle_logic.model_io import load_model
from src.processed_data.enemy_battle_logic.validation import validate_graph
from src.site_data.enemy_battle_logic import (
    PAGE_FILES,
    TABLE_FIELDS,
    TREE_FIELDS,
    export_battle_data,
    page_files,
    validate_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = (
    ROOT / "src/processed_data/enemy_battle_logic/models/em0001_00_0.v1.json"
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
        scratch = ROOT / ".tmp" / "test-runs"
        scratch.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=scratch)
        cls.addClassCleanup(cls.temp.cleanup)
        cls.stage = Path(cls.temp.name)
        cls.data = cls.stage / "data"
        original_open = Path.open

        def json_only(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            if "r" in mode and _is_research_input(path, ROOT):
                raise AssertionError(f"Production export read a research input: {path}")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", json_only):
            cls.paths = export_battle_data(
                cls.data,
                template_path=DEFAULT_TEMPLATE,
            )
        folder = cls.data / "enemy_battle_logic/EM0001_00_0"
        cls.files = {
            name: (folder / name).read_text(encoding="utf-8") for name in PAGE_FILES
        }
        cls.text = "".join(cls.files.values())
        cls.graph = load_model(DEFAULT_TEMPLATE)

    def test_research_guard_ignores_checkout_ancestor_names(self):
        for checkout_name in ("MHWS-in-json", "sdk"):
            root = self.stage / checkout_name / checkout_name
            for relative in (
                "src/processed_data/enemy_battle_logic/models/em0001_00_0.v1.json",
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
                "MonsterHunterWilds/il2cpp_dump.json",
            ):
                with self.subTest(checkout=checkout_name, path=relative):
                    self.assertTrue(_is_research_input(root / relative, root))

    def test_preview_is_json_only_and_keeps_actual_flow(self):
        index = validate_bundle(self.data, require_release=False)
        self.assertFalse(index["releaseReady"])
        self.assertEqual({p.suffix for p in self.paths}, {".json"})
        self.assertEqual(
            json.loads(self.files["tree.json"])["coverage"], self.graph["coverage"]
        )
        self.assertEqual(len(index["monsters"]), 1)
        self.assertNotIn("enemy_native_model", self.text)
        self.assertNotIn("行动逻辑待核实", self.text)

    def test_independent_candidate_slots_validate_their_actual_call_targets(self):
        from sdk.enemy_logic_exporter.shared.models.validation import (
            validate_graph as sdk_validate,
        )

        changed = deepcopy(self.graph)
        # Only the graph's candidate slots are under test, not the player view.
        changed.pop("playerView", None)
        node = next(
            n
            for t in changed["tables"]
            for n in t["nodes"]
            if n["kind"] == "weighted_random"
        )
        original = deepcopy(node["candidates"][0])
        target = original.get("nodeId", original["id"])
        node["candidates"] = [
            dict(original, id=f"slot:{i}", nodeId=target, nativeCandidateIndex=i)
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
            node["candidates"][1]["nodeId"] = target

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
        )
        record = dict(
            resource=changed["sources"][0],
            nativeType="Owner",
            status="native_no_dispatch_verified",
            evidence=proof,
            entryInstruction=dict(address="0x1000", bytes="c3", mnemonic="ret"),
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
            "src.site_data.enemy_battle_logic.read_models",
            return_value=incomplete,
        ):
            with self.assertRaisesRegex(ValueError, "缺少已恢复"):
                export_battle_data(target)
        self.assertFalse(target.exists())
        self.assertEqual(len(EXPECTED_ENEMY_IDS), 34)
        self.assertNotIn("EM0165_00_0", EXPECTED_ENEMY_IDS)

    def test_broken_continuation_and_coverage_cannot_be_released(self):
        broken = deepcopy(self.graph)
        next(n for t in broken["tables"] for n in t["nodes"] if n["kind"] == "call")[
            "resume"
        ] = "missing-node"
        # The player view, built from the same flow, may notice it first.
        with self.assertRaisesRegex(ValueError, "缺失节点|继续位置"):
            validate_graph(broken)
        incorrect = deepcopy(self.graph)
        incorrect["coverage"]["nodes"] += 1
        with self.assertRaises(ValueError):
            validate_graph(incorrect)

    def test_pages_keep_only_the_fields_the_site_reads(self):
        written = {name: json.loads(text) for name, text in self.files.items()}
        self.assertEqual(written, json.loads(json.dumps(page_files(self.graph))))
        self.assertLessEqual(set(written["tree.json"]), set(TREE_FIELDS))
        self.assertEqual(written["tree.json"]["playerView"], self.graph["playerView"])
        self.assertTrue(
            all(set(table) <= set(TABLE_FIELDS) for table in written["tables.json"])
        )
        self.assertEqual(
            [table["nodes"] for table in written["tables.json"]],
            [table["nodes"] for table in self.graph["tables"]],
        )
        self.assertEqual(
            written["flow.json"],
            json.loads(json.dumps(combined_diagram(self.graph, compact_details=True))),
        )

    def test_bundle_rejects_a_missing_page_file(self):
        with tempfile.TemporaryDirectory(dir=self.stage) as directory:
            copy = Path(directory)
            export_battle_data(copy, template_path=DEFAULT_TEMPLATE)
            (copy / "enemy_battle_logic/EM0001_00_0/flow.json").unlink()
            with self.assertRaisesRegex(ValueError, "三个 JSON"):
                validate_bundle(copy, require_release=False)

    def test_output_folder_must_start_empty(self):
        with self.assertRaisesRegex(ValueError, "必须为空"):
            export_battle_data(self.data, template_path=DEFAULT_TEMPLATE)

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
