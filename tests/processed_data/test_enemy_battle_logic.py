"""Regress native boundary semantics, resource binding and preserved continuations."""

from pathlib import Path
import unittest

from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry
from sdk.enemy_logic_exporter.shared.logic.weights import (
    choose_with_uint32,
    weighted_pool,
)
from sdk.enemy_logic_exporter.shared.logic.timers import (
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




if __name__ == "__main__":
    unittest.main()
