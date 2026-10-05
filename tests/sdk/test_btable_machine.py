"""Check actual x64 returns and navigation-result branches without game files."""

import hashlib
from importlib.util import find_spec
import unittest
from unittest.mock import patch


@unittest.skipUnless(find_spec("capstone"), "离线原生测试需要 SDK 的 Capstone 依赖")
class BTableMachineTests(unittest.TestCase):
    def entry_push(self, *, conflicting_position=False):
        from types import SimpleNamespace
        from sdk.enemy_logic_exporter.shared.logic.machine import Machine
        from sdk.enemy_logic_exporter.shared.native.bindings import pointer

        # Actual reviewed EM0160 capacity branch, fixed POSITION writes and call.
        native = bytes.fromhex(
            "488b9e800000008b4318488b53108b4a1c39c873204863c8488d0c49"
            "44896c8a2049b8000000000d0000004c89448a24ff431ceb724c8d5310"
            "ffc0448d040941b9c7ffff7f4539c8450f42c885c941b804000000"
            "450f45c14139c0440f4ec08b430848bafcffffffffffff7f4883c204"
            "4c09d285c0490f48d24889f9e89d6d0602488b431048634b18488d0c49"
            "44896c882048ba000000000d0000004889548824ff431c8b4318ffc0894318"
            "c686c5000000014889f94c89fa4d89f04989f1e81a210000"
        )
        if conflicting_position:
            native = native.replace(
                bytes.fromhex("48ba000000000d000000"),
                bytes.fromhex("48ba000000000e000000"),
            )
        row = dict(
            type="fixture",
            method="entry",
            address="0x144ef8562",
            end=hex(0x144EF8562 + len(native)),
            nativeSha256=hashlib.sha256(native).hexdigest(),
        )
        helper = b"verified resize fixture"
        machine = Machine(
            row,
            native,
            SimpleNamespace(read=lambda *_: helper),
            {},
            [],
            {0x144EFA740: []},
            {},
        )
        state = machine.initial(0)
        state["regs"].update(
            rsi=pointer("operator"),
            rbx=pointer("return_stack"),
            r13=0,
            rdi=pointer("thread"),
            r15=pointer("export"),
            r14=pointer("command_work"),
        )
        proof = dict(
            profile=machine.registry.data["profile"],
            methods=[row],
            scope="fixture",
            resizeHelper=dict(
                address="0x146f5f380",
                end="0x146f5f58f",
                nativeSha256=hashlib.sha256(helper).hexdigest(),
            ),
        )
        return machine, state, proof

    def test_entry_push_retains_same_call_and_position_for_both_capacity_paths(self):
        from sdk.enemy_logic_exporter.shared.logic.combat_position import (
            recover_entry_push,
        )
        from sdk.enemy_logic_exporter.shared.native.bindings import pointer

        machine, state, proof = self.entry_push()
        with patch(
            "sdk.enemy_logic_exporter.shared.logic.combat_position.evidence",
            return_value=proof,
        ):
            result = recover_entry_push(machine, machine.ins[0x144EF8575], state)
        address, recovered, receipt = result
        self.assertEqual(address, 0x144EF8621)
        self.assertEqual(recovered["saved"], (0, 13))
        self.assertEqual(recovered["regs"]["rdx"], pointer("export"))
        self.assertEqual(receipt["checkedStorageCases"], 4)
        self.assertEqual(receipt["checkedReferenceTagCases"], 2)
        self.assertEqual(len(receipt["positionWriteSites"]), 2)
        self.assertFalse(
            any(key[0].startswith("return_stack") for key in recovered["mem"])
        )

    def test_entry_push_rejects_different_continuation_on_growth_path(self):
        from sdk.enemy_logic_exporter.shared.logic.combat_position import (
            recover_entry_push,
        )

        machine, state, proof = self.entry_push(conflicting_position=True)
        with patch(
            "sdk.enemy_logic_exporter.shared.logic.combat_position.evidence",
            return_value=proof,
        ):
            self.assertIsNone(
                recover_entry_push(machine, machine.ins[0x144EF8575], state)
            )

    def test_entry_push_rejects_unverified_resize_helper(self):
        from sdk.enemy_logic_exporter.shared.logic.combat_position import (
            recover_entry_push,
        )

        machine, state, proof = self.entry_push()
        # The real evidence pins the game's helper bytes; the fixture differs.
        self.assertIsNone(recover_entry_push(machine, machine.ins[0x144EF8575], state))
        proof["resizeHelper"]["nativeSha256"] = "0" * 64
        with patch(
            "sdk.enemy_logic_exporter.shared.logic.combat_position.evidence",
            return_value=proof,
        ):
            self.assertIsNone(
                recover_entry_push(machine, machine.ins[0x144EF8575], state)
            )

    def machine(self, hexadecimal):
        from sdk.enemy_logic_exporter.shared.logic.machine import Machine

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

    def test_same_native_child_site_keeps_each_actual_target_and_saved_resume(self):
        from sdk.enemy_logic_exporter.shared.native.bindings import pointer

        machine = self.machine("e8 fb 0f 00 00 c3")
        machine.targets[0x2000] = [
            dict(row=dict(type="fixture"), tableGuid="child"),
            dict(row=dict(type="other"), tableGuid="other-child"),
        ]
        keys = []
        for pc in (3, 19, 45):
            state = machine.initial(0)
            state["saved"] = (93, pc)
            key = machine.walk(0x1000, state)
            keys.append(key)
            self.assertEqual(machine.nodes[key]["kind"], "call")
            self.assertEqual(machine.nodes[key]["nativeSite"], "0x1000")
        self.assertEqual(len(set(keys)), 3)
        for key, pc in zip(keys, (3, 19, 45)):
            self.assertEqual(
                machine.nodes[key]["nativeContinuation"],
                dict(tableIndex=93, programCounter=pc),
            )
        state = machine.initial(0)
        state["saved"] = (93, 3)
        self.assertEqual(machine.walk(0x1000, state), keys[0])
        state["regs"]["rdx"] = pointer(("import", "other"))
        other_key = machine.walk(0x1000, state)
        self.assertNotEqual(other_key, keys[0])
        self.assertEqual(machine.nodes[other_key]["targetTable"], "other-child")

    def test_dead_context_difference_reuses_the_proven_command_node(self):
        machine = self.machine("e8 00 00 00 00 84 c0 74 06 b8 01 00 00 00 c3 31 c0 c3")
        binding = dict(
            commandType="fixture.cCheckOpaque",
            commandIndex=0,
            argumentIndex=0,
            argumentType="fixture",
        )
        with patch.object(machine, "bind", return_value=binding):
            first = machine.walk(0x1000, machine.initial(0))
            changed = machine.initial(7)
            changed["saved"] = (93, 19)
            merged = machine.walk(0x1000, changed)
        self.assertEqual(machine.nodes[first]["kind"], "condition")
        self.assertEqual(merged, first)

    def test_live_context_difference_stops_without_replacing_first_node(self):
        import copy
        from sdk.enemy_logic_exporter.shared.native.bindings import pointer

        # The saved position differs and the later child call consumes it.
        machine = self.machine("e8 00 00 00 00 48 89 da e8 f3 0f 00 00 c3")
        machine.targets[0x2000] = [dict(row=dict(type="fixture"), tableGuid="child")]
        binding = dict(
            commandType="fixture.cCheckOpaque",
            commandIndex=0,
            argumentIndex=0,
            argumentType="fixture",
        )

        def bind(event):
            return binding if event["site"] == "0x1000" else None

        with patch.object(machine, "bind", side_effect=bind):
            state = machine.initial(0)
            state["regs"]["rbx"] = pointer("export")
            state["saved"] = (93, 3)
            first = machine.walk(0x1000, state)
            changed = copy.deepcopy(state)
            changed["saved"] = (93, 19)
            boundary = machine.walk(0x1000, changed)
        self.assertEqual(machine.nodes[first]["kind"], "condition")
        self.assertEqual(machine.nodes[boundary]["kind"], "unknown")
        self.assertNotIn("next", machine.nodes[boundary])

    def test_shared_call_instruction_keeps_one_node_per_argument_slot(self):
        machine = self.machine("e8 00 00 00 00 84 c0 74 06 b8 01 00 00 00 c3 31 c0 c3")
        keys = []
        for index in (4, 9):
            binding = dict(
                commandType="fixture.cCheckOpaque",
                commandIndex=0,
                argumentIndex=index,
                argumentType="fixture",
            )
            with patch.object(machine, "bind", return_value=binding):
                keys.append(machine.walk(0x1000, machine.initial(0)))
        self.assertEqual(keys, ["0x1000", "0x1000-variant-1"])
        for key, index in zip(keys, (4, 9)):
            self.assertEqual(machine.nodes[key]["argumentIndex"], index)
            self.assertEqual(machine.nodes[key]["nativeSite"], "0x1000")

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
        from sdk.enemy_logic_exporter.shared.logic.expressions import expression_unknown

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
