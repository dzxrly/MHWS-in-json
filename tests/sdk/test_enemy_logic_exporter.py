"""Guard version changes and preserve graph topology across compound layout."""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from sdk.enemy_logic_exporter.shared.cli import ROOT, SUPPORTED_PROFILE, verify_profile
from sdk.enemy_logic_exporter.shared.manifest import selected
from sdk.il2cpp import upload_il2cpp
from src.processed_data.enemy_battle_logic.diagram import combined_diagram, node_id
from src.processed_data.enemy_battle_logic.viewer import render_html


class SdkTests(unittest.TestCase):
    def test_offline_cli_registers_each_subcommand_once(self):
        from sdk.enemy_logic_exporter.shared.cli import parser

        value = parser().parse_args(
            ["analyze", "--exe", "game.exe", "--version", "1.42.0.2"]
        )
        self.assertEqual(value.command, "analyze")
        value = parser().parse_args(
            [
                "requests",
                "--exe",
                "game.exe",
                "--index",
                "index.json",
                "--inventory",
                "inventory.json",
            ]
        )
        self.assertEqual(value.command, "requests")

    def test_version_mismatch_refuses_old_recipe(self):
        with patch(
            "sdk.enemy_logic_exporter.shared.cli.digest", return_value="different"
        ):
            with self.assertRaisesRegex(ValueError, "Source version changed"):
                verify_profile(Path("new.exe"), Path("new.json"), SUPPORTED_PROFILE)

    def test_il2cpp_paths_remain_project_relative_after_move(self):
        self.assertEqual(upload_il2cpp.PROJECT_DIR, ROOT)
        self.assertEqual(
            upload_il2cpp.DEFAULT_DUMP_PATH, ROOT / "src/data/il2cpp_dump.json"
        )
        self.assertEqual(upload_il2cpp.DEFAULT_WORK_DIR, ROOT / ".agents/il2cpp")

    def test_selection_uses_requested_monster_and_shared_commands(self):
        self.assertTrue(
            selected(
                "app.Em0022_00_BTable_Combat_Export", "table_test", "Em0022_00", "all"
            )
        )
        self.assertFalse(
            selected(
                "app.Em0001_00_BTable_Combat_Export", "table_test", "Em0022_00", "all"
            )
        )
        self.assertTrue(
            selected(
                "app.btable.EmCommonCommand.cCheckAngle",
                "onExecute10",
                "Em0022_00",
                "base",
            )
        )


class DiagramTests(unittest.TestCase):
    def graph(self):
        evidence = {"method": "fixture"}
        return dict(
            enemyId="fixture",
            resource="fixture_BTable_Combat.json",
            entry="a",
            profile={},
            scope="fixture",
            coverage={"localTables": 2, "nodes": 4},
            tables=[
                dict(
                    tableGuid="a",
                    tableIndex=1,
                    entry="0",
                    evidence=evidence,
                    nodes=[
                        dict(id="0", kind="call", targetTable="b", resume="1"),
                        dict(id="1", kind="return", value=False),
                    ],
                ),
                dict(
                    tableGuid="b",
                    tableIndex=2,
                    entry="0",
                    evidence=evidence,
                    nodes=[
                        dict(id="0", kind="unknown", reason="not recovered"),
                        dict(id="1", kind="return", value=False),
                    ],
                ),
            ],
        )

    def test_shared_call_and_continuation_are_separate_edges(self):
        graph = self.graph()
        snapshot = deepcopy(graph)
        diagram = combined_diagram(graph)
        self.assertEqual(graph, snapshot)
        nodes = [
            node["id"]
            for group in diagram["layout"]["children"]
            for node in group["children"]
        ]
        self.assertEqual(len(nodes), len(set(nodes)))
        edges = diagram["layout"]["edges"]
        call = next(edge for edge in edges if edge["role"] == "call")
        resume = next(edge for edge in edges if edge["role"] == "resume")
        self.assertEqual(call["targets"], [node_id("b", "0")])
        self.assertEqual(resume["targets"], [node_id("a", "1")])
        self.assertTrue(resume["continuation"])
        self.assertFalse(any(edge["sources"] == [node_id("b", "1")] for edge in edges))

    def test_offline_html_embeds_library_and_escapes_source_text(self):
        graph = self.graph()
        graph["tables"][1]["nodes"][0]["reason"] = "</script><script>bad</script>"
        html = render_html(graph)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("</script><script>bad", html)
        self.assertIn("elkjs 0.11.1", html)
        self.assertIn("Eclipse Public License", html)
        payload = html.split('<script id="data" type="application/json">')[1].split(
            "</script>"
        )[0]
        self.assertEqual(json.loads(payload)["graph"], graph)


if __name__ == "__main__":
    unittest.main()
