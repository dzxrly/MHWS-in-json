"""Check variant identity, raw names and explicit naming evidence boundaries."""

from copy import deepcopy
from pathlib import Path
import unittest

from src.processed_data.enemy_battle_logic.builder import build_chain
from src.processed_data.enemy_battle_logic.validation import validate_graph
from src.processed_data.enemy_battle_logic.viewer import render_action_names
from src.processed_data.enemy_battle_logic.action_names import action_identity
from src.processed_data.enemy_battle_logic.resources import (
    Resources,
    typed,
    action_request_guid,
)

ROOT = Path(__file__).resolve().parents[2]


class ActionNameTests(unittest.TestCase):
    def test_inherited_action_uses_base_guid_and_keeps_instance_identity(self):
        resources = Resources(ROOT / "MHWS-in-json/natives")
        table = resources.read(
            "STM/GameDesign/Enemy/Em0002/50/BTable/Em0002_50_BTable_CommonAttack.user.3.json"
        )
        action = resources.action(table, typed(table["_CommandArgArray"][495])[1])
        self.assertEqual(action["actionGuid"], "19968770-35ed-4479-8643-795d7982ae28")
        self.assertEqual(
            action["instanceActionGuid"], "44cedecb-7ad2-06f9-3ad0-a5eb38cda2f5"
        )
        self.assertEqual(action["actionGuidBinding"], "base_guid")
        self.assertEqual(action["actionClass"], "cGlide")
        self.assertEqual(action["parameterInfo"]["_ActionGuid"], action["actionGuid"])

    def test_instance_guid_cannot_override_a_nonempty_base_guid(self):
        self.assertEqual(
            action_request_guid(
                {"_InstanceGuid": "instance", "_BaseActionGuid": "base"}
            ),
            "base",
        )
        self.assertEqual(
            action_request_guid(
                {
                    "_InstanceGuid": "instance",
                    "_BaseActionGuid": "00000000-0000-0000-0000-000000000000",
                }
            ),
            "instance",
        )

    def test_inherited_branched_parameter_is_resolved_in_declared_base_resource(self):
        resources = Resources(ROOT / "MHWS-in-json/natives")
        table = resources.read(
            "STM/GameDesign/Enemy/Em0002/50/BTable/Em0002_50_BTable_CommonAttack.user.3.json"
        )
        action = resources.action(table, typed(table["_CommandArgArray"][119])[1])
        self.assertEqual(
            action["parameterVariantGuid"], "5b642714-aae9-47f6-a590-e2394ccc4225"
        )
        self.assertEqual(action["actionClass"], "cBreathAttack")
        self.assertIn("/Em0002/00/", action["parameterAsset"])
        self.assertIn("/Em0002/50/", action["declaredParameterAsset"])
        self.assertEqual(len(action["parameterResolutionChain"]), 2)

    @classmethod
    def setUpClass(cls):
        cls.graph = build_chain(ROOT / "MHWS-in-json/natives")

    def test_exact_action_variants_and_repeated_nodes_have_stable_names(self):
        actions = [
            n["action"]
            for t in self.graph["tables"]
            for n in t["nodes"]
            if n["kind"] == "action"
        ]
        self.assertEqual(len(actions), 12)
        self.assertEqual(
            len({action_identity(self.graph["enemyId"], a) for a in actions}), 11
        )
        dash = [a for a in actions if a["actionClass"] == "cDashCombat"]
        self.assertEqual(len({a["parameterVariantGuid"] for a in dash}), 2)
        self.assertTrue(all(a["displayName"] == "战斗突进移动" for a in dash))
        self.assertTrue(all(a["nameBinding"]["identityVerified"] for a in actions))

    def test_project_original_names_keep_uid_and_distinct_comments(self):
        rows = self.graph["actionNameCatalog"]["shellCatalog"]
        self.assertEqual(len(rows), 7)
        same_name = [r for r in rows if r["name"] == "ブレス(ターゲットへの補正なし)"]
        self.assertEqual({r["uniqueId"] for r in same_name}, {1, 2})
        self.assertEqual(
            {r["comment"] for r in same_name}, {"３連ブレス２撃目", "３連ブレス３撃目"}
        )
        self.assertTrue(
            all(
                not r["shellTriggerBindingVerified"]
                for r in self.graph["actionNameCatalog"]["bindings"]
            )
        )

    def test_mismatched_guid_name_is_rejected(self):
        graph = deepcopy(self.graph)
        node = next(
            n for t in graph["tables"] for n in t["nodes"] if n["kind"] == "action"
        )
        node["action"]["nameBinding"]["parameterVariantGuid"] = "different-guid"
        with self.assertRaisesRegex(ValueError, "参数变体"):
            validate_graph(graph)

    def test_unverified_shell_link_cannot_be_promoted_by_annotation(self):
        graph = deepcopy(self.graph)
        node = next(
            n for t in graph["tables"] for n in t["nodes"] if n["kind"] == "action"
        )
        node["action"]["nameBinding"]["shellTriggerBindingVerified"] = True
        with self.assertRaisesRegex(ValueError, "触发关系"):
            validate_graph(graph)

    def test_raw_names_are_escaped_for_html(self):
        graph = deepcopy(self.graph)
        graph["actionNameCatalog"]["shellCatalog"][0][
            "name"
        ] = "</td><script>alert(1)</script>"
        html = render_action_names(graph)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
