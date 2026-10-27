"""Native navigation branch boundaries, field identity and unknown fallback."""

import unittest
import struct
from types import SimpleNamespace
from unittest.mock import patch

from sdk.enemy_logic_exporter.shared.logic.expressions import expression_unknown
from sdk.enemy_logic_exporter.shared.logic.expressions import evaluate_expression
from sdk.enemy_logic_exporter.shared.logic.navigation_conditions import (
    recover_navigation_condition,
    verify_navigation_conditions,
)
from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry

PREFIX = "app.btable.EmCommonCommand."


class NavigationConditionTests(unittest.TestCase):
    def bind(self, command="cCheckDestinationRelation", relation=1):
        node = dict(commandType=PREFIX + command)
        if command == "cCheckDestinationRelation":
            node["argument"] = dict(_EditType=relation)
        return recover_navigation_condition(node)

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

    def unfair_context(self):
        context = dict(
            enemy_command_work_valid=True,
            self_target_context_valid=True,
            selected_target_key_type=0,
            selected_target_key_unique_high_bit_clear=True,
            selected_hunter_lookup_found=True,
            selected_hunter_character_valid=True,
            self_current_stage_no=0,
            self_current_area_no=5,
            self_basic_category=0,
            selected_hunter_base_action_exists=False,
            selected_hunter_base_action_is_hunter_action=False,
            selected_hunter_ground_info_exists=True,
            selected_hunter_transform_valid=True,
            unfair_voxel_first_query_succeeded=True,
            unfair_voxel_second_query_succeeded=False,
            unfair_ground_transform_distance_squared=0.0,
            unfair_point_combat_area_no=5,
            selected_hunter_combat_area_bit_current=False,
            selected_hunter_combat_area_bit_special=False,
        )
        context.update(
            {
                "self_permanent_flag:129": False,
                "self_continue_flag:129": False,
                "selected_hunter_action_attr:29": False,
                "unfair_voxel_first_nav_attr:10": False,
                "unfair_voxel_second_nav_attr:27": False,
            }
        )
        return context

    def test_unfair_tarzan_fast_path_keeps_player_class_and_stage_guards(self):
        node = self.bind("cCheckUnfairRoutineActive")
        context = self.unfair_context()
        context.update(
            selected_hunter_base_action_exists=True,
            selected_hunter_base_action_is_hunter_action=True,
        )
        context["selected_hunter_action_attr:29"] = True
        for key in list(context):
            if key.startswith(("unfair_voxel_", "unfair_ground_", "unfair_point_")):
                del context[key]
        self.assertTrue(self.evaluate(node, context))
        self.assertFalse(self.evaluate(node, dict(context, selected_target_key_type=1)))
        self.assertFalse(self.evaluate(node, dict(context, self_current_stage_no=13)))
        self.assertIsNone(
            self.evaluate(
                node, dict(context, selected_hunter_base_action_is_hunter_action=False)
            )
        )
        other = self.unfair_context()
        other.update(
            {
                "selected_hunter_action_attr:26": True,
                "selected_hunter_continue_flag:294": True,
            }
        )
        self.assertFalse(self.evaluate(node, other))

    def test_unfair_voxel_failures_and_raw_bits_follow_distinct_branches(self):
        node, context = self.bind("cCheckUnfairRoutineActive"), self.unfair_context()
        self.assertFalse(self.evaluate(node, context))
        self.assertTrue(
            self.evaluate(node, dict(context, unfair_voxel_first_query_succeeded=False))
        )
        context["unfair_voxel_first_nav_attr:10"] = True
        for category in (0, 1):
            self.assertTrue(
                self.evaluate(node, dict(context, self_basic_category=category))
            )
        self.assertFalse(self.evaluate(node, dict(context, self_basic_category=2)))
        context["unfair_voxel_first_nav_attr:10"] = False
        context["unfair_voxel_second_nav_attr:27"] = True
        self.assertFalse(self.evaluate(node, context))
        self.assertTrue(
            self.evaluate(node, dict(context, unfair_voxel_second_query_succeeded=True))
        )
        del context["unfair_voxel_first_query_succeeded"]
        self.assertIsNone(self.evaluate(node, context))

    def test_unfair_st103_near_area_bounds_and_same_bit_identity(self):
        node, context = self.bind("cCheckUnfairRoutineActive"), self.unfair_context()
        context.update(
            self_current_stage_no=2,
            unfair_ground_transform_distance_squared=0.249999,
            selected_hunter_combat_area_bit_special=True,
        )
        self.assertTrue(self.evaluate(node, context))
        self.assertFalse(
            self.evaluate(
                node, dict(context, selected_hunter_combat_area_bit_current=True)
            )
        )
        # For area17 the native instructions read the same bit twice.
        self.assertFalse(self.evaluate(node, dict(context, self_current_area_no=17)))
        self.assertTrue(
            self.evaluate(
                node,
                dict(
                    context,
                    self_current_area_no=17,
                    selected_hunter_combat_area_bit_special=False,
                    selected_hunter_combat_area_bit_current=True,
                ),
            )
        )
        for area in (-1, 255, 256):
            invalid = dict(context, self_current_area_no=area)
            del invalid["selected_hunter_combat_area_bit_current"]
            self.assertTrue(self.evaluate(node, invalid))
        self.assertFalse(
            self.evaluate(
                node,
                dict(
                    context,
                    self_current_area_no=254,
                    selected_hunter_combat_area_bit_current=True,
                ),
            )
        )

    def test_unfair_st103_exact_distance_threshold_enters_point_query(self):
        node, context = self.bind("cCheckUnfairRoutineActive"), self.unfair_context()
        context.update(
            self_current_stage_no=2, unfair_ground_transform_distance_squared=0.25
        )
        for current, queried, expected in (
            (5, 17, True),
            (17, 5, True),
            (17, 17, False),
            (5, 6, False),
        ):
            with self.subTest(current=current, queried=queried):
                self.assertIs(
                    self.evaluate(
                        node,
                        dict(
                            context,
                            self_current_area_no=current,
                            unfair_point_combat_area_no=queried,
                        ),
                    ),
                    expected,
                )
        context["self_current_stage_no"] = 3
        context["unfair_point_combat_area_no"] = 17
        self.assertFalse(self.evaluate(node, context))

    def test_unfair_missing_transform_is_only_a_boundary_when_read(self):
        node, context = self.bind("cCheckUnfairRoutineActive"), self.unfair_context()
        context.update(
            selected_hunter_ground_info_exists=False,
            selected_hunter_transform_valid=False,
            unfair_voxel_first_query_succeeded=False,
        )
        self.assertIsNone(self.evaluate(node, context))
        context["selected_hunter_ground_info_exists"] = True
        self.assertTrue(self.evaluate(node, context))
        context.update(unfair_voxel_first_query_succeeded=True, self_current_stage_no=2)
        self.assertIsNone(self.evaluate(node, context))
        context["unfair_voxel_first_nav_attr:10"] = True
        self.assertTrue(self.evaluate(node, context))
        self.assertTrue(expression_unknown(node["expression"]))
        self.assertFalse(any("result" in key for key in node["inputDefinitions"]))

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

    def test_rise_and_terrain_follow_the_native_branches(self):
        rise = recover_navigation_condition(
            dict(
                commandType=PREFIX + "cCheckRise",
                argument=dict(_CheckHeight={"ace.btable.cEditFieldFloat": 25.0}),
            )
        )
        base = {
            "enemy_command_work_valid": True,
            "distance:2:0": 30.0,
            "self_current_stage_no": 0,
            "self_current_area_no": 0,
            "voxel_manager_valid": True,
            "voxel_self_info_found": True,
            "voxel_ceiling_clearance": 20.0,
        }
        # Clearance between 0 and the height difference: the ceiling blocks.
        self.assertFalse(self.evaluate(rise, base))
        self.assertTrue(self.evaluate(rise, dict(base, voxel_ceiling_clearance=40.0)))
        self.assertTrue(self.evaluate(rise, dict(base, voxel_ceiling_clearance=0.0)))
        # No voxel data or no query result: the native code answers true.
        self.assertTrue(self.evaluate(rise, dict(base, voxel_manager_valid=False)))
        self.assertTrue(self.evaluate(rise, dict(base, voxel_self_info_found=False)))
        # Below CheckHeight, or Stage 1 Area 6: false; an unordered h passes.
        self.assertFalse(self.evaluate(rise, dict(base, **{"distance:2:0": 24.0})))
        self.assertFalse(
            self.evaluate(
                rise, dict(base, self_current_stage_no=1, self_current_area_no=6)
            )
        )
        self.assertTrue(
            self.evaluate(rise, dict(base, **{"distance:2:0": float("nan")}))
        )
        terrain = self.bind("cCheckTerrainToDestination")
        base = {
            "enemy_command_work_valid": True,
            "voxel_manager_valid": True,
            "voxel_self_info_found": True,
            "voxel_wall_blocks_target": False,
            "distance:2:0": -5.0,
            "voxel_self_info_y": 3.0,
            "target_position_y": 4.0,
            "voxel_ceiling_distance": 2.0,
            "voxel_ceiling_y": 5.0,
        }
        # Monster above the target: the voxel floor must not be above it.
        self.assertTrue(self.evaluate(terrain, base))
        self.assertFalse(self.evaluate(terrain, dict(base, target_position_y=2.0)))
        self.assertFalse(
            self.evaluate(terrain, dict(base, voxel_wall_blocks_target=True))
        )
        # Monster not above: a negative ceiling distance or a ceiling at least
        # as high as the target passes.
        below = dict(base, **{"distance:2:0": 5.0})
        self.assertTrue(self.evaluate(terrain, below))
        self.assertFalse(self.evaluate(terrain, dict(below, voxel_ceiling_y=3.5)))
        self.assertTrue(
            self.evaluate(
                terrain, dict(below, voxel_ceiling_y=3.5, voxel_ceiling_distance=-1.0)
            )
        )

    def test_unlisted_relation_is_rejected(self):
        self.assertIsNone(self.bind(relation=2))

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


