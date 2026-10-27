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
    TableHistory,
    recover_table_history,
)
from sdk.enemy_logic_exporter.shared.native.bindings import pointer


class TableHistoryTests(unittest.TestCase):
    def test_ordinary_random_draw_does_not_use_local_history_state(self):
        native = bytes.fromhex("498b5010488b02488b40e8ff1083e001c3")
        row = dict(
            type="fixture",
            method="table",
            address="0x1000",
            end=hex(0x1000 + len(native)),
            nativeSha256=hashlib.sha256(native).hexdigest(),
        )
        machine = Machine(row, native, None, {}, [], {}, {})
        machine.random_modulus = 2
        result = machine.build()
        self.assertEqual(
            {node["value"] for node in result["nodes"] if node["kind"] == "return"},
            {False, True},
        )
        self.assertFalse(any(node.get("historyCaseLocal") for node in result["nodes"]))

    def test_multiple_intervals_are_selected_only_when_their_read_is_reached(self):
        # The second read is reachable only when the first saved Max is 41.
        draw = bytes.fromhex("498b542410488b02488b40e8ff10")
        native = bytearray.fromhex("4889d34d89c4")
        native.extend(draw)
        native.extend(bytes.fromhex("8b4b1083f9297500"))
        jump = len(native) - 1
        native.extend(bytes.fromhex("48b9470000002800000048894b10"))
        native.extend(draw)
        native.extend(bytes.fromhex("8b4b2083f91f0f94c0c3"))
        native[jump] = len(native) - jump - 1
        native.extend(bytes.fromhex("31c0c3"))
        native = bytes(native)
        row = dict(
            type="fixture",
            method="table",
            address="0x1000",
            end=hex(0x1000 + len(native)),
            nativeSha256=hashlib.sha256(native).hexdigest(),
        )
        machine = Machine(row, native, None, {}, [], {}, {})
        fields = {
            16: "BefoRandomMax_1",
            20: "BefoRandomMin_1",
            32: "BefoRandomMax_2",
            36: "BefoRandomMin_2",
        }
        history = TableHistory("fixture", 0x98, 0x30, 0x2000, fields)
        for offsets, values in [
            ((16, 20), [(-1, -1), (41, 0), (71, 40)]),
            ((32, 36), [(-1, -1), (31, 0), (51, 30)]),
        ]:
            pair = TableHistory(
                "fixture", 0x98, 0x30, 0x2000, {o: fields[o] for o in offsets}
            )
            pair.read_offsets = set(offsets)
            pair.candidates = {tuple(zip(offsets, case)): {"0x2000"} for case in values}
            history.local_pairs.append(pair)
        machine.table_history = history
        initial = machine.initial

        def state(pc):
            result = initial(pc)
            result["regs"]["rdx"] = pointer(history.owner)
            return result

        machine.initial = state
        result = machine.build()
        nodes = {n["id"]: n for n in result["nodes"]}
        head = nodes[result["entry"]]
        self.assertEqual(
            set(head["inputDefinitions"]), {history.key(16), history.key(20)}
        )
        settled = nodes[head["true"]]
        while settled["kind"] == "mutation":
            settled = nodes[settled["next"]]
        self.assertFalse(settled["value"])
        self.assertFalse(any(n["id"].startswith("history-pc-") for n in nodes.values()))
        second = [
            n
            for n in nodes.values()
            if n.get("historyCaseLocal") and history.key(32) in n["inputDefinitions"]
        ]
        self.assertEqual(len(second), 3)
        self.assertTrue(
            all(
                set(n["inputDefinitions"]) == {history.key(32), history.key(36)}
                for n in second
            )
        )
        writes = [
            n["stateUpdates"]
            for n in nodes.values()
            if n.get("effect") == "write_table_history"
        ]
        self.assertIn({history.key(16): 71, history.key(20): 40}, writes)
        # Replaying the second pair must not carry first-pair case facts into
        # every branch. Its earlier native writes remain semantic updates.
        machine.nodes, machine.event_contexts = {}, {}
        snapshots = []
        machine.walk = lambda address, selected: snapshots.append(selected) or "after"
        state = machine.initial(0)
        state["mem"].update({(history.owner, 16, 4): 71, (history.owner, 20, 4): 40})
        read = next(
            ins
            for ins in machine.ins.values()
            if ins.mnemonic == "mov"
            and len(ins.operands) == 2
            and ins.operands[1].type == 3
            and ins.operands[1].mem.disp == 32
        )
        machine.history_read(read, state, pair_hint=history.local_pairs[1])
        self.assertEqual(len(snapshots), 3)
        self.assertTrue(
            all(
                (history.owner, 16, 4) not in selected["mem"]
                and (history.owner, 20, 4) not in selected["mem"]
                for selected in snapshots
            )
        )
        # Without a verified draw prefix, a bare private read stays a boundary.
        machine.nodes, machine.event_contexts = {}, {}
        state["regs"]["rbx"] = pointer(history.owner)
        key = machine.history_read(read, state)
        self.assertEqual(machine.nodes[key]["kind"], "unknown")

    def test_short_random_regions_merge_only_equal_call_arguments_and_writes(self):
        def fixture(
            *, distinct_arguments=False, unsafe_write=False, noncontiguous=False
        ):
            native = bytearray.fromhex("e8fb0f000083e00383f8017600")
            if noncontiguous:
                native[7], native[10] = 1, 0
            jump = len(native) - 1
            native.extend(bytes.fromhex("48b9050000000100000048894b10eb00"))
            following = len(native) - 1
            native[jump] = len(native) - jump - 1
            native.extend(bytes.fromhex("48b9020000000000000048894b10"))
            native[following] = len(native) - following - 1
            if distinct_arguments:
                native.extend(bytes.fromhex("4189c0"))
            if unsafe_write:
                native.extend(bytes.fromhex("8902"))
            site = 0x1000 + len(native)
            native.extend(b"\xe8" + struct.pack("<i", 0x2000 - site - 5) + b"\xc3")
            native = bytes(native)
            q = Machine(
                dict(
                    type="fixture",
                    method="table",
                    address="0x1000",
                    end=hex(0x1000 + len(native)),
                    nativeSha256=hashlib.sha256(native).hexdigest(),
                ),
                native,
                None,
                {},
                [],
                {},
                {},
            )
            h = TableHistory(
                "fixture",
                0x98,
                0x30,
                0x2000,
                {16: "BefoRandomMax_1", 20: "BefoRandomMin_1"},
            )
            q.table_history, q.random_modulus = h, 4
            state = q.initial(0)
            state["regs"].update(rbx=pointer(h.owner), rdx=pointer("outside"))
            calls = []
            q.walk = lambda address, current: calls.append(
                (address, current)
            ) or "call-" + str(len(calls))
            result = q.random_history_choices(
                q.ins[0x1000], dict(arguments=[pointer("thread")]), state, "random"
            )
            return q, result, calls

        q, choices, calls = fixture()
        self.assertEqual(len(calls), 2)
        self.assertEqual(choices[0], choices[1])
        self.assertEqual(choices[2], choices[3])
        self.assertNotEqual(choices[0], choices[2])
        self.assertEqual(
            {
                tuple(node["nativeRandomRegionProof"]["remainders"])
                for node in q.nodes.values()
            },
            {(0, 1), (2, 3)},
        )
        _, choices, calls = fixture(distinct_arguments=True)
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(set(choices)), 4)
        q, choices, calls = fixture(noncontiguous=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(choices[0], choices[2])
        self.assertEqual(choices[1], choices[3])
        self.assertNotEqual(choices[0], choices[1])
        self.assertEqual(
            {
                tuple(node["nativeRandomRegionProof"]["remainders"])
                for node in q.nodes.values()
            },
            {(0, 2), (1, 3)},
        )
        _, choices, calls = fixture(unsafe_write=True)
        self.assertIsNone(choices)
        self.assertEqual(calls, [])

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

    def test_discovery_crosses_only_explicit_variable_effects(self):
        from unittest.mock import patch
        from sdk.enemy_logic_exporter.shared.logic.table_state import _discover

        original = self.machine()
        native = b"".join(ins.bytes for ins in original.ins.values())
        load = next(
            ins
            for ins in original.ins.values()
            if ins.mnemonic == "mov" and ins.op_str == "r12, qword ptr [rax]"
        )
        index = load.address + load.size - int(original.row["address"], 16)
        extra = b"\xe8" + struct.pack("<i", 0x900 - index - 5)
        native = native[:index] + extra + native[index:]
        row = dict(
            original.row,
            nativeSha256=hashlib.sha256(native).hexdigest(),
            end=hex(int(original.row["address"], 16) + len(native)),
        )
        for effect, expected in [
            ("set_float_value", {16, 20}),
            ("request_dynamic_action", set()),
            ("read_action_dispatch", set()),
        ]:
            q = Machine(row, native, original.pe, {}, [], {}, {})
            q.metadata = original.metadata
            h = TableHistory(
                "fixture.Export",
                0x98,
                0x30,
                int(
                    next(iter(q.metadata.get(DICT_TYPE)["methods"].values()))[
                        "function"
                    ],
                    16,
                ),
                {16: "BefoRandomMax_17", 20: "BefoRandomMin_17"},
            )
            with patch.object(
                Machine, "bind", return_value=dict(commandType="fixture")
            ), patch(
                "sdk.enemy_logic_exporter.shared.logic.command_effects.reviewed_command_effect",
                return_value=dict(effect=effect),
            ):
                _discover(q, h, reviewed_calls=True)
            self.assertEqual(h.read_offsets, expected)

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

    def test_vector_all_ones_constructor_supplies_only_covered_fields(self):
        from sdk.enemy_logic_exporter.shared.logic.table_state import _constructor_case

        machine = self.machine(maximum=0x28, minimum=0x84)
        original = machine.pe.read
        constructor = bytes.fromhex(
            "c5f857c0c5fcc2c00fc5fc114268c5fc114250c5fc114230c5fc114210c5f877c3"
        )
        machine.pe.read = lambda address, size: (
            constructor[:size] if address == 0x143980000 else original(address, size)
        )
        history = recover_table_history(machine)
        self.assertEqual(len(history.history_cases()), 2)
        _constructor_case(machine, history, allow_avx_fill=True)
        self.assertEqual(len(history.history_cases()), 3)
        # Without the final block covering +0x84, the initializer cannot assert
        # a complete pair even though the other field is initialized to -1.
        partial = constructor.replace(
            bytes.fromhex("c5fc114268"), bytes.fromhex("c5fc114210")
        )
        machine.pe.read = lambda address, size: (
            partial[:size] if address == 0x143980000 else original(address, size)
        )
        history = recover_table_history(machine)
        _constructor_case(machine, history, allow_avx_fill=True)
        self.assertEqual(len(history.history_cases()), 2)


if __name__ == "__main__":
    unittest.main()
