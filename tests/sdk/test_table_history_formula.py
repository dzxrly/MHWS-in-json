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
    MOD_PREFIX_90,
    MOD_PREFIX_110,
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


def scheduled_fixture(
    base=0x1000,
    *,
    thresholds=(30, 70),
    checked=False,
    register="ecx",
    offset=16,
    tag=1,
    modulus=100,
):
    """Compiler scheduling, multiple thresholds and a real post-write check."""
    old, old_call, state, _ = fixture(base)
    native = bytearray(
        b"".join(x.bytes for x in old.ins.values() if x.address < old_call.address)
    )
    labels, fixups = {}, []

    def label(name):
        labels[name] = base + len(native)

    def branch(opcode, target):
        native.extend(bytes.fromhex(opcode))
        fixups.append((len(native), target))
        native.extend(bytes(4))

    label("rng")
    native.extend(
        bytes.fromhex("ff10")
        + {100: MOD_PREFIX, 90: MOD_PREFIX_90, 110: MOD_PREFIX_110}[modulus]
    )
    label("max")
    if register == "r8d":
        native.extend(
            bytes.fromhex("448b43") + bytes([offset]) + bytes.fromhex("4439c0")
        )
    else:
        native.extend(bytes.fromhex("8b4b") + bytes([offset]) + bytes.fromhex("39c8"))
    branch("0f8d", "threshold0")
    label("min")
    native.extend(bytes.fromhex("3b43") + bytes([offset + 4]))
    branch("0f8e", "threshold0")
    if modulus == 110:
        native.extend(bytes.fromhex("89c8d1e84869c095204f0948c1e8216bc06e29c189c8"))
    elif modulus == 90:
        native.extend(bytes.fromhex("89c8d1e8bab7600bb6480fafd048c1ea256bc25a29c189c8"))
    else:
        native.extend(
            bytes.fromhex("4489c04869c01f85eb5148c1e8256bc0644129c04489c0")
            if register == "r8d"
            else MAX_REMAINDER
        )
    for index, threshold in enumerate(thresholds):
        label("threshold" + str(index))
        native.extend(bytes.fromhex("83f8") + bytes([threshold]))
        # LEA preserves CMP flags and replaces the now-dead Max register.
        native.extend(bytes.fromhex("488d4c2438"))
        branch("0f86", "low" + str(index))

    def write_pair(maximum, minimum):
        native.extend(
            bytes.fromhex("c743") + bytes([offset]) + struct.pack("<I", maximum)
        )
        native.extend(
            bytes.fromhex("c743") + bytes([offset + 4]) + struct.pack("<I", minimum)
        )
        branch("e9", "joint")

    write_pair(modulus + 1, thresholds[-1])
    for index, threshold in enumerate(thresholds):
        label("low" + str(index))
        write_pair(threshold + 1, thresholds[index - 1] if index else 0)
    label("joint")
    # RAX is explicitly overwritten before the real check; it cannot carry the
    # random result into the normal continuation.
    native.extend(bytes.fromhex("b807000000"))
    if checked:
        label("check")
        native.extend(bytes.fromhex("80bfc600000000"))
        branch("0f85", "alternate")
    native.extend(bytes.fromhex("4c89e14889f24c8bc74989f1"))
    branch("e8", 0x3000)
    native.extend(bytes.fromhex("c3"))
    if checked:
        label("alternate")
        native.extend(bytes.fromhex("4c89e14889f24c8bc74989f1"))
        branch("e8", 0x4000)
        native.extend(bytes.fromhex("c3"))
    for at, target in fixups:
        target = labels[target] if isinstance(target, str) else target
        struct.pack_into("<i", native, at, target - base - at - 4)
    native = bytes(native)
    q = Machine(
        dict(
            old.row,
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
    h = TableHistory(
        "fixture.Export",
        0x98,
        0x30,
        0x2000,
        {offset: f"BefoRandomMax_{tag}", offset + 4: f"BefoRandomMin_{tag}"},
    )
    h.complete_discovery = True
    h.read_offsets = set(h.fields)
    h.read_sites = {labels["max"]: {offset}, labels["min"]: {offset + 4}}
    q.table_history = h
    return q, q.ins[labels["rng"]], state, labels


class TableHistoryFormulaTests(unittest.TestCase):
    def test_90_and_110_unsigned_reciprocals_are_exact_on_the_uint32_domain(self):
        for divisor, magic, shift in ((90, 0xB60B60B7, 37), (110, 0x94F2095, 33)):
            # For m=floor(uint32(n)/2), m < 2**31. These inequalities prove
            # floor(m*magic/2**shift)==floor(m/(divisor/2)) for every m:
            # the maximal fractional part plus reciprocal error stays < 1.
            denominator = 1 << shift
            half = divisor // 2
            error = magic * half - denominator
            self.assertGreaterEqual(error, 0)
            self.assertLess((0x80000000 - 1) * error, denominator)
            self.assertLess((0x80000000 - 1) * magic, 1 << 64)
            q, ins, state, labels = scheduled_fixture(
                modulus=divisor, thresholds=(30, 60)
            )
            h = q.table_history
            prepare_history_formula(q, h, enabled=True)
            f = recover_history_formula(q, ins, q.event(ins, state), state)
            expr = f["expression"]
            self.assertEqual(expr["modulus"], divisor)
            for maximum in (-0x80000000, -1, 0, 1, 31, 61, divisor + 1, 0x7FFFFFFF):
                for minimum in (-0x80000000, -1, 0, 30, 60, 0x7FFFFFFF):
                    for draw in (*range(divisor), 0x80000000, 0xFFFFFFFF):
                        selected = q.complete_call(state, q.event(ins, state), draw)
                        selected["mem"][(h.owner, 16, 4)] = maximum & 0xFFFFFFFF
                        selected["mem"][(h.owner, 20, 4)] = minimum & 0xFFFFFFFF
                        address = ins.address + ins.size
                        for _ in range(48):
                            if address == labels["threshold0"]:
                                break
                            address = q.step(q.ins[address], selected)
                        else:
                            self.fail("native modulo region exceeded its bound")
                        facts = {
                            expr["drawKey"]: draw,
                            h.key(16): maximum,
                            h.key(20): minimum,
                        }
                        self.assertEqual(
                            evaluate_interval(expr, facts),
                            selected["regs"]["rax"] <= 30,
                        )

    def test_multiple_thresholds_share_one_draw_and_scheduled_moves_execute(self):
        q, ins, state, _ = scheduled_fixture()
        h = q.table_history
        prepare_history_formula(q, h, enabled=True)
        recovered = recover_history_formula(q, ins, q.event(ins, state), state)
        decisions = recovered["decisions"]
        self.assertEqual([d["expression"]["threshold"] for d in decisions], [30, 70])
        self.assertEqual(len({d["expression"]["drawKey"] for d in decisions}), 1)
        for draw, index in ((0, 0), (30, 0), (31, 1), (70, 1), (71, 2), (99, 2)):
            facts = {
                decisions[0]["expression"]["drawKey"]: draw,
                h.key(16): -1,
                h.key(20): -1,
            }
            decision = 0
            while True:
                d = decisions[decision]
                truth = evaluate_expression(d["expression"], None, facts).truth
                selected = d["true" if truth else "false"]
                if "bucket" in selected:
                    self.assertEqual(selected["bucket"], index)
                    break
                decision = selected["decision"]
        self.assertIsNone(
            evaluate_expression(decisions[1]["expression"], None, {}).truth
        )
        writes = [
            {k: v for w in bucket["writes"] for k, v in w["stateUpdates"].items()}
            for bucket in recovered["buckets"]
        ]
        self.assertEqual(
            writes,
            [
                {h.key(16): 31, h.key(20): 0},
                {h.key(16): 71, h.key(20): 30},
                {h.key(16): 101, h.key(20): 70},
            ],
        )

    def test_machine_emits_ordered_decisions_and_their_own_write_sequences(self):
        q, ins, state, _ = scheduled_fixture()
        prepare_history_formula(q, q.table_history, enabled=True)
        key = q.walk(ins.address, state)
        first = q.nodes[key]
        second = q.nodes[first["false"]]
        self.assertEqual(first["expression"]["threshold"], 30)
        self.assertEqual(second["expression"]["threshold"], 70)
        self.assertEqual(
            first["expression"]["drawKey"], second["expression"]["drawKey"]
        )
        branches = [(first, "true"), (second, "true"), (second, "false")]
        saved = []
        for node, role in branches:
            at, writes = node[role], {}
            while q.nodes[at].get("effect") == "write_table_history":
                writes.update(q.nodes[at]["stateUpdates"])
                at = q.nodes[at]["next"]
            saved.append(writes[q.table_history.key(16)])
        self.assertEqual(saved, [31, 71, 101])
        self.assertEqual(len(first["nativeHistoryFormula"]["continuations"]), 3)

    def test_r8_max_and_post_write_guard_resume_at_actual_check(self):
        q, ins, state, labels = scheduled_fixture(
            thresholds=(50,), checked=True, register="r8d"
        )
        prepare_history_formula(q, q.table_history, enabled=True)
        result = recover_history_formula(q, ins, q.event(ins, state), state)
        for bucket in result["buckets"]:
            self.assertEqual(bucket["continuationKind"], "nativeContinuation")
            self.assertEqual(bucket["address"], labels["check"])
            for flag, expected in ((0, 0x3000), (1, 0x4000)):
                selected = deepcopy(bucket["state"])
                selected["mem"][("operator", 0xC6, 1)] = flag
                at = bucket["address"]
                for _ in range(12):
                    op = q.ins[at]
                    if op.mnemonic == "call":
                        self.assertEqual(q.event(op, selected)["target"], expected)
                        break
                    at = q.step(op, selected)
                else:
                    self.fail("real post-write check did not reach its call")

    def test_local_pairs_keep_json_history_across_another_pair_without_cartesian_mem(
        self,
    ):
        a, ia, sa, _ = scheduled_fixture(thresholds=(50,), tag=1)
        b, ib, sb, _ = scheduled_fixture(0x5000, thresholds=(60,), offset=24, tag=2)
        ha, hb = a.table_history, b.table_history
        manager = TableHistory(
            ha.export_type, 0x98, 0x30, 0x2000, dict(ha.fields, **{})
        )
        manager.fields.update(hb.fields)
        manager.local_pairs = [ha, hb]
        manager.read_sites = dict(ha.read_sites, **{})
        manager.read_sites.update(hb.read_sites)
        manager.complete_discovery = True
        a.ins.update(b.ins)
        a.table_history = manager
        prepare_history_formula(a, manager, enabled=True)
        first = recover_history_formula(a, ia, a.event(ia, sa), sa)
        persistent = {
            k: v
            for w in first["buckets"][0]["writes"]
            for k, v in w["stateUpdates"].items()
        }
        # Both a qword and unrelated history constants must be projected.
        sb["mem"][(manager.owner, 16, 8)] = 51
        second = recover_history_formula(a, ib, a.event(ib, sb), sb)
        persistent.update(
            {
                k: v
                for w in second["buckets"][0]["writes"]
                for k, v in w["stateUpdates"].items()
            }
        )
        self.assertFalse(
            any(k[0] == manager.owner for k in second["entryState"]["mem"])
        )
        expr = first["expression"]
        persistent[expr["drawKey"]] = 25
        # A's saved (51,0) redirects 25 to 51 even after B's independent write.
        self.assertFalse(evaluate_expression(expr, None, persistent).truth)
        persistent[ha.key(16)] = -1
        persistent[ha.key(20)] = -1
        self.assertTrue(evaluate_expression(expr, None, persistent).truth)
        manager.read_sites[0x9000] = {16}
        with self.assertRaises(ValueError):
            prepare_history_formula(a, manager, enabled=True)

    def test_param_escape_does_not_enable_formula_projection(self):
        q, _, _, _ = fixture()
        q.table_history.escaped_sites.add(0x9000)
        with self.assertRaises(ValueError):
            prepare_history_formula(q, q.table_history, enabled=True)
        self.assertFalse(q.table_history.formula_enabled)

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