class NavigationEvidenceTests(unittest.TestCase):
    def fixture(self, *, value=255, moved=False, changed_bytes=False):
        code = bytes.fromhex("8b0d1a000000c3")
        document = dict(
            evidence={
                "unfair_active": [
                    dict(
                        type="fixture",
                        method="check1",
                        address="0x1000",
                        end="0x1007",
                        nativeBytes=code.hex(),
                        signature=dict(params=[], returns="System.Boolean"),
                    )
                ]
            },
            unfairConstants={"limit": 255},
            unfairFieldChecks=[],
            unfairEnumChecks=[],
            unfairRipChecks=[
                dict(
                    type="fixture",
                    method="check",
                    instructionOffset="0x0",
                    kind="Int32",
                    constant="limit",
                )
            ],
        )

        def read(address, size):
            if address == 0x1020:
                return struct.pack("<i", value)[:size]
            raw = (b"\x90" + code[1:]) if changed_bytes else code
            return (raw + b"\x90" * 16)[:size]

        metadata = SimpleNamespace(
            get=lambda owner: dict(
                methods={
                    "check1": dict(
                        function="1001" if moved else "1000",
                        params=[],
                        returns=dict(type="System.Boolean"),
                    )
                }
            )
        )
        return document, SimpleNamespace(read=read), metadata

    def test_unfair_constants_are_read_from_matched_instruction_targets(self):
        document, pe, metadata = self.fixture()
        with patch(
            "sdk.enemy_logic_exporter.shared.logic.navigation_conditions.receipt",
            return_value=document,
        ):
            verify_navigation_conditions(pe, metadata)
        for change in ({"value": 254}, {"moved": True}, {"changed_bytes": True}):
            document, pe, metadata = self.fixture(**change)
            with self.subTest(change=change), patch(
                "sdk.enemy_logic_exporter.shared.logic.navigation_conditions.receipt",
                return_value=document,
            ), self.assertRaises(ValueError):
                verify_navigation_conditions(pe, metadata)


if __name__ == "__main__":
    unittest.main()
