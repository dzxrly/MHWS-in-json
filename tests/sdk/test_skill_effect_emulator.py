"""Skill accessor emulation on hand-written machine code; no game files needed."""

import struct
import unittest

from sdk.skill_effect_exporter.native.emulator import STACK, Emulator
from sdk.skill_effect_exporter.native.values import Ptr, V, f32_bits
from sdk.skill_effect_exporter.runtime.heap import Heap, JsonObj, Layouts, SynthObj
from sdk.skill_effect_exporter.config import MAX_RECORDED_PATHS
from sdk.skill_effect_exporter.native.scan import indexed_fields
from sdk.skill_effect_exporter.workflow.extract import limit_recorded, merge_paths

BASE = 0x140001000
CONSTANT = 0x140002000
# Writable data with no raw bytes in the file (zero-filled section tail).
ZERO_FILLED = 0x140003000


class FakeMetadata:
    TYPES = {
        "Pair": dict(
            fields={
                "a": dict(type="System.Int32", offset_from_base="0x10"),
                "b": dict(type="System.Int32", offset_from_base="0x14"),
            }
        ),
        "IHolder": dict(
            flags="Public | ClassSemanticsMask | Abstract",
            methods={
                "set_Pair2": dict(id=2, returns=dict(type="System.Void")),
                "get_Pair1": dict(id=1, returns=dict(type="Pair")),
            },
        ),
        "Param": dict(
            fields={
                f"_Wp{n}Add": dict(type="System.Single", offset_from_base=hex(off))
                for n, off in ((11, 0x10), (12, 0x14), (13, 0x18))
            }
            | {"_Other": dict(type="System.Single", offset_from_base="0x1c")}
        ),
    }

    def get(self, name):
        return self.TYPES.get(name)


class FakePE:
    def __init__(self, code, constants=b""):
        self.code, self.constants = code, constants
        self.functions = [(BASE, BASE + len(code))]
        self.starts = [BASE]

    def read(self, address, size):
        if BASE <= address < BASE + len(self.code):
            return self.code[address - BASE : address - BASE + size]
        if CONSTANT <= address < CONSTANT + len(self.constants):
            return self.constants[address - CONSTANT : address - CONSTANT + size]
        return b""

    def read_only(self, address, size):
        return CONSTANT <= address and address + size <= CONSTANT + len(self.constants)

    def contains(self, address):
        return (
            BASE <= address < BASE + len(self.code)
            or CONSTANT <= address < CONSTANT + len(self.constants)
            or ZERO_FILLED <= address < ZERO_FILLED + 0x100
        )


def run(code, setup, returns, constants=b"", usage=None):
    heap = Heap(Layouts(FakeMetadata()), ".")
    emulator = Emulator(FakePE(code, constants), heap, {})
    emulator.usage = usage or {}

    def seed(st):
        st.regs["rsp"] = V(Ptr(STACK, 0))
        st.stack.write(0, 8, V("exit"))
        setup(st, heap)

    return emulator.run(BASE, seed, returns)


# mov eax,[rdx+0x10]; cmp eax,3; jg +3; xor eax,eax; ret; mov eax,1; ret
THRESHOLD = bytes.fromhex("8b4210" "83f803" "7f03" "31c0" "c3" "b801000000" "c3")


