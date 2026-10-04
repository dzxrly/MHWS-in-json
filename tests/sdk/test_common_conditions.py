"""Check reviewed native condition cases, guards and missing runtime inputs."""

import unittest

from sdk.enemy_logic_exporter.shared.common_conditions import recover_condition
from sdk.enemy_logic_exporter.shared.expressions import evaluate_expression
from sdk.enemy_logic_exporter.shared.predicates import RuleRegistry
from sdk.enemy_logic_exporter.shared.profile import SUPPORTED_PROFILE

PREFIX = "app.btable.EmCommonCommand."


class ResourcesFixture:
    def read(self, path):
        return {
            "_PartsBreakArray": {
                "parts": {
                    "_DataArray": [
                        {
                            "record": {
                                "_InstanceGuid": "wing-guid",
                                "_PartsType": "[1] LEFT_WING",
                            }
                        }
                    ]
                }
            }
        }


class CommonConditionTests(unittest.TestCase):
    def bind(self, command, argument):
        return recover_condition(
            dict(commandType=PREFIX + command, argument=argument),
            SUPPORTED_PROFILE,
            "EM0002_00_0",
            ResourcesFixture(),
        )

    def evaluate(self, recovered, context):
        return evaluate_expression(
            recovered["expression"], RuleRegistry.load(), context
        ).truth

    def test_rank_guard_and_missing_input(self):
        node = self.bind(
            "cCheckSelfType",
            {
                "_EditCategory": "[2] QUEST_RANK",
                "QuestRank": {"rank": {"_EditArg": {"value": 2}}},
            },
        )
        context = dict(enemy_command_work_valid=True, self_target_context_valid=True)
        self.assertIsNone(self.evaluate(node, context))
        self.assertTrue(self.evaluate(node, dict(context, environment_current_rank=2)))
        self.assertFalse(self.evaluate(node, dict(context, environment_current_rank=1)))
        self.assertFalse(self.evaluate(node, dict(enemy_command_work_valid=False)))
        self.assertIsNone(
            self.bind(
                "cCheckSelfType",
                {
                    "_EditCategory": "[2] QUEST_RANK",
                    "QuestRank": {"rank": {"_EditArg": 3}},
                },
            )
        )

    def test_enemy_enum_mapping_preserves_native_wildcard(self):
        node = self.bind(
            "cCheckSelfType",
            {
                "_EditCategory": "[1] ENEMY",
                "Enemy": {"enemy": {"_EditArg": "[123] EM0002_50_0"}},
            },
        )
        context = dict(enemy_command_work_valid=True, self_target_context_valid=True)
        self.assertIsNone(self.evaluate(node, context))
        context["enemy_enum_index:123"] = -1
        self.assertTrue(self.evaluate(node, context))
        context["enemy_enum_index:123"] = 5
        self.assertFalse(self.evaluate(node, dict(context, self_basic_enemy_id=3)))
        self.assertTrue(self.evaluate(node, dict(context, self_basic_enemy_id=5)))

    def test_stun_uses_distinct_player_and_enemy_fields(self):
        node = self.bind(
            "cCheckTargetStatus",
            {
                "_EditCategory": "[2] BAD_CONDITION",
                "BadConditions": {"condition": {"_EditArg": "[4] STUN"}},
            },
        )
        player = dict(
            enemy_command_work_valid=True,
            selected_target_key_type=0,
            selected_hunter_context_valid=True,
            selected_hunter_stun_active=True,
        )
        self.assertTrue(self.evaluate(node, player))
        self.assertFalse(
            self.evaluate(node, dict(player, selected_hunter_stun_active=False))
        )
        enemy = dict(
            enemy_command_work_valid=True,
            selected_target_key_type=1,
            selected_enemy_context_enabled=True,
        )
        enemy.update(
            {
                "selected_enemy_condition_state:15": 0,
                "selected_enemy_condition_state:16": 1,
            }
        )
        self.assertTrue(self.evaluate(node, enemy))
        self.assertFalse(
            self.evaluate(node, dict(enemy, selected_enemy_context_enabled=False))
        )
        self.assertFalse(
            self.evaluate(
                node, dict(enemy_command_work_valid=True, selected_target_key_type=-1)
            )
        )
        self.assertIsNone(
            self.evaluate(
                node, dict(enemy_command_work_valid=True, selected_target_key_type=0)
            )
        )

    def test_parts_query_bounds_record_presence_and_count(self):
        node = self.bind(
            "cCheckBreakParts",
            {"_EditType": "[0] BREAK", "_EditBreakPartsGuid": {"guid": "wing-guid"}},
        )
        self.assertEqual(node["summary"], "左翼的破坏次数 > 0")
        lookup = "parts_lookup:wing-guid:"
        context = dict(enemy_command_work_valid=True, self_parts_break_index_count=3)
        context.update(
            {
                lookup + "has_value": True,
                lookup + "index": 2,
                lookup + "record_found": True,
                lookup + "break_count": 1,
            }
        )
        # Runtime lookup index is deliberately different from the label resource's index 0.
        self.assertTrue(self.evaluate(node, context))
        for field, value in [
            ("index", 3),
            ("has_value", False),
            ("record_found", False),
            ("break_count", 0),
        ]:
            with self.subTest(field=field):
                modified = dict(context)
                modified[lookup + field] = value
                self.assertFalse(self.evaluate(node, modified))
        del context[lookup + "break_count"]
        self.assertIsNone(self.evaluate(node, context))

    def test_unreviewed_cases_and_changed_profile_are_rejected(self):
        self.assertIsNone(
            self.bind("cCheckSelfType", {"_EditCategory": "[7] REWARD_RANK"})
        )
        self.assertIsNone(
            self.bind(
                "cCheckTargetStatus",
                {
                    "_EditCategory": "[2] BAD_CONDITION",
                    "BadConditions": {"condition": {"_EditArg": "[3] SLEEP"}},
                },
            )
        )
        with self.assertRaisesRegex(ValueError, "来源版本"):
            recover_condition({}, {}, "EM0002_00_0", ResourcesFixture())
