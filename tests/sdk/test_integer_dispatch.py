"""A returned Int32 must remain an integer through the native setcc dispatch."""

import hashlib
import uuid
from types import SimpleNamespace
from unittest import TestCase

from sdk.enemy_logic_exporter.shared.logic.machine import Machine
from sdk.enemy_logic_exporter.shared.native.bindings import pointer, add


class IntegerDispatchTests(TestCase):
    def test_inlined_bool_argument_preserves_guid_byte_order_and_boolean_value(self):
        native = b"\xc3"
        row = dict(
            type="fixture",
            method="inline_bool",
            address="0x1000",
            end="0x1001",
            nativeSha256=hashlib.sha256(native).hexdigest(),
        )
        guid = "12345678-9abc-def0-1234-56789abcdef0"
        body = {
            "_CommandArgArray": [
                {
                    "ace.btable.cSetBoolValueArg": {
                        "_TargetVariableIndex": {
                            "ace.btable.cEditFieldDropBox`1<System.Guid>": guid
                        },
                        "_Value": {"ace.btable.cEditFieldBool": False},
                    }
                }
            ]
        }
        machine = Machine(
            row, native, SimpleNamespace(read=lambda *_: b""), body, [], {}, {}
        )
        machine.reviewed_effects = True
        machine.metadata = SimpleNamespace(
            fields=lambda name: {
                "_Value": dict(
                    type="System.Guid" if "System.Guid" in name else "System.Boolean",
                    offset_from_base="0x10",
                )
            }
        )
        state = machine.initial(0)
        field = machine.load(pointer(("argument", 0), 0x18), 8, state)
        raw = bytes(machine.load(add(field, 0x10 + i), 1, state) for i in range(16))
        self.assertEqual(str(uuid.UUID(bytes_le=raw)), guid)
        boolean = machine.load(pointer(("argument", 0), 0x20), 8, state)
        self.assertEqual(machine.load(add(boolean, 0x10), 1, state), 0)
        machine.body["_CommandArgArray"][0] = {"fixture.OtherArgument": {}}
        self.assertIsNone(machine.load(pointer(("argument", 0), 0x18), 8, state))

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
