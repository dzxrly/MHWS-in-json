"""Partial target commands preserve real exits, exceptions and call boundaries."""

from copy import deepcopy
import hashlib
from types import SimpleNamespace
import unittest

from sdk.enemy_logic_exporter.monster import em0150_00_0 as doshaguma
from sdk.enemy_logic_exporter.shared.logic import throw_target
from sdk.enemy_logic_exporter.shared.logic.expressions import evaluate_expression
from sdk.enemy_logic_exporter.shared.logic.machine import Machine
from sdk.enemy_logic_exporter.shared.logic.target_command_effects import (
    target_receipt,
    verify_target_receipt,
)
from tests.sdk.test_target_command_effects import ProofMetadata, ProofPE


def command_evidence(receipt, command):
    row = next(x for x in target_receipt(receipt)["methods"] if x["type"] == command)
    return {key: row[key] for key in ("type", "method", "address", "end")}


def throw(private=False):
    command = doshaguma.THROW_COMMAND if private else throw_target.COMMAND
    argument = doshaguma.THROW_ARGUMENT if private else throw_target.ARGUMENT
    bound = dict(
        commandType=command,
        argumentType=argument,
        argument={
            "_RangeMin": {"ace.btable.cEditFieldFloat": 2.0},
            "_RangeMax": {"ace.btable.cEditFieldFloat": 20.0},
        },
    )
    proof = command_evidence(throw_target.RECEIPT, command)
    return (
        doshaguma.recover_target_command_effect(bound, proof)
        if private
        else throw_target.throw_target_effect(bound, proof)
    )


def wall():
    return doshaguma.recover_target_command_effect(
        dict(commandType=doshaguma.WALL_COMMAND, argumentType="", argument={}),
        command_evidence(doshaguma.WALL_RECEIPT, doshaguma.WALL_COMMAND),
    )


def graph(detail, *, uses_boolean=True):
    native = bytes.fromhex(
        "84c07406b801000000c331c0c3" if uses_boolean else "b801000000c3"
    )
    row = dict(
        type="fixture",
        method="caller",
        address="0x1000",
        end=hex(0x1000 + len(native)),
        nativeSha256=hashlib.sha256(native).hexdigest(),
    )
    machine = Machine(row, native, SimpleNamespace(read=lambda *_: b""), {}, [], {}, {})
    entry = machine.target_command_nodes(
        "command",
        dict(nativeSite="0xffb"),
        detail,
        dict(arguments=[None]),
        0x1000,
        machine.initial(0),
    )
    return machine, entry


