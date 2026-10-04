"""Regress native boundary semantics, resource binding and preserved continuations."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.processed_data.enemy_battle_logic import RuleRegistry
from src.processed_data.enemy_battle_logic.builder import (
    build_chain,
    trace_until_request,
)
from src.processed_data.enemy_battle_logic.random_choice import (
    choose_with_uint32,
    weighted_pool,
)
from src.processed_data.enemy_battle_logic.timers import (
    TimerState,
    advance_timer,
    timer_operation,
)

ROOT = Path(__file__).resolve().parents[2]
NATIVES = ROOT / "MHWS-in-json/natives"
TIMER = "f0788707-65eb-49af-a5b0-f3b8555053f9"


class PredicateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = RuleRegistry.load()

    def bound(self, kind, values):
        rule = next(r for r in self.registry.data["rules"] if r["kind"] == kind)
        argument = {rule["bindings"][k]: v for k, v in values.items()}
        return self.registry.bind(rule["commandType"], rule["argumentType"], argument)

    def test_distance_equality_passes_neither_near_nor_far(self):
        for compare in (0, 1):
            with self.subTest(compare=compare):
                bound = self.bound(
                    "distance",
                    {
                        "threshold": 10,
                        "compare": compare,
                        "height": 0,
                        "axis": 0,
                        "base": 0,
                    },
                )
                context = {
                    "distance:0:0": 10,
                    "distance_scale": 1,
                    "distance_offset": 0,
                }
                self.assertIs(self.registry.evaluate(bound, context).truth, False)
                context["distance:0:0"] = 9 if compare == 0 else 11
                self.assertIs(self.registry.evaluate(bound, context).truth, True)

    def test_distance_modifier_is_required_and_applied(self):
        bound = self.bound(
            "distance",
            {"threshold": 10, "compare": 0, "height": 0, "axis": 0, "base": 0},
        )
        context = {"distance:0:0": 20}
        self.assertIsNone(self.registry.evaluate(bound, context).truth)
        context.update(distance_scale=2, distance_offset=1)
        self.assertIs(self.registry.evaluate(bound, context).truth, True)

    def test_signed_height_and_inside_range_use_different_comparisons(self):
        for height, measured, expected in (
            (0, 6, True),
            (0, -6, False),
            (1, -6, True),
            (2, -4, True),
            (2, 6, False),
            (2, 5, False),
        ):
            with self.subTest(height=height, measured=measured):
                bound = self.bound(
                    "distance",
                    {
                        "threshold": 5,
                        "compare": 1,
                        "height": height,
                        "axis": 2,
                        "base": 0,
                    },
                )
                self.assertIs(
                    self.registry.evaluate(
                        bound,
                        {
                            "distance:2:0": measured,
                            "distance_scale": 1,
                            "distance_offset": 0,
                        },
                    ).truth,
                    expected,
                )

    def test_distance_modifier_trigger_uses_current_or_pending_ai_state(self):
        bound = self.bound(
            "distance",
            {"threshold": 10, "compare": 0, "height": 0, "axis": 0, "base": 0},
        )
        ordinary = {"distance:0:0": 11, "ai_state_current": 2, "ai_state_pending": 2}
        self.assertIs(self.registry.evaluate(bound, ordinary).truth, False)
        combat = dict(ordinary, ai_state_pending=3)
        self.assertIsNone(self.registry.evaluate(bound, combat).truth)
        combat["objects"] = {
            "app.cEmModuleCombatEm": {
                "<CombatRangeScale>k__BackingField": 2,
                "<CombatRangeOffset>k__BackingField": 1,
            }
        }
        self.assertIs(self.registry.evaluate(bound, combat).truth, True)
        combat["ai_state_current"], combat["ai_state_pending"] = 3, 2
        self.assertIs(self.registry.evaluate(bound, combat).truth, True)
        ordinary["ai_state_pending"] = None
        self.assertIsNone(self.registry.evaluate(bound, ordinary).truth)

    def test_angle_uses_half_width_including_boundary(self):
        bound = self.bound(
            "angle", {"width": 180, "base": 0, "option": 0, "option2": 0}
        )
        for angle, expected in ((0, True), (90, True), (90.001, False), (180, False)):
            with self.subTest(angle=angle):
                self.assertIs(
                    self.registry.evaluate(
                        bound, {"angle:0": angle, "angle_vectors_valid": True}
                    ).truth,
                    expected,
                )
        self.assertIs(
            self.registry.evaluate(
                bound, {"angle:0": 0, "angle_vectors_valid": False}
            ).truth,
            False,
        )

    def test_unverified_angle_option_never_defaults_to_true(self):
        bound = self.bound(
            "angle", {"width": 180, "base": 0, "option": 1, "option2": 0}
        )
        self.assertIsNone(
            self.registry.evaluate(
                bound, {"angle:0": 0, "angle_vectors_valid": True}
            ).truth
        )

    def test_timer_expiry_and_missing_state(self):
        bound = self.bound("timer", {"variable": TIMER})
        self.assertIsNone(self.registry.evaluate(bound, {}).truth)
        for remaining, expected in ((0, True), (-1, True), (0.001, False)):
            self.assertIs(
                self.registry.evaluate(bound, {"timers": {TIMER: remaining}}).truth,
                expected,
            )

    def test_mushroom_special_match_does_not_match_none(self):
        for expected, actual, truth in (
            (2, 5, True),
            (0, 5, False),
            (2, 3, False),
            (0, 0, True),
        ):
            bound = self.bound("mushroom", {"value": expected})
            binding = bound["contextBinding"]
            context = {"objects": {binding["type"]: {binding["field"]: actual}}}
            self.assertIs(self.registry.evaluate(bound, context).truth, truth)

    def test_electric_two_also_accepts_three_but_three_does_not_accept_two(self):
        for expected, actual, truth in (
            (2, 2, True),
            (2, 3, True),
            (2, 4, False),
            (3, 2, False),
        ):
            bound = self.bound("electric", {"value": expected})
            binding = bound["contextBinding"]
            self.assertIs(
                self.registry.evaluate(
                    bound, {"objects": {binding["type"]: {binding["field"]: actual}}}
                ).truth,
                truth,
            )

    def test_fang_quantity_comparisons_include_equality(self):
        for compare in (0, 1, 2):
            bound = self.bound("fang_count", {"compare": compare, "value": 2})
            binding = bound["contextBinding"]
            self.assertIs(
                self.registry.evaluate(
                    bound, {"objects": {binding["type"]: {binding["field"]: 2}}}
                ).truth,
                True,
            )

    def test_common_flight_state_is_blocked_by_extra_or_fixed_state(self):
        bound = self.bound(
            "self_status",
            {
                "category": 1,
                "stand": {"STRUCT__Value_Type": 0, "STRUCT__Value_Value": 1},
                "health": 100,
                "ai": 0,
            },
        )
        for extra, fixed, truth in ((-1, None, True), (0, None, False), (-1, 1, False)):
            context = {
                "objects": {
                    "app.cEnemyContext": {
                        "StandState": 1,
                        "ExtraState": extra,
                        "UniqueStateFixedID": fixed,
                    }
                }
            }
            self.assertIs(self.registry.evaluate(bound, context).truth, truth)

    def test_health_boundary_and_pending_ai_state(self):
        values = {"category": 4, "stand": {}, "health": 50, "ai": 1}
        bound = self.bound("self_status", values)
        self.assertIs(
            self.registry.evaluate(bound, {"self_health_ratio": 0.5}).truth, True
        )
        self.assertIs(
            self.registry.evaluate(bound, {"self_health_ratio": 0.501}).truth, False
        )
        values["category"] = 5
        bound = self.bound("self_status", values)
        self.assertIs(
            self.registry.evaluate(bound, {"ai_state_pending": 2}).truth, True
        )
        self.assertIsNone(self.registry.evaluate(bound, {"ai_state_pending": 0}).truth)

    def test_unknown_commands_and_mismatched_arguments_are_not_accepted(self):
        unknown = self.registry.bind("unverified.Command", None, {})
        self.assertIsNone(self.registry.evaluate(unknown, {}).truth)
        with self.assertRaises(ValueError):
            self.registry.bind(
                "app.btable.EmCommonCommand.cCheckAngle", "wrong.Argument", {}
            )


class RandomTests(unittest.TestCase):
    def test_exclusion_changes_the_conditional_pool(self):
        candidates = [
            {"id": "a", "weight": 2},
            {"id": "b", "weight": 3},
            {"id": "disabled", "weight": 0},
        ]
        self.assertEqual(
            [r["share"] for r in weighted_pool(candidates)], ["2/5", "3/5"]
        )
        self.assertEqual(
            weighted_pool(candidates, excluded=["a"]),
            [{"id": "b", "weight": 3, "share": "1"}],
        )
        self.assertEqual(
            [choose_with_uint32(candidates, n) for n in range(6)],
            ["a", "a", "b", "b", "b", "a"],
        )
        self.assertIsNone(choose_with_uint32(candidates, 0, excluded=["a", "b"]))

    def test_invalid_weights_or_oversized_pool_fail(self):
        for weight in (-1, 0.5, True, 0x80000000):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                weighted_pool([{"id": "a", "weight": weight}])


class TimerTests(unittest.TestCase):
    def test_activate_reset_pause_resume_and_auto_stop(self):
        state = timer_operation(TimerState(2, False), 15, "[0] ACTIVATE")
        self.assertEqual(state, TimerState(15, True))
        state = advance_timer(state, 4)
        self.assertEqual(state, TimerState(11, True))
        state = timer_operation(state, 15, "[1] DEACTIVATE")
        self.assertEqual(advance_timer(state, 10), TimerState(11, False))
        state = timer_operation(state, 15, "[2] REACTIVATE")
        self.assertEqual(advance_timer(state, 20), TimerState(0, False))

    def test_timer_input_and_writeability(self):
        state = TimerState(3, False)
        self.assertEqual(timer_operation(state, 15, 0, writable=False), state)
        for value in (True, float("nan"), "unknown"):
            with self.assertRaises(ValueError):
                TimerState(value, False)
        with self.assertRaises(ValueError):
            advance_timer(state, -1)
        with self.assertRaises(ValueError):
            timer_operation(state, 15, 3)


@unittest.skipUnless(
    (
        NATIVES
        / "STM/GameDesign/Enemy/Em0001/00/BTable/Em0001_00_BTable_CommonAttack.user.3.json"
    ).exists(),
    "需要真实雌火龙资源 JSON",
)
class RealResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = build_chain(NATIVES)
        # Test the local chain inside the production model, without a separate
        # four-table template in the formal build inputs.
        cls.graph["entry"] = cls.graph["localEntry"]

    def context(self, distance=11, timer=0):
        return {
            "distance:0:0": distance,
            "distance_scale": 1,
            "distance_offset": 0,
            "angle:0": 0,
            "angle_vectors_valid": True,
            "timers": {TIMER: timer},
            "objects": {
                "app.cEnemyContext": {
                    "StandState": 1,
                    "ExtraState": -1,
                    "UniqueStateFixedID": None,
                }
            },
        }

    def test_real_distance_boundaries_select_different_action_variants(self):
        for distance in (10, 10.0001, 11, 12):
            result = trace_until_request(self.graph, self.context(distance))
            if distance == 10:
                self.assertEqual(result["status"], "completed")
            elif distance < 12:
                self.assertEqual(
                    result["action"]["actionClass"], "cSomersaultDashCancel"
                )
                self.assertEqual(result["continuation"]["node"], "5")
            else:
                self.assertEqual(result["status"], "action_requested")
                self.assertNotEqual(
                    result["action"]["parameterVariantGuid"],
                    "00000000-0000-0000-0000-000000000000",
                )

    def test_missing_timer_is_unknown_and_active_timer_completes(self):
        context = self.context()
        del context["timers"]
        self.assertEqual(trace_until_request(self.graph, context)["status"], "unknown")
        self.assertEqual(
            trace_until_request(self.graph, self.context(timer=1))["status"],
            "completed",
        )

    def test_action_resume_requires_timer_state_change(self):
        first = trace_until_request(self.graph, self.context())
        resumed = trace_until_request(
            self.graph, self.context(), position=first["continuation"]
        )
        self.assertEqual(resumed["status"], "state_change_required")
        self.assertEqual(resumed["mutation"]["timerGuid"], TIMER)
        self.assertEqual(
            resumed["mutation"]["timer"]["definition"]["_DefaultValue"], 15.0
        )

    def test_child_calls_preserve_three_caller_return_positions(self):
        first = trace_until_request(self.graph, self.context(12))
        second = trace_until_request(
            self.graph, self.context(12), position=first["continuation"]
        )
        self.assertEqual(second["status"], "action_requested")
        self.assertEqual(len(second["continuation"]["stack"]), 3)
        third = trace_until_request(
            self.graph, self.context(12), position=second["continuation"]
        )
        self.assertEqual(third["status"], "action_requested")
        self.assertEqual(len(third["continuation"]["stack"]), 2)

    def test_build_opens_only_json_and_no_historical_analysis(self):
        opened = []
        original = Path.open

        def checked(path, *args, **kwargs):
            opened.append(path)
            self.assertEqual(path.suffix, ".json")
            self.assertNotIn(".agents", path.parts)
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", checked):
            graph = build_chain(NATIVES)
        self.assertTrue(opened)
        self.assertEqual(graph["coverage"]["unknownConditions"], 0)

    def test_parameter_value_edit_rebinds_but_slot_layout_change_fails(self):
        temporary_root = ROOT / ".agents/enemy-battle-logic-tests"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
            fixture = Path(directory)
            for relative in self.graph["sourceHashes"]:
                target = fixture / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(NATIVES / relative, target)
            source = fixture / self.graph["resource"]
            data = json.loads(source.read_text(encoding="utf-8"))
            arguments = next(iter(data[0].values()))["_CommandArgArray"]
            argument = next(iter(arguments[260].values()))
            argument["_Distance"] = {"ace.btable.cEditFieldFloat": 11}
            source.write_text(json.dumps(data), encoding="utf-8")
            rebound = build_chain(fixture)
            rebound["entry"] = rebound["localEntry"]
            self.assertEqual(
                trace_until_request(rebound, self.context(10.5))["status"], "completed"
            )
            arguments[260] = arguments[259]
            source.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "结构"):
                build_chain(fixture)

    def test_mismatched_metadata_version_fails_before_resource_binding(self):
        temporary_root = ROOT / ".agents/enemy-battle-logic-tests"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
            metadata = Path(directory) / "different-metadata.json"
            metadata.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "元数据版本"):
                build_chain(NATIVES, metadata_path=metadata)


@unittest.skipUnless(
    (
        NATIVES
        / "STM/GameDesign/Enemy/Em0001/00/BTable/Em0001_00_BTable_Combat.user.3.json"
    ).exists(),
    "需要真实雌火龙 Combat 资源",
)
class UpstreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = build_chain(
            NATIVES,
            ROOT
            / "src/processed_data/enemy_battle_logic/models/em0001.upstream.v1.json",
        )
        # Exercise this selection chain inside the expanded Combat entry model.
        cls.graph["entry"] = cls.graph["selectionEntry"]

    def context(self, tired=False, angry=False):
        return {
            "objects": {
                "app.cEnemyContext": {
                    "IsTired": tired,
                    "IsAngry": angry,
                    "StandState": 0,
                    "ExtraState": -1,
                    "UniqueStateFixedID": None,
                }
            },
            "angle_vectors_valid": True,
            "angle:0": 0,
            "angle:3": 180,
            "distance:0:0": 11,
            "distance_scale": 1,
            "distance_offset": 0,
            "timers": {TIMER: 0, "a76a1178-86fa-48c5-be91-513666365680": 1},
        }

    def test_tired_precedes_angry_and_nonempty_skip_list_is_unknown(self):
        context = self.context(tired=True, angry=True)
        result = trace_until_request(self.graph, context)
        self.assertEqual(result["status"], "unknown")
        key = self.graph["entry"] + ":1"
        context["skip_list_matches_current_action"] = {key: False}
        result = trace_until_request(self.graph, context)
        self.assertEqual([c["weight"] for c in result["pool"]], [10, 70, 20])
        context["skip_list_matches_current_action"][key] = True
        result = trace_until_request(self.graph, context)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["path"][1]["selection"], "empty_pool_fallback")

    def test_angry_and_normal_pools_keep_conditional_weights(self):
        for angry, weights in ((True, [50, 50]), (False, [40, 35, 25])):
            result = trace_until_request(self.graph, self.context(angry=angry))
            self.assertEqual(result["status"], "random_draw_required")
            self.assertEqual([c["weight"] for c in result["pool"]], weights)

    def test_explicit_draw_enters_imported_table_and_preserves_combat_caller(self):
        context = self.context()
        context["random_draws"] = {self.graph["entry"] + ":15": 39}
        result = trace_until_request(self.graph, context)
        self.assertEqual(result["action"]["actionClass"], "cDashCombat")
        self.assertEqual(
            result["action"]["parameterVariantGuid"],
            "00000000-0000-0000-0000-000000000000",
        )
        self.assertEqual(
            result["continuation"]["stack"],
            [{"table": self.graph["entry"], "node": "17"}],
        )
        context["random_draws"][self.graph["entry"] + ":15"] = 75
        result = trace_until_request(self.graph, context)
        self.assertEqual(result["action"]["actionClass"], "cBreathAttackNoWeakPoint")
        self.assertEqual(len(result["continuation"]["stack"]), 2)
        next_result = trace_until_request(
            self.graph, context, position=result["continuation"]
        )
        self.assertEqual(next_result["status"], "state_change_required")
        self.assertEqual(next_result["mutation"]["effect"], "set_float_value")
        final_result = trace_until_request(
            self.graph, context, position=next_result["continuation"]
        )
        self.assertEqual(final_result["action"]["actionClass"], "cSomersaultDashCancel")
        self.assertEqual(len(final_result["continuation"]["stack"]), 2)

    def test_missing_native_getter_does_not_assume_normal_state(self):
        context = self.context()
        del context["objects"]["app.cEnemyContext"]["IsTired"]
        self.assertEqual(trace_until_request(self.graph, context)["status"], "unknown")

    def test_unknown_parts_prefix_stays_unknown(self):
        context = self.context()
        context["random_draws"] = {self.graph["entry"] + ":15": 40}
        context["timers"]["cc4ccfe8-5c49-41f7-9270-c32838a217e3"] = 0
        first = trace_until_request(self.graph, context)
        self.assertEqual(first["status"], "state_change_required")
        result = trace_until_request(
            self.graph, context, position=first["continuation"]
        )
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["path"][-1]["node"], "18")
        self.assertEqual(self.graph["coverage"]["unknownFlowNodes"], 41)

    def test_new_builder_still_reads_only_formal_and_resource_json(self):
        original = Path.open

        def checked(path, *args, **kwargs):
            self.assertEqual(path.suffix, ".json")
            self.assertNotIn(".agents", path.parts)
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", checked):
            graph = build_chain(
                NATIVES,
                ROOT
                / "src/processed_data/enemy_battle_logic/models/em0001.upstream.v1.json",
            )
        self.assertEqual(graph["coverage"]["resourceTables"], 2)
        self.assertEqual(graph["coverage"]["weightedSelections"], 15)


if __name__ == "__main__":
    unittest.main()
