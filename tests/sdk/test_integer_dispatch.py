"""A returned Int32 must remain an integer through the native setcc dispatch."""

import hashlib
from types import SimpleNamespace
from unittest import TestCase

from sdk.enemy_logic_exporter.shared.logic.machine import Machine


class IntegerDispatchTests(TestCase):
    def test_integer_comparison_then_setcc_preserves_both_paths(self):
        # cmp eax,117h; sete al; xor eax,1; ret -- low-byte Boolean aftermath.
        native = bytes.fromhex("3d170100000f94c083f001c3")
        row = dict(
            type="fixture",
            method="dispatch",
            address="0x1000",
            end=hex(0x1000 + len(native)),
            nativeSha256=hashlib.sha256(native).hexdigest(),
        )
        machine = Machine(
            row, native, SimpleNamespace(read=lambda *_: b""), {}, [], {}, {}
        )
        machine.integer_inputs["action_dispatch:damage"] = dict(
            label="受击动作编号", number=True
        )
        state = machine.initial(0)
        state["regs"]["rax"] = ("integer_input", "action_dispatch:damage")
        entry = machine.walk(0x1000, state)
        condition = machine.nodes[entry]
        self.assertEqual(condition["expression"]["right"]["value"], 0x117)
        self.assertEqual(condition["expression"]["operator"], "eq")
        self.assertIs(machine.nodes[condition["true"]]["value"], False)
        self.assertIs(machine.nodes[condition["false"]]["value"], True)