class EmulatorTests(unittest.TestCase):
    def test_known_field_takes_one_path(self):
        def setup(st, heap):
            st.regs["rdx"] = V(
                Ptr(SynthObj("t", "obj", {0x10: V(5, frozenset({"obj.level"}))}))
            )

        (result,) = run(THRESHOLD, setup, "System.Int32")
        self.assertEqual(
            (result["status"], result["value"], result["conditions"]), ("ok", 1, [])
        )
        # The returned 1 is an immediate: the branch input is not a data source of the value.
        self.assertEqual(result["prov"], frozenset())

    def test_unknown_field_forks_with_named_conditions(self):
        def setup(st, heap):
            st.regs["rdx"] = V(Ptr(heap.unknown("t", "状态")))

        results = sorted(
            run(THRESHOLD, setup, "System.Int32"), key=lambda r: r["value"]
        )
        self.assertEqual([r["value"] for r in results], [0, 1])
        self.assertEqual(results[1]["conditions"], ["状态+0x10 > 3"])
        self.assertEqual(results[0]["conditions"], ["状态+0x10 <= 3"])

    def test_runtime_writes_are_kept_and_reported(self):
        # mov dword ptr [rdx+0x10],7; mov eax,[rdx+0x10]; ret
        code = bytes.fromhex("c7421007000000" "8b4210" "c3")

        def setup(st, heap):
            st.regs["rdx"] = V(Ptr(heap.unknown("t", "状态")))

        (result,) = run(code, setup, "System.Int32")
        self.assertEqual(result["value"], 7)
        self.assertEqual(
            [(w["target"], w["value"]) for w in result["writes"]], [("状态+0x10", 7)]
        )

    def test_zero_filled_global_is_runtime_state_not_null(self):
        # mov rax, ZERO_FILLED+0x10; mov eax, [rax]; ret
        code = bytes.fromhex("48b8") + struct.pack("<Q", ZERO_FILLED + 0x10)
        code += bytes.fromhex("8b00" "c3")
        (result,) = run(code, lambda st, heap: None, "System.Int32")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["value"].name, f"全局量 {ZERO_FILLED + 0x10:#x}")

    def test_unhandled_operand_widths_end_as_unsupported(self):
        # idiv cx; ret  /  vpshufd ymm0,ymm1,0xe4; ret
        for code in (bytes.fromhex("66f7f9" "c3"), bytes.fromhex("c5fd70c1e4" "c3")):
            (result,) = run(code, lambda st, heap: None, "System.Int32")
            self.assertEqual(result["status"], "unsupported", code.hex())

    def test_later_condition_on_same_flags_keeps_feasible_outcomes(self):
        # mov eax,[rdx+0x10]; cmp eax,0; jl neg; je zero; mov eax,1; ret;
        # neg: mov eax,-1; ret; zero: xor eax,eax; ret
        code = bytes.fromhex(
            "8b4210"
            "83f800"
            "7c08"
            "740c"
            "b801000000"
            "c3"
            "b8ffffffff"
            "c3"
            "31c0"
            "c3"
        )

        def setup(st, heap):
            st.regs["rdx"] = V(Ptr(heap.unknown("t", "状态")))

        results = run(code, setup, "System.Int32")
        by_value = {r["value"]: r["conditions"] for r in results}
        self.assertEqual(sorted(by_value), [-1, 0, 1])
        self.assertEqual(by_value[0], ["状态+0x10 >= 0", "状态+0x10 == 0"])

    def test_overlapping_writes_combine_by_byte(self):
        # mov dword [rdx+0x10],0x100; mov byte [rdx+0x11],2; mov eax,[rdx+0x10]; ret
        code = bytes.fromhex("c7421000010000" "c6421102" "8b4210" "c3")

        def setup(st, heap):
            st.regs["rdx"] = V(Ptr(heap.unknown("t", "状态")))

        (result,) = run(code, setup, "System.Int32")
        self.assertEqual(result["value"], 0x200)
        self.assertEqual(
            [(w["target"], w["value"]) for w in result["writes"]],
            [("状态+0x10", 0x200)],
        )

    def test_merged_writes_of_any_width_are_readable(self):
        # mov dword [rdx],0x11223344; mov dword [rdx+2],0x55667788;
        # mov dword [rdx+4],0x99aabbcc; mov rax,[rdx]; ret
        code = bytes.fromhex(
            "c70244332211" "c7420288776655" "c74204ccbbaa99" "488b02" "c3"
        )

        def setup(st, heap):
            st.regs["rdx"] = V(Ptr(SynthObj("t", "obj", {0: V(0)})))

        (result,) = run(code, setup, "System.UInt64")
        self.assertEqual(result["value"], 0x99AABBCC77883344)

    def test_parity_of_concrete_result(self):
        # mov eax,3; cmp eax,0; setp al; movzx eax,al; ret
        code = bytes.fromhex("b803000000" "83f800" "0f9ac0" "0fb6c0" "c3")
        (result,) = run(code, lambda st, heap: None, "System.Int32")
        self.assertEqual(result["value"], 1)

    def test_vpinsrd_replaces_one_lane(self):
        # mov ecx,7; vpinsrd xmm0,xmm0,ecx,1; vextractps eax,xmm0,1; ret
        code = bytes.fromhex("b907000000" "c4e37922c101" "c4e37917c001" "c3")
        (result,) = run(code, lambda st, heap: None, "System.Int32")
        self.assertEqual(result["value"], 7)

    def test_registers_clobbered_by_opaque_call_stay_unknown(self):
        # call [rax] (not emulated); vmovaps xmm0,xmm1; ret
        code = bytes.fromhex("ff10" "c5f828c1" "c3")

        def setup(st, heap):
            st.regs["rax"] = V(Ptr(heap.unknown("t", "表")))

        (result,) = run(code, setup, "System.Single")
        self.assertEqual(result["status"], "ok")
        self.assertNotIsInstance(result["value"], (int, float))

    def test_imul_sets_overflow(self):
        # mov eax,0x40000000; imul eax,eax,4; seto al; movzx eax,al; ret
        code = bytes.fromhex("b800000040" "6bc004" "0f90c0" "0fb6c0" "c3")
        (result,) = run(code, lambda st, heap: None, "System.Int32")
        self.assertEqual(result["value"], 1)

    def test_legacy_movss_keeps_upper_lanes(self):
        # movss xmm1,xmm0; vextractps eax,xmm1,1; ret
        code = bytes.fromhex("f30f10c8" "c4e37917c801" "c3")

        def setup(st, heap):
            st.vregs[0] = [V(5)] * 8
            st.vregs[1] = [V(10), V(11), V(12), V(13)] + [V(0)] * 4

        (result,) = run(code, setup, "System.Int32")
        self.assertEqual(result["value"], 11)

    def test_float_edge_cases_follow_hardware(self):
        # cvttss2si eax,xmm0; ret: 3e9 does not fit, giving the integer indefinite
        def big(st, heap):
            st.vregs[0] = [V(f32_bits(3e9))] + [V(0)] * 7

        (result,) = run(bytes.fromhex("f30f2cc0" "c3"), big, "System.Int32")
        self.assertEqual(result["value"], -(2**31))

        # vmulss xmm0,xmm0,xmm0; ret: 3e38 squared overflows to infinity
        def huge(st, heap):
            st.vregs[0] = [V(f32_bits(3e38))] + [V(0)] * 7

        (result,) = run(bytes.fromhex("c5fa59c0" "c3"), huge, "System.Single")
        self.assertEqual(result["value"], float("inf"))

    def test_partial_write_keeps_unknown_upper_bits(self):
        # mov al,1; shr eax,8; ret  (eax was never set)
        code = bytes.fromhex("b001" "c1e808" "c3")
        (result,) = run(code, lambda st, heap: None, "System.Int32")
        self.assertNotIsInstance(result["value"], int)

    def test_wide_read_spans_adjacent_fields(self):
        # mov rax,[rdx+0x10]; ret
        def setup(st, heap):
            st.regs["rdx"] = V(Ptr(JsonObj("Pair", {"a": 1, "b": 2}, "pair")))

        (result,) = run(bytes.fromhex("488b4210" "c3"), setup, "System.UInt64")
        self.assertEqual(result["value"], 0x200000001)

    def test_switch_on_unknown_index_takes_every_case(self):
        # mov eax,[rdx+0x10]; cmp eax,2; ja default; lea rcx,[rip+table];
        # movsxd rax,[rcx+rax*4]; add rax,rcx; jmp rax; cases return 10/20/30, default -1
        head = bytes.fromhex("8b4210" "83f802" "7722" "488d0d") + struct.pack(
            "<i", CONSTANT - (BASE + 15)
        )
        code = head + bytes.fromhex("48630481" "4801c8" "ffe0")
        for value in (10, 20, 30, -1):
            code += bytes([0xB8]) + struct.pack("<i", value) + bytes([0xC3])
        table = b"".join(
            struct.pack("<i", BASE + 24 + 6 * k - CONSTANT) for k in range(3)
        )

        def setup(st, heap):
            st.regs["rdx"] = V(Ptr(heap.unknown("t", "状态")))

        results = run(code, setup, "System.Int32", constants=table)
        by_value = {r["value"]: r["conditions"] for r in results}
        self.assertEqual(sorted(by_value), [-1, 10, 20, 30])
        self.assertEqual(by_value[20][-1], "状态+0x10 == 1")

    def test_paths_differing_in_an_irrelevant_branch_merge(self):
        negations = {"a": "!a", "!a": "a", "b": "!b", "!b": "b"}
        paths = [
            dict(status="ok", value=1, conditions=c)
            for c in (["a", "b"], ["a", "!b"], ["!a", "b"])
        ]
        merged = merge_paths(paths, negations)
        self.assertEqual(
            sorted(tuple(p.get("conditions", [])) for p in merged),
            [("!a", "b"), ("a",)],
        )

    def test_inc_of_unknown_still_branches_on_zero(self):
        # mov eax,[rdx+0x10]; mov ecx,[rdx+0x14]; cmp eax,3; inc ecx; jz +6;
        # mov eax,1; ret; xor eax,eax; ret
        code = bytes.fromhex(
            "8b4210" "8b4a14" "83f803" "ffc1" "7406" "b801000000" "c3" "31c0" "c3"
        )

        def setup(st, heap):
            st.regs["rdx"] = V(Ptr(heap.unknown("t", "状态")))

        results = run(code, setup, "System.Int32")
        self.assertEqual(
            sorted((r["status"], r["value"]) for r in results), [("ok", 0), ("ok", 1)]
        )

    def test_recorded_paths_keep_the_fewest_conditions(self):
        paths = [
            dict(status="ok", value=n, conditions=["c"] * n)
            for n in range(MAX_RECORDED_PATHS + 5)
        ]
        kept = limit_recorded(list(reversed(paths)))
        self.assertEqual(len(kept), MAX_RECORDED_PATHS + 1)
        self.assertEqual(kept[0]["value"], 0)
        self.assertEqual(kept[-1]["status"], "truncated")

    def test_dec_keeps_carry(self):
        # mov eax,2; cmp eax,3; dec eax; setb al; movzx eax,al; ret
        code = bytes.fromhex("b802000000" "83f803" "ffc8" "0f92c0" "0fb6c0" "c3")
        (result,) = run(code, lambda st, heap: None, "System.Int32")
        self.assertEqual(result["value"], 1)

    def test_lea_on_integers_is_arithmetic(self):
        # lea rcx,[r8+7]; mov rax,rcx; ret  (getSkillValue builds masks this way)
        code = bytes.fromhex("498d4807" "4889c8" "c3")

        def setup(st, heap):
            st.regs["r8"] = V(0x7FFFFFFFFFFFFFF8)

        (result,) = run(code, setup, "System.UInt64")
        self.assertEqual(result["value"], 0x7FFFFFFFFFFFFFFF)

    def test_slot_scaling_by_read_only_constant(self):
        # vcvtsi2ss xmm0,xmm0,r8d; vmulss xmm0,xmm0,[rip+disp]; ret
        prefix = bytes.fromhex("c4c17a2ac0")
        mulss = bytes.fromhex("c5fa5905")
        after = BASE + len(prefix) + len(mulss) + 4
        code = prefix + mulss + struct.pack("<i", CONSTANT - after) + b"\xc3"

        def setup(st, heap):
            st.regs["r8"] = V(102, frozenset({"SkillData._value[0]"}))

        (result,) = run(code, setup, "System.Single", constants=struct.pack("<f", 0.01))
        self.assertAlmostEqual(result["value"], 1.02, places=6)
        self.assertIn("SkillData._value[0]", result["prov"])
        self.assertTrue(any(p.startswith("EXE 常量") for p in result["prov"]))

    def test_ror_of_known_value(self):
        # mov eax,6; ror eax,1; ret
        code = bytes.fromhex("b806000000" "d1c8" "c3")
        (result,) = run(code, lambda st, heap: None, "System.Int32")
        self.assertEqual(result["value"], 3)

    def test_flags_after_ror_of_unknown_are_unsupported(self):
        # mov eax,[rdx+0x10]; ror eax,1; jc +3; xor eax,eax; ret; mov eax,1; ret
        code = bytes.fromhex("8b4210" "d1c8" "7203" "31c0" "c3" "b801000000" "c3")

        def setup(st, heap):
            st.regs["rdx"] = V(Ptr(heap.unknown("t", "状态")))

        (result,) = run(code, setup, "System.Int32")
        self.assertEqual(result["status"], "unsupported")

    def test_compare_mask_selects_with_blend(self):
        # vxorps xmm2,xmm2,xmm2; vcmpnless xmm2,xmm1,xmm2;
        # vblendvps xmm0,xmm3,xmm1,xmm2; ret  ->  xmm1 > 0 ? xmm1 : xmm3
        code = bytes.fromhex("c5e857d2" "c5f2c2d206" "c4e3614ac120" "c3")
        for given, expected in ((2.0, 2.0), (-1.0, 5.0)):

            def setup(st, heap, given=given):
                st.vregs[1] = [V(f32_bits(given))] + [V(0)] * 7
                st.vregs[3] = [V(f32_bits(5.0))] * 8

            (result,) = run(code, setup, "System.Single")
            self.assertEqual(result["value"], expected)

    def test_compare_mask_on_unknown_forks(self):
        code = bytes.fromhex("c5e857d2" "c5f2c2d206" "c4e3614ac120" "c3")

        def setup(st, heap):
            st.vregs[1] = [heap.unknown("t", "状态").read(0x10, 4, heap)] + [V(0)] * 7
            st.vregs[3] = [V(f32_bits(5.0))] * 8

        results = run(code, setup, "System.Single")
        by_condition = {r["conditions"][0]: r["value"] for r in results}
        self.assertEqual(by_condition["not nle(状态+0x10, 0.0)"], 5.0)
        self.assertEqual(by_condition["nle(状态+0x10, 0.0)"].name, "状态+0x10")

    def test_interface_call_returns_typed_object(self):
        # mov rax,[rdx]; mov rax,[rax-0x20]; call [rax]; mov eax,[rax+0x14]; ret
        code = bytes.fromhex("488b02" "488b40e0" "ff10" "8b4014" "c3")

        def setup(st, heap):
            st.regs["rdx"] = V(Ptr(heap.unknown("IHolder", "holder")))

        (result,) = run(code, setup, "System.Int32")
        self.assertEqual(result["value"].name, "IHolder.get_Pair1().b")

    def test_condition_taken_again_does_not_fork(self):
        # mov eax,[rdx+0x10]; cmp eax,3; jg one; mov ecx,[rdx+0x10]; cmp ecx,3;
        # jg two; xor eax,eax; ret; one: mov eax,1; ret; two: mov eax,2; ret
        code = bytes.fromhex(
            "8b4210"
            "83f803"
            "7f0b"
            "8b4a10"
            "83f903"
            "7f09"
            "31c0"
            "c3"
            "b801000000"
            "c3"
            "b802000000"
            "c3"
        )

        def setup(st, heap):
            st.regs["rdx"] = V(Ptr(heap.unknown("t", "状态")))

        values = sorted(r["value"] for r in run(code, setup, "System.Int32"))
        self.assertEqual(values, [0, 1])

    def test_usage_site_result_is_named(self):
        # call +1 (a ret); ret: the call at BASE is a traced skill read
        code = bytes.fromhex("e801000000" "c3" "c3")
        (result,) = run(
            code, lambda st, heap: None, "System.Int32", usage={BASE: "技能等级〈S〉"}
        )
        self.assertEqual(result["value"].name, "技能等级〈S〉()")

    def test_narrow_focus_takes_the_branch_nearer_the_site(self):
        # mov eax,[rdx+0x10]; cmp eax,3; jg site; nop x3; site: mov eax,1; ret
        code = bytes.fromhex("8b4210" "83f803" "7f03" "909090" "b801000000" "c3")
        site = BASE + 0xB
        reaching = {
            BASE + k: d
            for k, d in ((0, 3), (3, 2), (6, 1), (8, 3), (9, 2), (10, 1), (11, 0))
        }

        def evaluate(narrow):
            heap = Heap(Layouts(FakeMetadata()), ".")
            emulator = Emulator(FakePE(code), heap, {})
            emulator.focus = (BASE, BASE + len(code), reaching, frozenset({site}))
            emulator.narrow = narrow

            def seed(st):
                st.regs["rsp"] = V(Ptr(STACK, 0))
                st.stack.write(0, 8, V("exit"))
                st.regs["rdx"] = V(Ptr(heap.unknown("t", "状态")))

            return emulator.run(BASE, seed, "System.Int32")

        self.assertEqual(len(evaluate(False)), 2)
        (result,) = evaluate(True)
        self.assertEqual(result["conditions"], ["状态+0x10 > 3"])

    def test_loading_an_exception_type_ends_the_path_as_thrown(self):
        # mov rax,[rip+X] (a writable global holding a type descriptor); ret
        code = bytes.fromhex("488b05") + struct.pack("<i", ZERO_FILLED - BASE - 7)
        code += bytes.fromhex("c3")
        heap = Heap(Layouts(FakeMetadata()), ".")
        emulator = Emulator(FakePE(code), heap, {})
        # The zero-filled global reads as descriptor address 0.
        emulator.type_names = {0: "System.ArgumentOutOfRangeException"}

        def seed(st):
            st.regs["rsp"] = V(Ptr(STACK, 0))
            st.stack.write(0, 8, V("exit"))

        (result,) = emulator.run(BASE, seed, "System.Int64")
        self.assertEqual(result["status"], "throws")

    def test_indexed_read_covers_per_weapon_fields(self):
        layouts = Layouts(FakeMetadata())
        layout = layouts.fields("Param")
        self.assertEqual(
            indexed_fields(layout, 0x14, 4, layouts), ["_Wp12Add", "_Wp13Add"]
        )
        self.assertEqual(indexed_fields(layout, 0x14, 0, layouts), ["_Wp12Add"])


if __name__ == "__main__":
    unittest.main()
