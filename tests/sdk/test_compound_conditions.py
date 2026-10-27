"""Nested resource hashes, native short-circuit semantics and binding failures."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from sdk.enemy_logic_exporter.shared.logic.compound_conditions import (
    receipt,
    recover_compound_condition,
    verify_compound_conditions,
)
from sdk.enemy_logic_exporter.shared.logic.expressions import evaluate_expression
from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry


class CompoundConditionsTests(TestCase):
    def test_nested_reviewed_scene_query_keeps_its_input_definition(self):
        recovered = dict(
            sceneInput="fixture_scene",
            summary="已核实的局部方位查询",
            expression=dict(
                kind="runtime",
                key="fixture_scene:query",
                source="reviewed query output",
            ),
        )
        factory = dict(_OrderType="fixture.Query", _ArgumentType="fixture.Arg")
        with patch(
            "sdk.enemy_logic_exporter.shared.logic.compound_conditions.recover_condition",
            return_value=recovered,
        ):
            result = self.recover(
                "cCommandOr", [self.child(1, "fixture.Arg", {})], {1: factory}
            )
        self.assertIs(
            result["inputDefinitions"]["fixture_scene:query"]["boolean"], True
        )
        self.assertEqual(result["expression"]["items"][0], recovered["expression"])

    def recover(self, command, children, factories):
        return recover_compound_condition(
            dict(
                commandType="ace.btable." + command,
                argumentType="ace.btable.ConditionCommandArg",
                argument=dict(argumentCommands=children),
            ),
            "fixture",
            SimpleNamespace(factories_by_hash=lambda _: factories),
            {},
            RuleRegistry.load(),
            {},
        )

    def child(self, identity, argument_type, argument):
        return {
            "ace.btable.ConditionCommandArg.ArgumentCommand": {
                "_ArgumentCommandHash": identity,
                "_ArgumentCommandArgument": {argument_type: argument},
            }
        }

    def test_empty_and_and_or_follow_native_false_result(self):
        for command in ("cCommandAnd", "cCommandOr"):
            expression = self.recover(command, [], {})["expression"]
            self.assertIs(
                evaluate_expression(expression, RuleRegistry.load(), {}).truth, False
            )

    def test_order_bank_hash_selects_actual_self_status_command(self):
        factory = dict(
            _OrderType="app.btable.EmCommonCommand.cCheckSelfStatus",
            _ArgumentType="app.btable.EmCommonCommand.cCheckStatusArg",
        )
        child = self.child(
            42,
            factory["_ArgumentType"],
            {
                "_EditCategory": "[3] STATUS",
                "Status": {
                    "app.btable.EmCommonCommand.cCheckStatusStatusArg": {
                        "_EditArg": "[0] ANGRY"
                    }
                },
                "AIState": {},
                "Health": {},
                "StandState": {},
            },
        )
        result = self.recover("cCommandAnd", [child], {42: factory})
        predicate = result["expression"]["items"][0]["predicate"]
        self.assertEqual(predicate["commandType"], factory["_OrderType"])
        self.assertEqual(predicate["kind"], "self_status")

    def test_unbound_child_keeps_unknown_without_discarding_nested_false(self):
        unknown = self.child(99, "fixture", {})
        nested = self.child(
            1, "ace.btable.ConditionCommandArg", dict(argumentCommands=[])
        )
        factory = dict(
            _OrderType="ace.btable.cCommandAnd",
            _ArgumentType="ace.btable.ConditionCommandArg",
        )
        expression = self.recover("cCommandAnd", [unknown, nested], {1: factory})[
            "expression"
        ]
        self.assertIs(
            evaluate_expression(expression, RuleRegistry.load(), {}).truth, False
        )

    def test_hash_argument_type_conflict_is_rejected(self):
        factory = dict(
            _OrderType="ace.btable.cCommandAnd",
            _ArgumentType="ace.btable.ConditionCommandArg",
        )
        with self.assertRaisesRegex(ValueError, "类型不匹配"):
            self.recover("cCommandOr", [self.child(1, "wrong", {})], {1: factory})

    def test_changed_native_bytes_cannot_enable_compound_recipe(self):
        rows = receipt()["methods"]
        metadata = SimpleNamespace(
            get=lambda name: {
                "methods": {
                    row["method"]: dict(function=row["address"])
                    for row in rows
                    if row["type"] == name
                }
            }
        )
        with self.assertRaisesRegex(ValueError, "字节变化"):
            verify_compound_conditions(
                SimpleNamespace(read=lambda *_: b"changed"), metadata
            )
