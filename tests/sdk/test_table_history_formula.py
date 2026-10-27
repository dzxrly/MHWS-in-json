"""Native interval formulas keep the whole Int32 domain and real fixed writes."""

from copy import deepcopy
import hashlib
import struct
import unittest

from sdk.enemy_logic_exporter.shared.logic.expressions import (
    evaluate_expression,
    expression_unknown,
    validate_expression,
)
from sdk.enemy_logic_exporter.shared.logic.machine import Machine
from sdk.enemy_logic_exporter.shared.logic.table_state import TableHistory
from sdk.enemy_logic_exporter.shared.logic.table_history_formula import (
    MAX_REMAINDER,
    MOD_PREFIX,
    evaluate_interval,
    prepare_history_formula,
    recover_history_formula,
)


def fixture(base=0x1000, *, dirty_branch=False):
    native = bytearray.fromhex(
        "53565741544c89c64889d34c89cf4989cc488b9798000000448b4330"
    )
    site = base + len(native)
    native.extend(b"\xe8" + struct.pack("<i", 0x2000 - site - 5))
    native.extend(bytes.fromhex("480fbaf03f488b18488b5610488b02488b40e84c89e1"))
    random_site = base + len(native)
    native.extend(bytes.fromhex("ff10") + MOD_PREFIX)
    maximum = base + len(native)
    native.extend(bytes.fromhex("8b4b1039c80f8d") + bytes(4))
    upper = len(native) - 4
    minimum = base + len(native)
    native.extend(bytes.fromhex("3b43140f8e") + bytes(4) + MAX_REMAINDER)
    lower = minimum - base + 5
    threshold = base + len(native)
    native.extend(bytes.fromhex("83f8320f86") + bytes(4))
    choose = len(native) - 4
    native.extend(bytes.fromhex("c7431065000000c7431432000000e9") + bytes(4))
    join = len(native) - 4
    low = base + len(native)
    if dirty_branch:
        native.extend(
            bytes.fromhex("4189c0")
        )  # old effective value becomes an argument
    native.extend(bytes.fromhex("c7431033000000c7431400000000"))
    joint = base + len(native)
    native.extend(bytes.fromhex("4c89e14889f24c8bc74989f1"))
    call = base + len(native)
    native.extend(b"\xe8" + struct.pack("<i", 0x3000 - call - 5))
    native.extend(bytes.fromhex("31c0415c5f5e5bc3"))
    for offset, target in (
        (upper, threshold),
        (lower, threshold),
        (choose, low),
        (join, joint),
    ):
        struct.pack_into("<i", native, offset, target - base - offset - 4)
    native = bytes(native)
    machine = Machine(
        dict(
            type="fixture.Export",
            method="table_fixture",
            address=hex(base),
            end=hex(base + len(native)),
            nativeSha256=hashlib.sha256(native).hexdigest(),
        ),
        native,
        None,
        {},
        [],
        {},
        {},
    )
    history = TableHistory(
        "fixture.Export",
        0x98,
        0x30,
        0x2000,
        {16: "BefoRandomMax_1", 20: "BefoRandomMin_1"},
    )
    history.complete_discovery = True
    history.read_offsets = {16, 20}
    history.read_sites = {maximum: {16}, minimum: {20}}
    history.candidates = {
        ((16, 51), (20, 0)): {"0x3000"},
        ((16, 101), (20, 50)): {"0x3000"},
    }
    machine.table_history = history
    state, address = machine.initial(0), base
    while address != random_site:
        ins = machine.ins[address]
        if ins.mnemonic == "call":
            event = machine.event(ins, state)
            handled, value = history.call(event, state)
            assert handled
            state = machine.complete_call(state, event, None)
            state["regs"]["rax"] = value
            address += ins.size
        else:
            address = machine.step(ins, state)
    return machine, machine.ins[random_site], state, threshold


