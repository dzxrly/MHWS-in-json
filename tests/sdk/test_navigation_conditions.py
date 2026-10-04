"""Native navigation branch boundaries, field identity and unknown fallback."""

import unittest

from sdk.enemy_logic_exporter.shared.logic.expressions import expression_unknown
from sdk.enemy_logic_exporter.shared.logic.expressions import evaluate_expression
from sdk.enemy_logic_exporter.shared.logic.navigation_conditions import (
    recover_navigation_condition,
)
from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry
from sdk.enemy_logic_exporter.shared.config import SUPPORTED_PROFILE

PREFIX = "app.btable.EmCommonCommand."


class NavigationConditionTests(unittest.TestCase):
    def bind(self, command="cCheckDestinationRelation", relation=1):
        node = dict(commandType=PREFIX + command)
        if command == "cCheckDestinationRelation":
            node["argument"] = dict(_EditType=relation)
        return recover_navigation_condition(node, SUPPORTED_PROFILE)

    def evaluate(self, node, context):
        return evaluate_expression(
            node["expression"], RuleRegistry.load(), context
        ).truth

    def context(self):
        values = dict(
            enemy_command_work_valid=True,
            self_target_context_valid=True,
            destination_nav_query_succeeded=True,
            self_target_module_valid=True,
            destination_override_has_value=False,
            destination_target_position_has_value=True,
            destination_wall_query_succeeded=True,
            destination_wall_distance=6,
            destination_displacement_length=6,
            destination_displacement_y=-1,
            self_basic_category=0,
            self_current_area_no=0,
            self_current_stage_no=0,
        )
        for member, bits in {
            "_Attribute1": (1, 4, 7, 8, 9),
            "_MaskBits": (8, 13, 31),
            "_NaviAttribute": (3, 5, 6),
        }.items():
            for bit in bits:
                values[f"destination_wall:{member}:bit:{bit}"] = False
        values["destination_wall:_MaskBits:bit:8"] = True
        return values

    def test_low_exact_distance_and_height_boundaries(self):
        node, context = self.bind(), self.context()
        self.assertFalse(expression_unknown(node["expression"]))
        self.assertTrue(self.evaluate(node, context))
        for key, value in [
            ("destination_wall_distance", -0.001),
            ("destination_wall_distance", 6.001),
            ("destination_displacement_y", 0),
            ("destination_displacement_y", 1),
            ("destination_wall:_NaviAttribute:bit:3", True),
            ("destination_nav_query_succeeded", False),
            ("destination_wall_query_succeeded", False),
            ("self_target_module_valid", False),
        ]:
            with self.subTest(key=key, value=value):
                self.assertFalse(self.evaluate(node, dict(context, **{key: value})))
        self.assertTrue(self.evaluate(node, dict(context, destination_wall_distance=0)))
        del context["destination_wall_distance"]
        self.assertIsNone(self.evaluate(node, context))

    def test_category_is_boss_zako_animal_and_not_ai_state(self):
        node, context = self.bind(), self.context()
        self.assertFalse(self.evaluate(node, dict(context, self_basic_category=1)))
        context["destination_wall:_MaskBits:bit:13"] = True
        for category in (1, 2):
            self.assertTrue(
                self.evaluate(node, dict(context, self_basic_category=category))
            )
        context["destination_wall:_MaskBits:bit:8"] = False
        self.assertFalse(self.evaluate(node, context))
        context["destination_wall:_Attribute1:bit:4"] = True
        del context["self_basic_category"]
        self.assertTrue(self.evaluate(node, context))

    def test_nullable_override_and_target_query_are_distinct(self):
        node, context = self.bind(), self.context()
        context["destination_target_position_has_value"] = False
        self.assertFalse(self.evaluate(node, context))
        context["destination_override_has_value"] = True
        self.assertTrue(self.evaluate(node, context))
        context["self_target_module_valid"] = False
        self.assertFalse(self.evaluate(node, context))

    def test_high_keeps_physical_fallback_unknown(self):
        node, context = self.bind(relation=0), self.context()
        context["destination_displacement_y"] = 1
        self.assertTrue(expression_unknown(node["expression"]))
        self.assertFalse(self.evaluate(node, context))
        for member, bit in [
            ("_NaviAttribute", 5),
            ("_Attribute1", 1),
            ("_Attribute1", 8),
            ("_Attribute1", 9),
        ]:
            modified = dict(context)
            modified[f"destination_wall:{member}:bit:{bit}"] = True
            self.assertTrue(self.evaluate(node, modified))
        context["self_current_area_no"] = 2
        context["destination_wall:_Attribute1:bit:7"] = True
        self.assertIsNone(self.evaluate(node, context))
        # The complete physical qualification still has no final-result Boolean key.
        context["native_command_result:" + PREFIX + "cCheckDestinationRelation"] = True
        self.assertIsNone(self.evaluate(node, context))
        self.assertFalse(self.evaluate(node, dict(context, self_current_stage_no=1)))
        self.assertFalse(
            self.evaluate(node, dict(context, destination_displacement_y=0))
        )

    def test_unfair_rejection_guards_do_not_read_active_field(self):
        node = self.bind("cCheckUnfairRoutineActive")
        context = dict(
            enemy_command_work_valid=True,
            self_target_context_valid=True,
            selected_target_key_type=0,
            selected_target_key_unique_high_bit_clear=True,
            selected_hunter_lookup_found=True,
            selected_hunter_character_valid=True,
            self_current_stage_no=0,
            self_current_area_no=0,
        )
        context.update(
            {"self_permanent_flag:129": False, "self_continue_flag:129": False}
        )
        self.assertIsNone(self.evaluate(node, context))
        self.assertFalse(self.evaluate(node, dict(context, selected_target_key_type=1)))
        self.assertFalse(
            self.evaluate(
                node, dict(context, selected_target_key_unique_high_bit_clear=False)
            )
        )
        self.assertFalse(self.evaluate(node, dict(context, self_current_stage_no=13)))
        self.assertFalse(
            self.evaluate(
                node, dict(context, self_current_stage_no=10, self_current_area_no=4)
            )
        )
        self.assertFalse(
            self.evaluate(node, dict(context, **{"self_continue_flag:129": True}))
        )
        self.assertIsNone(
            self.evaluate(node, dict(context, is_active_unfair_routine=True))
        )

    def test_occlusion_disabled_flags_and_missing_inputs(self):
        node = self.bind("cCheckOccludedToDest")
        self.assertFalse(self.evaluate(node, {"enemy_command_work_valid": False}))
        context = {
            "enemy_command_work_valid": True,
            "self_permanent_flag:128": False,
            "self_continue_flag:128": False,
        }
        self.assertIsNone(self.evaluate(node, context))
        self.assertFalse(
            self.evaluate(node, dict(context, **{"self_permanent_flag:128": True}))
        )
        self.assertFalse(
            self.evaluate(node, dict(context, **{"self_continue_flag:128": True}))
        )

    def test_profile_and_unlisted_relation_are_rejected(self):
        self.assertIsNone(self.bind(relation=2))
        with self.assertRaisesRegex(ValueError, "来源版本"):
            recover_navigation_condition({}, {})

    def test_occlusion_ray_range_and_gimmick_filter(self):
        node = self.bind("cCheckOccludedToDest")
        self.assertFalse(expression_unknown(node["expression"]))
        context = {
            "enemy_command_work_valid": True,
            "self_permanent_flag:128": False,
            "self_continue_flag:128": False,
            "selected_target_key_type": 0,
            "occlusion_ray_length_squared": 2499.9,
            "destination_occlusion_ray_hits": [],
        }
        self.assertFalse(self.evaluate(node, context))
        context["destination_occlusion_ray_hits"] = [{"key_category": 1}]
        self.assertTrue(self.evaluate(node, context))
        self.assertFalse(
            self.evaluate(node, dict(context, occlusion_ray_length_squared=2500))
        )
        for category in (-1, 3, 6):
            self.assertFalse(
                self.evaluate(node, dict(context, selected_target_key_type=category))
            )
        context["destination_occlusion_ray_hits"] = [
            {"key_category": 4, "key_unique_index": 100}
        ]
        self.assertIsNone(self.evaluate(node, context))
        context["occlusion_special_gimmick_unique_index"] = 100
        self.assertTrue(self.evaluate(node, context))
        context["occlusion_special_gimmick_unique_index"] = -1
        hit = context["destination_occlusion_ray_hits"][0]
        hit["gimmick_lookup_found"] = False
        self.assertTrue(self.evaluate(node, context))
        hit.update(
            gimmick_lookup_found=True, gimmick_game_object_valid=True, gimmick_id=123
        )
        context["self_occluded_check_through_gimmick_ids"] = [123]
        self.assertFalse(self.evaluate(node, context))
        context["self_occluded_check_through_gimmick_ids"] = [124]
        self.assertTrue(self.evaluate(node, context))
        context["destination_occlusion_ray_hits"] = [
            {"key_category": 4},
            {"key_category": 1},
        ]
        self.assertTrue(self.evaluate(node, context))


if __name__ == "__main__":
    unittest.main()
