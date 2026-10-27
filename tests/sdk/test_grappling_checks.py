"""Partial grappling decisions retain their manager boundary and real writes."""

from copy import deepcopy
import hashlib
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from capstone import Cs, CS_ARCH_X86, CS_MODE_64

from sdk.enemy_logic_exporter.monster import em0009_00_0 as gypseros
from sdk.enemy_logic_exporter.monster import em0070_00_0 as spider
from sdk.enemy_logic_exporter.shared.logic import grappling_checks as checks
from sdk.enemy_logic_exporter.shared.logic.expressions import (
    evaluate_expression,
    expression_unknown,
)
from sdk.enemy_logic_exporter.shared.logic.machine import Machine
from sdk.enemy_logic_exporter.shared.models.player_view import PlayerCompiler


class GrapplingCheckTests(unittest.TestCase):
    def sources(self, monster):
        proof = checks.receipt(monster.GRAPPLING_RECEIPT)
        records, memory = {}, {}
        for row in proof["methods"]:
            records.setdefault(row["type"], {}).setdefault("methods", {})[
                row["method"]
            ] = dict(
                function=row["address"][2:],
                returns=dict(type=row["returns"]),
                params=[
                    dict(type=name, modifier=modifier)
                    for name, modifier in zip(
                        row["parameters"], row["parameterModifiers"]
                    )
                ],
                impl_flags=row["implFlags"],
            )
            memory[int(row["address"], 16)] = bytes.fromhex(row["nativeBytes"])
        for row in proof["fieldChecks"]:
            records.setdefault(row["type"], {}).setdefault("fields", {})[
                row["field"]
            ] = dict(type=row["fieldType"], offset_from_base=row["offset"])
        for row in proof["enumChecks"]:
            records.setdefault(row["type"], {}).setdefault("fields", {})[
                row["field"]
            ] = dict(default=row["value"])
        decoder = Cs(CS_ARCH_X86, CS_MODE_64)
        decoder.detail = True
        for index, check in enumerate(proof["classChecks"], 1):
            row = next(
                row
                for row in proof["methods"]
                if row["methodBaseName"] == check["methodBaseName"]
            )
            address = int(row["address"], 16) + check["instructionOffset"]
            ins = next(
                decoder.disasm(
                    memory[int(row["address"], 16)][check["instructionOffset"] :],
                    address,
                )
            )
            slot = address + ins.size + ins.operands[check["operandIndex"]].mem.disp
            records.setdefault(check["expectedType"], {})["address"] = hex(index)[2:]
            memory[slot] = struct.pack("<Q", index)

        def read(address, size):
            for start, data in memory.items():
                if start <= address < start + len(data):
                    return data[address - start : address - start + size]
            return b""

        metadata = SimpleNamespace(
            get=lambda name: records.get(name),
            fields=lambda name: records.get(name, {}).get("fields", {}),
            enum=lambda name: (
                name,
                {
                    key: value["default"]
                    for key, value in records[name]["fields"].items()
                },
            ),
        )
        return (
            deepcopy(proof["methods"][0]),
            metadata,
            SimpleNamespace(read=read),
            records,
            memory,
        )

    def recipe(self, monster):
        row, metadata, pe, _, _ = self.sources(monster)
        return monster.recover_boolean_command_effect(row, metadata, pe)

    def truth(self, recipe, **values):
        return evaluate_expression(
            recipe["condition"]["expression"], None, values
        ).truth

    def test_gypseros_role_and_own_part_paths_are_independent(self):
        recipe = self.recipe(gypseros)
        self.assertTrue(
            self.truth(
                recipe,
                **{
                    checks.TARGET_READY: True,
                    checks.TARGET_ID: 9,
                    checks.TARGET_ROLE: 5,
                    checks.SELF_PART_COUNT: 0,
                }
            )
        )
        self.assertTrue(
            self.truth(
                recipe, **{checks.TARGET_READY: False, checks.SELF_PART_COUNT: 1}
            )
        )
        self.assertIsNone(
            self.truth(
                recipe, **{checks.TARGET_READY: False, checks.SELF_PART_COUNT: 0}
            )
        )
        self.assertTrue(expression_unknown(recipe["condition"]["expression"]))

    def test_spider_requires_a_ready_gypseros_then_own_role_or_target_part(self):
        recipe = self.recipe(spider)
        self.assertFalse(self.truth(recipe, **{checks.TARGET_READY: False}))
        self.assertFalse(
            self.truth(recipe, **{checks.TARGET_READY: True, checks.TARGET_ID: 9})
        )
        base = {
            checks.TARGET_READY: True,
            checks.TARGET_ID: 5,
            checks.SELF_ROLE: 0,
            checks.TARGET_PART_COUNT: 0,
        }
        self.assertIsNone(self.truth(recipe, **base))
        self.assertTrue(self.truth(recipe, **dict(base, **{checks.SELF_ROLE: 5})))
        self.assertTrue(
            self.truth(recipe, **dict(base, **{checks.TARGET_PART_COUNT: 2}))
        )
        self.assertEqual(recipe["onTrue"], {})
        self.assertEqual(recipe["onFalse"], {})

    def test_inputs_are_precise_array_cardinalities_and_not_helper_booleans(self):
        for monster, key, subject in [
            (gypseros, checks.SELF_PART_COUNT, "self"),
            (spider, checks.TARGET_PART_COUNT, "selected_enemy"),
        ]:
            recipe = self.recipe(monster)
            query = recipe["condition"]["queryContracts"][0]
            self.assertEqual(query["input"], key)
            self.assertEqual(query["source"], subject + ".Parts._BreakParts")
            self.assertEqual(
                query["predicate"],
                dict(
                    all=[
                        dict(field="_BreakCount", operator="gt", value=0),
                        dict(field="_BreakParamIndex", operator="eq", value=0),
                    ]
                ),
            )
            self.assertEqual(query["emptyArrayValue"], 0)
            self.assertTrue(recipe["condition"]["inputDefinitions"][key]["options"])
            self.assertTrue(recipe["condition"]["reviewedBooleanCommand"])

    def test_failed_work_or_extend_guard_does_not_write_capture(self):
        recipe = self.recipe(gypseros)
        guard = recipe["guard"]["expression"]
        for context in [
            dict(enemy_command_work_valid=False),
            dict(enemy_command_work_valid=True, self_extend_valid=False),
        ]:
            self.assertFalse(evaluate_expression(guard, None, context).truth)
        self.assertIsNone(
            evaluate_expression(guard, None, dict(enemy_command_work_valid=True)).truth
        )
        self.assertEqual(recipe["onTrue"], {gypseros.CAPTURE_KEY: True})
        self.assertEqual(recipe["onFalse"], {gypseros.CAPTURE_KEY: False})
        self.assertFalse(
            evaluate_expression(
                recipe["normalPrecondition"],
                None,
                {gypseros.CARRY_MANAGER_VALID: False},
            ).truth
        )

    def test_method_suffix_changes_do_not_change_identity(self):
        row, metadata, pe, records, _ = self.sources(gypseros)
        methods = records[row["type"]]["methods"]
        methods["onExecute999999"] = methods.pop(row["method"])
        row["method"] = "onExecute999999"
        recipe = gypseros.recover_boolean_command_effect(row, metadata, pe)
        self.assertEqual(
            recipe["condition"]["semanticEvidence"][0]["method"], "onExecute999999"
        )

    def test_changed_bytes_fields_or_enums_fail_closed(self):
        for category in ["bytes", "fields", "enums", "class"]:
            row, metadata, pe, records, memory = self.sources(gypseros)
            if category == "bytes":
                memory[int(row["address"], 16)] = (
                    b"\x90" + memory[int(row["address"], 16)][1:]
                )
            if category == "fields":
                records["app.cEmModuleParts.cBreakParts"]["fields"]["_BreakParamIndex"][
                    "offset_from_base"
                ] = "0x24"
            if category == "enums":
                records["app.EnemyDef.ID"]["fields"]["EM0009_00_0"]["default"] = 9
            if category == "class":
                records["app.cEnemyBTableCommandWork"]["address"] = "ff"
            with self.assertRaises(ValueError):
                gypseros.recover_boolean_command_effect(row, metadata, pe)

    def machine(self, monster):
        row, metadata, pe, _, _ = self.sources(monster)
        recipe = monster.recover_boolean_command_effect(row, metadata, pe)
        base = 0x14606CE00
        target = int(row["address"], 16)
        native = (
            b"\xe8"
            + struct.pack("<i", target - base - 5)
            + bytes.fromhex("84c07406b801000000c331c0c3")
        )
        machine = Machine(
            dict(
                type="fixture",
                method="table",
                address=hex(base),
                end=hex(base + len(native)),
                nativeSha256=hashlib.sha256(native).hexdigest(),
            ),
            native,
            pe,
            {},
            [{"_ArgumentType": ""}],
            {},
            {},
        )
        machine.metadata = metadata
        machine.reviewed_effects = True
        machine.boolean_commands[monster.GRAPPLING_COMMAND] = recipe
        machine.command_evidence[monster.GRAPPLING_COMMAND] = row
        bound = dict(
            commandType=monster.GRAPPLING_COMMAND,
            commandIndex=0,
            argumentIndex=None,
            argumentType="",
            argument={},
        )
        with patch.object(machine, "bind", return_value=bound):
            result = machine.build()
        return result, {node["id"]: node for node in result["nodes"]}

    def test_capture_writes_follow_both_body_results_but_not_guard_failure(self):
        graph, nodes = self.machine(gypseros)
        guard = nodes[graph["entry"]]
        self.assertEqual(nodes[guard["false"]]["kind"], "return")
        self.assertFalse(nodes[guard["false"]]["value"])
        refs = nodes[guard["true"]]
        self.assertEqual(nodes[refs["false"]]["boundaryKind"], "native_exception")
        body = nodes[refs["true"]]
        for branch, truth in [("true", True), ("false", False)]:
            mutation = nodes[body[branch]]
            self.assertEqual(mutation["stateUpdates"], {gypseros.CAPTURE_KEY: truth})
            self.assertEqual(nodes[mutation["next"]]["value"], truth)

    def test_spider_keeps_native_boolean_paths_without_capture_mutation(self):
        graph, nodes = self.machine(spider)
        guard = nodes[graph["entry"]]
        body = nodes[guard["true"]]
        self.assertEqual(nodes[body["true"]]["value"], True)
        self.assertEqual(nodes[body["false"]]["value"], False)
        self.assertFalse(any(node["kind"] == "mutation" for node in nodes.values()))

    def test_player_compile_keeps_part_inputs_unknown_boundary_and_false_write(self):
        graph, nodes = self.machine(gypseros)
        compiler = PlayerCompiler(
            dict(
                tables=[dict(tableGuid="t", nodes=list(nodes.values()))],
                rules=dict(rules=[]),
            )
        )
        body = next(
            node for node in nodes.values() if node.get("reviewedBooleanCommand")
        )
        expression = compiler.expression(body["expression"])
        self.assertEqual(expression["items"][-1]["op"], "unknown")
        self.assertTrue(compiler.inputs[checks.SELF_PART_COUNT]["options"])
        self.assertNotIn("grappling_result", compiler.inputs)
        false_write = compiler.node("t", nodes[body["false"]])
        self.assertEqual(false_write["stateUpdates"], {gypseros.CAPTURE_KEY: False})
        self.assertFalse(false_write["invalidateSnapshot"])


if __name__ == "__main__":
    unittest.main()