class TableHistoryFormulaTests(unittest.TestCase):
    def test_preparation_relocates_and_covers_every_actual_private_read(self):
        for base in (0x1000, 0x1100):
            q, ins, state, _ = fixture(base)
            h = q.table_history
            self.assertEqual(len(h.history_cases()), 2)
            self.assertTrue(prepare_history_formula(q, h, enabled=True))
            self.assertEqual(h.history_cases(), [])
            self.assertEqual(h.input_definitions()[h.key(16)]["min"], -0x80000000)
            before = deepcopy(state)
            recovered = recover_history_formula(q, ins, q.event(ins, state), state)
            self.assertEqual(state, before)
            self.assertEqual(recovered["expression"]["kind"], "table_history_interval")
            self.assertEqual({b["truth"] for b in recovered["buckets"]}, {True, False})
            values = {
                b["truth"]: {
                    k: v for w in b["writes"] for k, v in w["stateUpdates"].items()
                }
                for b in recovered["buckets"]
            }
            self.assertEqual(values[True], {h.key(16): 51, h.key(20): 0})
            self.assertEqual(values[False], {h.key(16): 101, h.key(20): 50})
            for bucket in recovered["buckets"]:
                self.assertEqual(q.ins[bucket["address"]].mnemonic, "call")
                self.assertEqual(len(bucket["writes"]), 2)

    def test_changed_signed_guard_modulus_or_uncovered_read_rejects_recipe(self):
        for change in ("signed", "modulus", "uncovered"):
            q, ins, _, _ = fixture()
            if change == "uncovered":
                q.table_history.read_sites[0x9000] = {16}
            else:
                replacement = (
                    bytes.fromhex("0f83")
                    if change == "signed"
                    else bytes.fromhex("48c1e924")
                )
                old = (
                    bytes.fromhex("0f8d")
                    if change == "signed"
                    else bytes.fromhex("48c1e925")
                )
                raw = b"".join(x.bytes for x in q.ins.values()).replace(
                    old, replacement, 1
                )
                row = dict(q.row, nativeSha256=hashlib.sha256(raw).hexdigest())
                changed = Machine(row, raw, None, {}, [], {}, {})
                changed.table_history = q.table_history
                q = changed
            with self.assertRaises(ValueError):
                prepare_history_formula(q, q.table_history, enabled=True)
            self.assertFalse(q.table_history.formula_enabled)

    def test_effective_value_live_in_branch_is_not_replaced_by_representative(self):
        q, ins, state, _ = fixture(dirty_branch=True)
        prepare_history_formula(q, q.table_history, enabled=True)
        with self.assertRaisesRegex(ValueError, "still live"):
            recover_history_formula(q, ins, q.event(ins, state), state)

    def test_sdk_formula_matches_native_instruction_edges_and_unknown_is_contextual(
        self,
    ):
        q, ins, state, threshold = fixture()
        h = q.table_history
        prepare_history_formula(q, h, enabled=True)
        expr = recover_history_formula(q, ins, q.event(ins, state), state)["expression"]
        validate_expression(expr)
        self.assertFalse(expression_unknown(expr))
        for maximum in (-2147483648, -1, 0, 1, 51, 101, 2147483647):
            for minimum in (-2147483648, -1, 0, 50, 2147483647):
                for draw in (*range(100), 0xFFFFFFFF, 0x80000000):
                    selected = q.complete_call(state, q.event(ins, state), draw)
                    selected["mem"][(h.owner, 16, 4)] = maximum & 0xFFFFFFFF
                    selected["mem"][(h.owner, 20, 4)] = minimum & 0xFFFFFFFF
                    address = ins.address + ins.size
                    for _ in range(40):
                        if address == threshold:
                            break
                        address = q.step(q.ins[address], selected)
                    else:
                        self.fail("native region did not reach its threshold")
                    facts = {
                        expr["drawKey"]: draw,
                        expr["maxKey"]: maximum,
                        expr["minKey"]: minimum,
                    }
                    self.assertEqual(
                        evaluate_expression(expr, None, facts).truth,
                        (selected["regs"]["rax"] & 0xFFFFFFFF) <= 50,
                    )
        self.assertIsNone(evaluate_expression(expr, None, {}).truth)
        for value in (None, True, 1.5, "51", 1 << 64, -2147483649):
            self.assertIsNone(
                evaluate_interval(
                    expr, {expr["drawKey"]: 0, expr["maxKey"]: value, expr["minKey"]: 0}
                )
            )
        self.assertTrue(
            evaluate_interval(
                expr, {expr["drawKey"]: 75, expr["maxKey"]: 200, expr["minKey"]: 60}
            )
        )
        self.assertEqual(
            h.candidates,
            {((16, 51), (20, 0)): {"0x3000"}, ((16, 101), (20, 50)): {"0x3000"}},
        )


if __name__ == "__main__":
    unittest.main()
