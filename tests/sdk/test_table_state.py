"""Previous-draw state is per export and remains explicit across table calls."""

import hashlib
import json
import struct
from types import SimpleNamespace
import unittest

from sdk.enemy_logic_exporter.shared.config import EVIDENCE_DIR
from sdk.enemy_logic_exporter.shared.logic.machine import Machine
from sdk.enemy_logic_exporter.shared.logic.table_state import (
    DICT_TYPE,
    EXPORT_TYPE,
    OPERATOR_TYPE,
    PARAM_TYPE,
    RUNTIME_FIXTURE_ID,
    recover_table_history,
)
from sdk.enemy_logic_exporter.shared.native.bindings import pointer


class TableHistoryTests(unittest.TestCase):
    def machine(
        self,
        *,
        maximum=0x10,
        minimum=0x14,
        partial=False,
        changed_lookup=False,
        unrelated=False
    ):
        base, constructor = 0x143990000, 0x143980000
        owner = "fixture.Export"
        proof = json.loads(
            (EVIDENCE_DIR / "table_state.v1.json").read_text(encoding="utf8")
        )["lookup"]
        lookup = int(proof["address"], 16)
        native = bytearray.fromhex("49 89 d2 49 8b 91 98 00 00 00 45 8b 42 30")
        native.extend(b"\xe8" + struct.pack("<i", lookup - (base + len(native) + 5)))
        native.extend(bytes.fromhex("48 85 c0 74 00"))
        missing = len(native) - 1
        native.extend(bytes.fromhex("48 0f ba f0 3f 4c 8b 20"))
        native.extend(bytes.fromhex("41 8b 44 24") + bytes([maximum]))
        native.extend(bytes.fromhex("41 3b 84 24") + struct.pack("<i", minimum))
        native.extend(bytes.fromhex("74 00"))
        branch = len(native) - 1

        def pair(high, low):
            native.extend(
                bytes.fromhex("41 c7 84 24") + struct.pack("<iI", maximum, high)
            )
            if not partial:
                native.extend(
                    bytes.fromhex("41 c7 84 24") + struct.pack("<iI", minimum, low)
                )
            native.extend(bytes.fromhex("b8 01 00 00 00 c3"))

        pair(71, 40)
        native[branch] = len(native) - branch - 1
        pair(41, 0)
        native[missing] = len(native) - missing - 1
        native.extend(bytes.fromhex("31 c0 c3"))
        native = bytes(native)
        fields = {
            "BefoRandomMax_17": dict(
                type="System.Int32", offset_from_base=hex(maximum)
            ),
            "BefoRandomMin_17": dict(
                type="System.Int32", offset_from_base=hex(minimum)
            ),
            # Another table in this export must not multiply this table's cases.
            "BefoRandomMax_999": dict(type="System.Int32", offset_from_base="0x190"),
            "BefoRandomMin_999": dict(type="System.Int32", offset_from_base="0x194"),
        }
        records = {
            owner
            + ".Param": dict(
                parent=PARAM_TYPE if not unrelated else "System.Object",
                fields=fields,
                methods={".ctor1": dict(function=hex(constructor)[2:])},
            ),
            OPERATOR_TYPE: dict(
                fields={
                    "ExportTableParam": dict(type=DICT_TYPE, offset_from_base="0x98")
                }
            ),
            EXPORT_TYPE: dict(
                fields={
                    "<RuntimeID>k__BackingField": dict(
                        type="System.Int32", offset_from_base="0x30"
                    )
                }
            ),
            DICT_TYPE: dict(
                methods={
                    proof["method"]: dict(
                        function=hex(lookup)[2:],
                        params=[dict(type="System.Int32")],
                        returns=dict(type=PARAM_TYPE, modifier="ByRef"),
                    )
                }
            ),
        }
        metadata = SimpleNamespace(
            get=lambda name: records.get(name),
            fields=lambda name: records.get(name, {}).get("fields", {}),
        )
        # Both stores are explicit in the matched constructor; no class-wide
        # convention supplies -1 for an unrelated or unwritten field.
        ctor = bytes.fromhex("c7 82") + struct.pack("<iI", maximum, 0xFFFFFFFF)
        ctor += (
            bytes.fromhex("c7 82") + struct.pack("<iI", minimum, 0xFFFFFFFF) + b"\xc3"
        )
        helper = bytes.fromhex(proof["nativeBytes"])
        if changed_lookup:
            helper = b"\x90" + helper[1:]
        pe = SimpleNamespace(
            read=lambda address, size: (
                helper[:size]
                if address == lookup
                else ctor[:size] if address == constructor else b""
            )
        )
        row = dict(
            type=owner,
            method="table_fixture1",
            address=hex(base),
            end=hex(base + len(native)),
            nativeSha256=hashlib.sha256(native).hexdigest(),
        )
        machine = Machine(row, native, pe, {}, [], {}, {})
        machine.metadata = metadata
        return machine

    def test_native_pairs_are_predicated_cases_and_not_a_fixed_first_draw(self):
        history = recover_table_history(self.machine())
        cases = history.history_cases()
        self.assertEqual(len(cases), 3)
        values = {tuple(sorted(case["values"].values())) for case in cases}
        self.assertEqual(values, {(0, 41), (40, 71), (0xFFFFFFFF, 0xFFFFFFFF)})
        self.assertEqual(set(history.fields), {0x10, 0x14})
        self.assertTrue(all(len(case["expression"]["items"]) == 2 for case in cases))
        self.assertEqual(
            history.load(pointer(history.owner, 0x10), 4, {"mem": {}}), (False, None)
        )

    def test_nonadjacent_offsets_come_from_this_param_layout(self):
        history = recover_table_history(self.machine(maximum=0x28, minimum=0x84))
        self.assertEqual(set(history.fields), {0x28, 0x84})
        self.assertEqual(len(history.history_cases()), 3)

    def test_incomplete_pair_does_not_invent_the_other_bound(self):
        self.assertIsNone(recover_table_history(self.machine(partial=True)))

    def test_lookup_needs_matching_dictionary_and_runtime_identity(self):
        history = recover_table_history(self.machine())
        dictionary = history.load(pointer("operator", 0x98), 8, {})[1]
        event = dict(
            direct=True,
            target=history.lookup,
            arguments=[pointer("thread"), dictionary, RUNTIME_FIXTURE_ID],
        )
        handled, slot = history.call(event, {})
        self.assertTrue(handled)
        self.assertTrue(history.tagged_reference(slot))
        self.assertEqual(history.load(slot, 8, {})[1], pointer(history.owner))
        event["arguments"][2] += 1
        self.assertFalse(history.call(event, {})[0])
        event["arguments"][2] = RUNTIME_FIXTURE_ID
        event["arguments"][1] = pointer(
            ("table_history_dictionary", "different.Export")
        )
        self.assertFalse(history.call(event, {})[0])

    def test_packed_stores_split_fields_and_partial_stores_invalidate(self):
        history = recover_table_history(self.machine())
        self.assertEqual(
            history.updates(pointer(history.owner, 0x10), 8, (40 << 32) | 71),
            {history.key(0x10): 71, history.key(0x14): 40},
        )
        self.assertEqual(
            history.updates(pointer(history.owner, 0x10), 8, -1),
            {history.key(0x10): -1, history.key(0x14): -1},
        )
        self.assertEqual(
            history.updates(pointer(history.owner, 0x11), 1, 0),
            {history.key(0x10): None},
        )
        self.assertEqual(
            history.updates(pointer(history.owner, 0x10), 4, None),
            {history.key(0x10): None},
        )
        self.assertEqual(
            history.updates(pointer(("table_history", "other.Export"), 0x10), 8, 0), {}
        )

    def test_changed_lookup_bytes_fail_instead_of_reusing_old_meaning(self):
        with self.assertRaisesRegex(ValueError, "字典查找原生字节变化"):
            recover_table_history(self.machine(changed_lookup=True))

    def test_unrelated_param_parent_keeps_native_boundary(self):
        self.assertIsNone(recover_table_history(self.machine(unrelated=True)))

    def test_bulk_initialization_requires_the_actual_memset_import(self):
        for import_name, case_count in ((b"memset", 3), (b"memcpy", 2)):
            with self.subTest(import_name=import_name):
                machine = self.machine(maximum=0x28, minimum=0x84)
                original_read = machine.pe.read
                base, constructor, thunk = 0x140000000, 0x143980000, 0x143970000
                header = bytearray(512)
                struct.pack_into("<I", header, 0x3C, 0x80)
                struct.pack_into("<II", header, 0x80 + 24 + 120, 0x1000, 40)
                fill = bytes.fromhex("48 8d 4a 10 41 b8 40 01 00 00 b2 ff")
                fill += b"\xe9" + struct.pack(
                    "<i", thunk - (constructor + len(fill) + 5)
                )
                jump = bytes.fromhex("ff 25") + struct.pack(
                    "<i", base + 0x3000 - (thunk + 6)
                )
                memory = {
                    constructor: fill,
                    thunk: jump,
                    base + 0x1000: struct.pack("<IIIII", 0x2000, 0, 0, 0x5000, 0x3000),
                    base + 0x1014: bytes(20),
                    base + 0x2000: struct.pack("<Q", 0x4000),
                    base + 0x2008: bytes(8),
                    base + 0x4002: import_name + b"\0",
                }
                machine.pe.base, machine.pe.data = base, header
                machine.pe.read = lambda address, size: (
                    memory[address][:size]
                    if address in memory
                    else original_read(address, size)
                )
                history = recover_table_history(machine)
                self.assertEqual(len(history.history_cases()), case_count)


if __name__ == "__main__":
    unittest.main()
