from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from sdk.action_map_exporter.action_data import ActionDataCatalog
from sdk.action_map_exporter.action_relations import (
    action_identity,
    build_action_relations,
)
from sdk.action_map_exporter.models import (
    ActionGuide,
    ActionSeed,
    Il2CppMethod,
    MotionSetHit,
    MotionTarget,
    MotlistRequestSetEvent,
    RequestSetIdentity,
)
from sdk.action_map_exporter.request_sets import RequestSetCatalog
from sdk.action_map_exporter.utils import murmur3_utf16


class ActionGuideNameTests(unittest.TestCase):
    def setUp(self):
        self.guide = ActionGuide(
            "Wp10", -12, 7, "STAB", "69b0ff9d-1ce7-4b73-a36b-6f5b1b504e90", "突き"
        )
        self.target = RequestSetIdentity(
            "Wp10", "Wp10/Attack.rcol.38.json", 5, murmur3_utf16("突き"), 2
        )

    def resolve(self, guides):
        return build_action_relations(
            [], {}, RequestSetCatalog([self.target]), {}, guides=guides
        )

    def test_guide_without_action_class_keeps_real_identity_and_order(self):
        result = self.resolve([self.guide])
        self.assertEqual(len(result.relations), 1)
        relation = result.relations[0]
        self.assertEqual(relation["actionIdentity"], "guide:Wp10:-12")
        self.assertEqual(relation["actionOrder"], 7)
        self.assertEqual(relation["evidence"], [])
        self.assertEqual(result.mapped_actions, set())

    def test_same_name_different_guides_remains_ambiguous(self):
        result = self.resolve([self.guide, replace(self.guide, guide_id=13)])
        self.assertEqual(result.relations, [])
        self.assertEqual(result.unresolved_names[0].guide_ids, (-12, 13))

    def test_cross_scope_name_cannot_bind(self):
        self.assertEqual(
            self.resolve([replace(self.guide, scope="Wp00")]).relations, []
        )

    def test_class_backed_ambiguous_name_keeps_explicit_derived_candidate(self):
        action = ActionSeed(
            "Wp10",
            "app.Wp10Action.Stab",
            -12,
            7,
            "STAB",
            self.guide.name_guid,
            self.guide.japanese_name,
            (),
        )
        result = build_action_relations(
            [action],
            {action: []},
            RequestSetCatalog([self.target]),
            {},
            guides=[self.guide, replace(self.guide, guide_id=13)],
        )
        self.assertEqual(len(result.relations), 1)
        self.assertEqual(result.relations[0]["confidence"], "derived")
        self.assertEqual(
            result.relations[0]["conditions"][0]["candidateGuideIds"], [-12, 13]
        )
        self.assertEqual(result.unresolved_names[0].guide_ids, (-12, 13))

    def test_unguided_classes_keep_separate_identities(self):
        first = ActionSeed(
            "Wp10", "app.Wp10Action.cA", -1, 2**31 - 1, "cA", "", "", (), guided=False
        )
        second = replace(first, class_name="app.Wp10Action.cB", internal_name="cB")
        self.assertEqual(action_identity(first), "class:Wp10:app.Wp10Action.cA")
        self.assertEqual(action_identity(replace(first, guided=True)), "guide:Wp10:-1")
        event = MotlistRequestSetEvent(
            1, "wp10_00_1", 5, "motion", 0, "", 0, "", 0.0, None
        )
        target = MotionTarget(
            "Wp10", (20 << 12) | 1, 20, 1, "wp10_00.motlist", "wp10_00", (event,)
        )

        def hit(action: ActionSeed) -> MotionSetHit:
            return MotionSetHit(
                action.class_name, ".ctor", 0x1000, 0x1004, "Mov_r64_imm64", 1, target
            )

        methods = {
            a.class_name: [Il2CppMethod(a.class_name, ".ctor", 0x1000)]
            for a in (first, second)
        }
        result = build_action_relations(
            [first, second],
            {first: [hit(first)], second: [hit(second)]},
            RequestSetCatalog([self.target]),
            methods,
            guides=[],
        )
        self.assertEqual(
            sorted(r["actionIdentity"] for r in result.relations),
            ["class:Wp10:app.Wp10Action.cA", "class:Wp10:app.Wp10Action.cB"],
        )
        self.assertEqual(
            sorted(r["actionInternalName"] for r in result.relations), ["cA", "cB"]
        )

    def test_catalog_collects_guide_even_without_actionparam(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "natives/STM/GameDesign/Player/ActionData").mkdir(parents=True)
            guide_path = (
                root
                / "natives/STM/GameDesign/Common/Player/ActionGuide/ActionGuideData_Wp10Name.user.3.json"
            )
            guide_path.parent.mkdir(parents=True)
            guide_path.write_text(
                json.dumps(
                    {
                        "_Action": "[-12] STAB",
                        "_Index": 7,
                        "_ActionName": self.guide.name_guid,
                    }
                ),
                encoding="utf8",
            )
            catalog = ActionDataCatalog.load(root)
        self.assertEqual(catalog.actions, [])
        self.assertEqual(
            [(g.scope, g.guide_id, g.guide_order) for g in catalog.guides],
            [("Wp10", -12, 7)],
        )


if __name__ == "__main__":
    unittest.main()