class TargetCommandGraphTests(unittest.TestCase):
    def test_private_throw_alias_requires_its_own_typed_argument(self):
        public, private = throw(), throw(True)
        self.assertEqual(public["nativeGraph"], private["nativeGraph"])
        self.assertEqual(public["returnType"], "System.Boolean")
        with self.assertRaisesRegex(ValueError, "参数类型"):
            doshaguma.recover_target_command_effect(
                dict(
                    commandType=doshaguma.THROW_COMMAND,
                    argumentType=throw_target.ARGUMENT,
                    argument={},
                ),
                command_evidence(throw_target.RECEIPT, doshaguma.THROW_COMMAND),
            )

    def test_throw_never_assumes_two_nullable_queries_are_the_same(self):
        nodes = throw()["nativeGraph"]["nodes"]
        self.assertNotEqual(
            nodes["first-position"]["expression"]["key"],
            nodes["second-position"]["expression"]["key"],
        )
        self.assertEqual(nodes["first-position"]["false"], "return-false")
        self.assertEqual(nodes["second-position"]["false"], "nullable-exception")
        self.assertNotIn("next", nodes["nullable-exception"])

    def test_collection_selection_is_unknown_with_exact_range_contract(self):
        detail = throw()
        selected = detail["nativeGraph"]["nodes"]["selection"]
        self.assertIsNone(evaluate_expression(selected["expression"], None, {}).truth)
        self.assertEqual(selected["queryContract"]["rangeMin"], 2)
        self.assertEqual(selected["queryContract"]["rangeMax"], 20)
        self.assertNotIn("throw_success", detail["inputDefinitions"])
        setter_guard = detail["nativeGraph"]["nodes"]["setter-guard"]
        self.assertEqual(setter_guard["false"], "hold-request")

    def test_target_write_precedes_unresolved_hold_and_actual_true_return(self):
        machine, entry = graph(throw())
        self.assertIs(machine.nodes[machine.nodes[entry]["false"]]["value"], False)
        update = machine.nodes["command-target-write"]
        boundary = machine.nodes[update["next"]]
        self.assertEqual(update["targetUpdates"][0]["orderName"], "SECOND")
        self.assertEqual(boundary["continuationKind"], "normal_return")
        self.assertNotIn("resume", boundary)
        self.assertIs(machine.nodes[boundary["next"]]["value"], True)

    def test_void_wall_guard_and_normal_return_rejoin_same_actual_caller(self):
        machine, entry = graph(wall(), uses_boolean=False)
        caller = machine.nodes[entry]["false"]
        self.assertIs(machine.nodes[caller]["value"], True)
        self.assertEqual(machine.nodes["command-fallback-write"]["next"], caller)
        boundary = machine.nodes["command-exclusive-call"]
        self.assertEqual(boundary["continuationKind"], "normal_return")
        self.assertEqual(machine.nodes[boundary["next"]]["kind"], "condition")

    def test_missing_exclusive_point_uses_fallback_but_failed_point_does_not(self):
        nodes = wall()["nativeGraph"]["nodes"]
        self.assertEqual(nodes["exclusive-result"]["false"], "fallback")
        self.assertEqual(nodes["point"]["false"], "return")
        self.assertEqual(nodes["fallback"]["false"], "return")
        self.assertNotIn("next", nodes["exception"])
        self.assertNotIn("resume", nodes["exception"])
        self.assertEqual(nodes["point-parameters"]["false"], "parameter-exception")
        self.assertNotIn("next", nodes["parameter-exception"])

    def test_receipts_reject_changed_native_bytes_and_fields(self):
        for name in (throw_target.RECEIPT, doshaguma.WALL_RECEIPT):
            proof = deepcopy(target_receipt(name))
            metadata = ProofMetadata(proof)
            pe = ProofPE(proof, metadata)
            self.assertTrue(verify_target_receipt(pe, metadata, name))
            row = proof["methods"][0]
            pe.ranges[int(row["address"], 16)] = (
                b"\x90" + bytes.fromhex(row["nativeBytes"])[1:]
            )
            with self.assertRaisesRegex(ValueError, "原生字节"):
                verify_target_receipt(pe, metadata, name)

    def test_wall_invalid_index_and_base_state_are_actual_native_values(self):
        nodes = wall()["nativeGraph"]["nodes"]
        invalid = next(
            row["value"]
            for row in target_receipt(doshaguma.WALL_RECEIPT)["constants"]
            if row.get("name") == "invalidGimmickUniqueIndex"
        )
        self.assertEqual(invalid, 2147483647)
        self.assertIs(
            evaluate_expression(
                nodes["point"]["expression"],
                None,
                {"wall_point_sub_unique_id": invalid},
            ).truth,
            False,
        )
        state = nodes["fallback-state"]["expression"]
        for value in (0, 3):
            self.assertIs(
                evaluate_expression(
                    state, None, {"wall_fallback_base_state": value}
                ).truth,
                True,
            )
        self.assertIs(
            evaluate_expression(state, None, {"wall_fallback_base_state": 1}).truth,
            False,
        )
        self.assertEqual(nodes["point-references"]["true"], "point-direction")
        self.assertEqual(nodes["point-direction"]["next"], "point-position")
        self.assertEqual(nodes["point-position"]["continuationKind"], "normal_return")
        self.assertNotIn("partialImplementationEffects", nodes["point-write"])


if __name__ == "__main__":
    unittest.main()
