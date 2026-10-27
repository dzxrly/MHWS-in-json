"""Keep transparent native calls and pointer arithmetic out of game semantics."""

import hashlib
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from sdk.enemy_logic_exporter.shared.config import (
    FN_POSITION_STACK_PUSH,
    FN_STACK_COOKIE_CHECK,
    MACHINE_TRANSPARENT_CALLS,
    OPERATOR_EXPORT_END,
    POSITION_ROW,
    POSITION_TABLE,
)
from sdk.enemy_logic_exporter.shared.logic.machine import Machine
from sdk.enemy_logic_exporter.shared.native.bindings import pointer


def machine(hexadecimal="c3", *, address=0x1000):
    native = bytes.fromhex(hexadecimal)
    row = dict(
        type="fixture.Export",
        method="table_fixture",
        address=hex(address),
        end=hex(address + len(native)),
        nativeSha256=hashlib.sha256(native).hexdigest(),
    )
    result = Machine(
        row,
        native,
        None,
        {"_CommandArgArray": [{"fixture.Argument": {"value": 7}}]},
        [{"_OrderType": "fixture.Command", "_ArgumentType": "fixture.Argument"}],
        {},
        {},
    )
    result.registry = SimpleNamespace(
        bind=Mock(return_value=dict(status="verified", summary="fixture command"))
    )
    return result


def event(target):
    return dict(
        site="0x1000",
        target=target,
        direct=isinstance(target, int),
        arguments=[
            pointer("thread"),
            pointer(("command", 0)),
            pointer("command_work"),
            pointer(("argument", 0)),
        ],
    )


class CallClassificationTests(unittest.TestCase):
    def test_transparent_targets_ignore_residual_command_and_argument_aliases(self):
        for target in MACHINE_TRANSPARENT_CALLS:
            with self.subTest(target=hex(target)):
                subject = machine()
                subject.reviewed_effects = True
                subject.command_evidence["fixture.Command"] = dict(address=hex(target))
                self.assertIsNone(subject.bind(event(target)))
                subject.registry.bind.assert_not_called()

    def test_real_execute_wrapper_keeps_its_command_and_argument(self):
        subject = machine()
        subject.reviewed_effects = True
        # An execute wrapper is distinct from its implementation's onExecute.
        subject.command_evidence["fixture.Command"] = dict(address="0x2100")
        bound = subject.bind(event(0x2000))
        self.assertEqual(bound["commandType"], "fixture.Command")
        self.assertEqual(bound["commandIndex"], 0)
        self.assertEqual(bound["argumentIndex"], 0)

    def test_real_virtual_execute_keeps_its_resource_binding(self):
        subject = machine()
        bound = subject.bind(event(("command_method", 0, 0x70)))
        self.assertEqual(bound["commandType"], "fixture.Command")
        self.assertEqual(bound["argumentType"], "fixture.Argument")
        self.assertEqual(bound["argumentIndex"], 0)

    def test_reviewed_direct_implementation_still_binds_without_command_object(self):
        subject = machine()
        subject.reviewed_effects = True
        subject.command_evidence["fixture.Command"] = dict(address="0x2000")
        call = event(0x2000)
        call["arguments"][1] = pointer("command_work")
        bound = subject.bind(call)
        self.assertEqual(bound["commandIndex"], 0)
        self.assertEqual(bound["argumentIndex"], 0)

    def test_cookie_call_preserves_distinct_native_returns_without_command_nodes(self):
        address = FN_STACK_COOKIE_CHECK - 0x1000
        native = b"\xe8" + struct.pack("<i", 0x1000 - 5) + b"\x89\xf8\xc3"
        subject = machine(native.hex(), address=address)
        for value in (0, 1):
            with self.subTest(value=value):
                state = subject.initial(0)
                state["regs"].update(
                    rdi=value,
                    rdx=pointer(("command", 0)),
                    r8=pointer(("argument", 0)),
                )
                state["mem"][("operator", OPERATOR_EXPORT_END, 1)] = value
                key = subject.walk(address, state)
                self.assertEqual(
                    subject.nodes[key],
                    dict(
                        id=f"return-{str(bool(value)).lower()}-end-{value}",
                        kind="return",
                        value=bool(value),
                        tableEnded=bool(value),
                    ),
                )
        self.assertEqual({node["kind"] for node in subject.nodes.values()}, {"return"})
        subject.registry.bind.assert_not_called()

    def test_position_push_keeps_its_saved_continuation_with_command_alias(self):
        address = FN_POSITION_STACK_PUSH - 0x1000
        native = b"\xe8" + struct.pack("<i", 0x1000 - 5) + b"\xb8\x01\x00\x00\x00\xc3"
        subject = machine(native.hex(), address=address)
        state = subject.initial(0)
        state["regs"].update(
            rdx=pointer("return_stack"),
            r8=pointer("stack", -0x40),
            r9=pointer(("command", 0)),
        )
        state["mem"][("stack", -0x40 + POSITION_TABLE, 4)] = 7
        state["mem"][("stack", -0x40 + POSITION_ROW, 4)] = 23
        subject.walk(address, state)
        self.assertEqual(state["saved"], (7, 23))
        self.assertEqual({node["kind"] for node in subject.nodes.values()}, {"return"})
        subject.registry.bind.assert_not_called()


