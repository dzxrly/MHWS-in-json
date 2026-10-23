"""Skill accessor emulation on hand-written machine code; no game files needed."""

import struct
import unittest

from sdk.skill_effect_exporter.native.emulator import STACK, Emulator
from sdk.skill_effect_exporter.native.values import Ptr, V
from sdk.skill_effect_exporter.runtime.heap import Heap, Layouts, SynthObj

BASE = 0x140001000
CONSTANT = 0x140002000


class FakeMetadata:
    def get(self, name):
        return None


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
