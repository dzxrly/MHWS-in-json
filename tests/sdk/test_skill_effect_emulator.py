"""Skill accessor emulation on hand-written machine code; no game files needed."""

from importlib.util import find_spec
import struct
import unittest

if find_spec("capstone"):
    from sdk.skill_effect_exporter.native.emulator import STACK, Emulator
    from sdk.skill_effect_exporter.native.values import Ptr, V, f32_bits
    from sdk.skill_effect_exporter.runtime.heap import Heap, JsonObj, Layouts, SynthObj
    from sdk.skill_effect_exporter.config import MAX_RECORDED_PATHS
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
        )
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


def run(code, setup, returns, constants=b""):
    heap = Heap(Layouts(FakeMetadata()), ".")
    emulator = Emulator(FakePE(code, constants), heap, {})

    def seed(st):
        st.regs["rsp"] = V(Ptr(STACK, 0))
        st.stack.write(0, 8, V("exit"))
        setup(st, heap)

    return emulator.run(BASE, seed, returns)


# mov eax,[rdx+0x10]; cmp eax,3; jg +3; xor eax,eax; ret; mov eax,1; ret
THRESHOLD = bytes.fromhex("8b4210" "83f803" "7f03" "31c0" "c3" "b801000000" "c3")


@unittest.skipUnless(
    find_spec("capstone"), "技能效果模拟器测试需要 SDK 的 Capstone 依赖"
)
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


if __name__ == "__main__":
    unittest.main()
