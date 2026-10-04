"""Check actual x64 returns and navigation-result branches without game files."""

import hashlib
from importlib.util import find_spec
import unittest
from unittest.mock import patch


@unittest.skipUnless(find_spec("capstone"), "离线原生测试需要 SDK 的 Capstone 依赖")
class BTableMachineTests(unittest.TestCase):
    def machine(self, hexadecimal):
        from sdk.enemy_logic_exporter.shared.btable_machine import Machine

        native = bytes.fromhex(hexadecimal)
        row = dict(
            type="fixture",
            address="0x1000",
            nativeSha256=hashlib.sha256(native).hexdigest(),
        )
        return Machine(row, native, None, {}, [{"_ArgumentType": "fixture"}], {}, {})

    def test_native_return_value_is_preserved(self):
        for code, expected in (("b8 01 00 00 00 c3", True), ("31 c0 c3", False)):
            result = self.machine(code).build()
            self.assertEqual([node["value"] for node in result["nodes"]], [expected])

    def test_negation_sign_and_addition_carry_choose_native_branches(self):
        for code in (
            "b8 01 00 00 00 f7 d8 85 c0 78 06 b8 00 00 00 00 c3 b8 01 00 00 00 c3",
            "b8 ff ff ff ff 83 c0 01 72 06 b8 00 00 00 00 c3 b8 01 00 00 00 c3",
            "b8 05 00 00 00 83 f8 06 ff c0 72 06 b8 00 00 00 00 c3 b8 01 00 00 00 c3",
        ):
            with self.subTest(code=code):
                result = self.machine(code).build()
                self.assertEqual([node["value"] for node in result["nodes"]], [True])

    def test_destination_result_retains_both_native_continuations(self):
        machine = self.machine("e8 00 00 00 00 84 c0 74 06 b8 01 00 00 00 c3 31 c0 c3")
        binding = dict(
            commandType="fixture.cSetDest",
            commandIndex=0,
            argumentIndex=0,
            argumentType="fixture",
        )
        with patch.object(machine, "bind", return_value=binding):
            result = machine.build()
        nodes = {node["id"]: node for node in result["nodes"]}
        condition = nodes[nodes[result["entry"]]["next"]]
        self.assertEqual(condition["kind"], "condition")
        self.assertTrue(nodes[condition["true"]]["value"])
        self.assertFalse(nodes[condition["false"]]["value"])

    def test_destination_result_is_collapsed_only_if_both_paths_are_equal(self):
        machine = self.machine("e8 00 00 00 00 31 c0 c3")
        binding = dict(
            commandType="fixture.cSetDest",
            commandIndex=0,
            argumentIndex=0,
            argumentType="fixture",
        )
        with patch.object(machine, "bind", return_value=binding):
            result = machine.build()
        self.assertEqual(
            {node["kind"] for node in result["nodes"]}, {"mutation", "return"}
        )

    def test_random_type_command_returns_the_resource_enum_not_a_boolean(self):
        code = "e8 00 00 00 00 83 f8 02 75 06 b8 01 00 00 00 c3 31 c0 c3"
        for value, expected in ((0, False), (1, False), (2, True)):
            with self.subTest(value=value):
                machine = self.machine(code)
                binding = dict(
                    commandType="ace.btable.cCommandRandamRandomType",
                    commandIndex=0,
                    argumentIndex=0,
                    argumentType="fixture",
                    argument={"_EditType": f"[{value}] fixture"},
                )
                with patch.object(machine, "bind", return_value=binding):
                    result = machine.build()
                nodes = {node["id"]: node for node in result["nodes"]}
                mode = nodes[result["entry"]]
                self.assertEqual(mode["value"], value)
                self.assertEqual(nodes[mode["next"]]["value"], expected)
                self.assertEqual(len(nodes), 2)

    def test_unfair_result_writes_activation_only_on_true_continuation(self):
        machine = self.machine("e8 00 00 00 00 84 c0 74 06 b8 01 00 00 00 c3 31 c0 c3")
        machine.factories[0]["_ArgumentType"] = ""
        binding = dict(
            commandType="app.btable.EmCommonCommand.cCheckUnfairRoutineActive",
            commandIndex=0,
            argumentIndex=None,
            argumentType="",
            argument={},
        )
        with patch.object(machine, "bind", return_value=binding):
            result = machine.build()
        nodes = {node["id"]: node for node in result["nodes"]}
        condition = nodes[result["entry"]]
        from sdk.enemy_logic_exporter.shared.expressions import expression_unknown

        self.assertTrue(expression_unknown(condition["expression"]))
        effect = nodes[condition["true"]]
        self.assertEqual(effect["nativeOffset"], "0x44")
        self.assertIs(effect["nativeValue"], True)
        self.assertTrue(nodes[effect["next"]]["value"])
        self.assertFalse(nodes[condition["false"]]["value"])

    def set_command_return(self, machine, command, return_type):
        from types import SimpleNamespace

        proof = dict(type=command, method="onExecute", address="0x1005")
        machine.command_evidence[command] = proof
        machine.metadata = SimpleNamespace(
            get=lambda _: {
                "methods": {
                    "onExecute": {
                        "function": "0x1005",
                        "returns": {"type": return_type},
                    }
                }
            }
        )

    def test_unknown_void_command_retains_actual_next_without_fixed_action(self):
        machine = self.machine("e8 00 00 00 00 31 c0 c3")
        command = "app.btable.EmCommonCommand.cRequestSelectedAction"
        binding = dict(
            commandType=command, commandIndex=0, argumentIndex=0, argumentType="fixture"
        )
        self.set_command_return(machine, command, "System.Void")
        with patch.object(machine, "bind", return_value=binding):
            result = machine.build()
        nodes = {n["id"]: n for n in result["nodes"]}
        unknown = nodes[result["entry"]]
        self.assertEqual(unknown["kind"], "unknown")
        self.assertEqual(unknown["returnType"], "System.Void")
        self.assertFalse(nodes[unknown["next"]]["value"])
        self.assertNotIn("action", {n["kind"] for n in nodes.values()})

    def test_void_command_does_not_supply_fake_boolean_return(self):
        machine = self.machine("e8 00 00 00 00 84 c0 74 06 b8 01 00 00 00 c3 31 c0 c3")
        command = "fixture.cOpaqueVoid"
        binding = dict(
            commandType=command, commandIndex=0, argumentIndex=0, argumentType="fixture"
        )
        self.set_command_return(machine, command, "System.Void")
        with patch.object(machine, "bind", return_value=binding):
            result = machine.build()
        nodes = {n["id"]: n for n in result["nodes"]}
        self.assertEqual(nodes[nodes[result["entry"]]["next"]]["kind"], "unknown")
        self.assertNotIn("return", {n["kind"] for n in nodes.values()})

    def test_nonvoid_unreviewed_command_cannot_claim_sequential_continuation(self):
        machine = self.machine("e8 00 00 00 00 31 c0 c3")
        command = "fixture.cOpaqueBoolean"
        binding = dict(
            commandType=command, commandIndex=0, argumentIndex=0, argumentType="fixture"
        )
        self.set_command_return(machine, command, "System.Boolean")
        with patch.object(machine, "bind", return_value=binding):
            result = machine.build()
        self.assertEqual(len(result["nodes"]), 1)
        self.assertNotIn("next", result["nodes"][0])

    def test_partial_boundary_binding_remains_unknown(self):
        machine = self.machine("e8 00 00 00 00 31 c0 c3")
        with patch.object(
            machine,
            "bind",
            return_value=dict(
                kind="boundary",
                reason="factory_argument_type_mismatch",
                commandIndex=0,
                argumentIndex=0,
            ),
        ):
            result = machine.build()
        self.assertEqual(result["nodes"][0]["kind"], "unknown")
        self.assertEqual(
            result["nodes"][0]["nativeBinding"]["reason"],
            "factory_argument_type_mismatch",
        )

    def test_no_argument_rule_conflict_remains_unknown(self):
        machine = self.machine("e8 00 00 00 00 31 c0 c3")
        machine.factories[0].update(
            _ArgumentType="",
            _OrderType="app.btable.Em0021_00BTableCommand.cCheckCatchMushroom",
        )
        event = dict(target=("command_method", 0), arguments=[], site="0x1000")
        binding = machine.bind(event)
        self.assertEqual(binding["argumentBindingStatus"], "conflict")
        with patch.object(machine, "bind", return_value=binding):
            result = machine.build()
        self.assertEqual(result["nodes"][0]["kind"], "unknown")

    def test_unreviewed_no_argument_boolean_retains_unknown_and_both_successors(self):
        machine = self.machine("e8 00 00 00 00 84 c0 74 06 b8 01 00 00 00 c3 31 c0 c3")
        machine.factories[0]["_ArgumentType"] = ""
        binding = dict(
            commandType="fixture.cCheckOpaque",
            commandIndex=0,
            argumentIndex=None,
            argumentType="",
            argument={},
        )
        with patch.object(machine, "bind", return_value=binding):
            result = machine.build()
        nodes = {n["id"]: n for n in result["nodes"]}
        condition = nodes[result["entry"]]
        self.assertEqual(condition["expression"]["kind"], "unknown")
        self.assertTrue(nodes[condition["true"]]["value"])
        self.assertFalse(nodes[condition["false"]]["value"])

    def test_inline_position_requires_same_written_continuation_for_all_storage_paths(
        self,
    ):
        # Load ReturnStack and its array, then write root/table/PC and stack count.
        code = "498b8180000000488b5010c742200000000048bb000000000300000048895a24c7401801000000c3"
        machine = self.machine(code)
        self.assertEqual(machine.find_resume(0x1000, machine.initial(0)), (0, 3))
        self.assertEqual(machine.last_resume_trace["checkedStackStorageCases"], 4)
        code = "498b8180000000488b501083781800740c48bb0000000003000000eb0a48bb0000000004000000c742200000000048895a24c7401801000000c3"
        machine = self.machine(code)
        self.assertIsNone(machine.find_resume(0x1000, machine.initial(0)))
