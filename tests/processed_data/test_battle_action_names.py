"""Check variant identity, raw names and explicit naming evidence boundaries."""

from pathlib import Path
import unittest

from sdk.enemy_logic_exporter.shared.resources.reader import (
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