class PointerAdditionTests(unittest.TestCase):
    def step(self, hexadecimal, registers, memory=None):
        subject = machine(hexadecimal)
        state = subject.initial(0)
        state["regs"].update(registers)
        state["mem"].update(memory or {})
        state["flags"] = dict(z=False, s=False, c=True, o=False)
        subject.step(subject.ins[0x1000], state)
        return state

    def test_em0009_native_argument_load_keeps_slot_309(self):
        # Current table_51baca10...: mov eax,0x9c8; add rax,[r14+0x18]; mov r9,[rax].
        subject = machine("b8 c8 09 00 00 49 03 46 18 4c 8b 08")
        state = subject.initial(0)
        state["regs"]["r14"] = pointer("export")
        for instruction in subject.ins.values():
            subject.step(instruction, state)
        self.assertEqual(state["regs"]["rax"], pointer("arguments", 0x9C8))
        self.assertEqual(state["regs"]["r9"], pointer(("argument", 309)))
        self.assertIsNone(state["flags"])

    def test_fixed_register_offset_adds_to_typed_pointer_and_discards_unknown_flags(
        self,
    ):
        state = self.step("48 01 d8", dict(rax=0x20, rbx=pointer("stack", -0x80)))
        self.assertEqual(state["regs"]["rax"], pointer("stack", -0x60))
        self.assertIsNone(state["flags"])

    def test_twos_complement_offset_keeps_64_bit_address_semantics(self):
        state = self.step(
            "48 01 d8", dict(rax=0xFFFFFFFFFFFFFFF8, rbx=pointer("stack", 0x20))
        )
        self.assertEqual(state["regs"]["rax"], pointer("stack", 0x18))
        self.assertIsNone(state["flags"])

    def test_64_bit_memory_destination_adds_the_actual_source_pointer(self):
        state = self.step(
            "48 01 18",
            dict(
                rax=pointer("stack", -0x10),
                rbx=pointer(("table_history", "fixture"), 8),
            ),
            {("stack", -0x10, 8): 24},
        )
        self.assertEqual(
            state["mem"][("stack", -0x10, 8)],
            pointer(("table_history", "fixture"), 32),
        )
        self.assertIsNone(state["flags"])

    def test_64_bit_memory_source_pointer_is_preserved(self):
        state = self.step(
            "48 03 03",
            dict(rax=0x18, rbx=pointer("stack", -0x10)),
            {("stack", -0x10, 8): pointer("operator", 0x40)},
        )
        self.assertEqual(state["regs"]["rax"], pointer("operator", 0x58))
        self.assertIsNone(state["flags"])

    def test_32_bit_add_does_not_preserve_a_truncated_pointer(self):
        state = self.step(
            "03 03",
            dict(rax=0x18, rbx=pointer("stack", -0x10)),
            {("stack", -0x10, 4): pointer("operator", 0x40)},
        )
        self.assertIsNone(state["regs"]["rax"])
        self.assertIsNone(state["flags"])

    def test_subtraction_does_not_exchange_the_integer_and_pointer_operands(self):
        state = self.step("48 29 d8", dict(rax=0x20, rbx=pointer("stack", -0x80)))
        self.assertIsNone(state["regs"]["rax"])
        self.assertIsNone(state["flags"])

    def test_add_rejects_other_symbols_and_incomplete_pointer_values(self):
        for value in (("integer_input", "fixture"), ("pointer", "stack")):
            with self.subTest(value=value):
                state = self.step("48 01 d8", dict(rax=0x20, rbx=value))
                self.assertIsNone(state["regs"]["rax"])
                self.assertIsNone(state["flags"])

    def test_concrete_integer_add_still_computes_carry_and_wraparound(self):
        state = self.step("48 01 d8", dict(rax=0xFFFFFFFFFFFFFFFF, rbx=1))
        self.assertEqual(state["regs"]["rax"], 0)
        self.assertEqual(state["flags"], dict(z=True, s=False, c=True, o=False))


if __name__ == "__main__":
    unittest.main()
