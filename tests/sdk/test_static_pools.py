import struct
import unittest
from importlib.util import find_spec
from sdk.enemy_logic_exporter.shared.logic.static_pools import native_initializer_pools


@unittest.skipUnless(find_spec("capstone"), "离线原生测试需要 SDK 的 Capstone 依赖")
class StaticPoolTests(unittest.TestCase):
    def code(self, *, branch=False, clobber=False):
        base = 0x143928000
        code = bytearray()

        def call(target):
            code.extend(b"\xe8" + struct.pack("<i", target - (base + len(code) + 5)))

        code.extend(bytes.fromhex("41 b8 07 00 00 00 41 b9 19 00 00 00"))
        if clobber:
            call(base + 0x900)
        call(0x143928820)
        if branch:
            code.extend(b"\x75\x00")
        code.extend(b"\x48\xb9" + struct.pack("<Q", 0x1547EC3D0))
        call(0x143801F50)
        code.append(0xC3)
        return base, bytes(code)

    def recover(self, **kwargs):
        base, code = self.code(**kwargs)
        return native_initializer_pools(
            code,
            base,
            dict(
                type="Initializer",
                method=".cctor1",
                address=hex(base),
                end=hex(base + len(code)),
                nativeSha256="a" * 64,
            ),
        )

    def test_native_arguments_are_constants_and_do_not_become_probabilities(self):
        pool = self.recover()[0]
        self.assertEqual(pool["entries"][0]["nativeKey"], 7)
        self.assertEqual(pool["entries"][0]["weight"], 25)
        self.assertEqual(pool["address"], "0x1547ec3d0")
        self.assertFalse(pool["keyMeaningReviewed"])
        self.assertFalse(pool["runtimeCandidateFilteringReviewed"])

    def test_unresolved_branch_prevents_pair_grouping(self):
        self.assertEqual(self.recover(branch=True), [])

    def test_clobbered_constructor_arguments_are_not_reused(self):
        self.assertEqual(self.recover(clobber=True), [])

    def packed_code(
        self,
        *,
        missing=False,
        branch=False,
        atomic=False,
        unknown_call=False,
        wrong_type=False,
        vector=False,
        vector_clobber=False,
        tail_release=False,
        interleave=None
    ):
        base = 0x145F89000
        code = bytearray()

        def rip(prefix, target):
            code.extend(
                prefix
                + struct.pack("<i", target - (base + len(code) + len(prefix) + 4))
            )

        def call(target):
            code.extend(b"\xe8" + struct.pack("<i", target - (base + len(code) + 5)))

        rip(bytes.fromhex("48 8b 15"), 0x1547535A8 if wrong_type else 0x1547535A0)
        code.extend(bytes.fromhex("41 b8 02 00 00 00 41 b9 01 00 00 00"))
        call(0x14B030670)
        if vector:
            rip(bytes.fromhex("c5 f8 28 05"), base + 0x1000)
            if vector_clobber:
                code.extend(bytes.fromhex("c5 f8 57 c0"))
            code.extend(bytes.fromhex("c5 f8 11 40 20"))
        else:
            code.extend(bytes.fromhex("48 ba") + struct.pack("<Q", 0x32B33C8F26))
            code.extend(bytes.fromhex("48 89 50 20"))
            if not missing:
                code.extend(bytes.fromhex("48 ba") + struct.pack("<Q", 0x32F0586635))
                code.extend(bytes.fromhex("48 89 50 28"))
        if unknown_call:
            code.extend(bytes.fromhex("48 89 c1"))
            call(base + 0x900)
        if branch:
            code.extend(b"\x75\x00")
        if atomic:
            rip(bytes.fromhex("48 39 05"), 0x1547DBF38)
            if interleave:
                # movabs <reg>, imm64 scheduled between the compare and its je.
                code.extend(bytes.fromhex(interleave) + struct.pack("<Q", 0x23223FD2F7))
            fast_jump = len(code)
            code.extend(b"\x74\x00")
            code.extend(bytes.fromhex("48 89 c7 48 89 c1"))
            call(0x14B007BD0)
            loop = len(code)
            rip(bytes.fromhex("48 8b 0d"), 0x1547DBF38)
            code.extend(bytes.fromhex("48 89 c8"))
            rip(bytes.fromhex("f0 48 0f b1 3d"), 0x1547DBF38)
            code.extend(b"\x75" + struct.pack("b", loop - len(code) - 2))
            code.extend(bytes.fromhex("48 85 c9"))
            null_jump = len(code)
            code.extend(b"\x74\x00")
            if tail_release:
                code.extend(bytes.fromhex("48 83 c4 28 5b"))
                code.extend(
                    b"\xe9" + struct.pack("<i", 0x14B0099E0 - (base + len(code) + 5))
                )
            else:
                call(0x14B0099E0)
            code[fast_jump + 1] = len(code) - fast_jump - 2
            code[null_jump + 1] = len(code) - null_jump - 2
        else:
            rip(bytes.fromhex("48 89 05"), 0x1547DBF38)
        code.append(0xC3)
        return base, bytes(code)

    def packed_recover(self, *, read_memory=None, **kwargs):
        base, code = self.packed_code(**kwargs)
        return native_initializer_pools(
            code,
            base,
            dict(
                type="Initializer",
                method=".cctor",
                address=hex(base),
                end=hex(base + len(code)),
                nativeSha256="a" * 64,
            ),
            read_memory=read_memory,
        )

    def test_packed_arrays_keep_allocation_and_assignment_identity(self):
        for atomic in (False, True):
            pool = self.packed_recover(atomic=atomic)[0]
            self.assertEqual(pool["address"], "0x1547dbf38")
            self.assertEqual(
                [(entry["nativeKey"], entry["weight"]) for entry in pool["entries"]],
                [(0xB33C8F26, 50), (0xF0586635, 50)],
            )
            self.assertEqual(pool["arrayLength"], 2)
            self.assertTrue(all(entry["storeSites"] for entry in pool["entries"]))
            self.assertFalse(pool["keyMeaningReviewed"])

    def test_packed_arrays_reject_incomplete_or_unproved_paths(self):
        for kwargs in [
            dict(missing=True),
            dict(branch=True),
            dict(unknown_call=True),
            dict(wrong_type=True),
        ]:
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.packed_recover(**kwargs), [])

    def test_vector_copy_requires_actual_constant_bytes(self):
        self.assertEqual(self.packed_recover(vector=True), [])
        data = struct.pack("<QQ", 0x32B33C8F26, 0x32F0586635)
        pool = self.packed_recover(
            vector=True,
            read_memory=lambda address, size: (
                data if (address, size) == (0x145F8A000, 16) else b""
            ),
        )[0]
        self.assertEqual([entry["weight"] for entry in pool["entries"]], [50, 50])
        self.assertEqual(pool["constantEvidence"][0]["address"], "0x145f8a000")
        self.assertEqual(
            self.packed_recover(
                vector=True, vector_clobber=True, read_memory=lambda address, size: data
            ),
            [],
        )

    def test_final_atomic_assignment_tail_release_is_proved(self):
        pool = self.packed_recover(atomic=True, tail_release=True)[0]
        self.assertEqual(pool["address"], "0x1547dbf38")
        self.assertEqual(pool["arrayLength"], 2)

    def test_constant_load_between_compare_and_branch_is_carried(self):
        # 48 bb = movabs rbx: runs on both paths and leaves the array intact.
        pool = self.packed_recover(atomic=True, interleave="48 bb")[0]
        self.assertEqual(pool["address"], "0x1547dbf38")
        # 48 b8 = movabs rax would overwrite the compared array register.
        self.assertEqual(self.packed_recover(atomic=True, interleave="48 b8"), [])
