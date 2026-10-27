"""Memory-dump section names and unwind-less neighbors are not identities."""

from pathlib import Path
import struct
import tempfile
import unittest

from sdk.enemy_logic_exporter.shared.config import TMP_DIR
from sdk.enemy_logic_exporter.shared.native.pe import PE
from sdk.enemy_logic_exporter.shared.native.symbols import (
    masked_pattern,
    normalized_digest,
)
from sdk.enemy_logic_exporter.shared.workflow.version_update import _function_end


class PELayoutTests(unittest.TestCase):
    def setUp(self):
        folder = TMP_DIR / "action-map-migration"
        folder.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=folder)
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "sample.exe"
        self.base = 0x140000000
        self.sequence = 0

    def image(
        self,
        code=b"\x31\xc0\xc3",
        *,
        names=None,
        directories=None,
        constant_flags=0xC0000040,
        unwind=False,
    ):
        data = bytearray(0x2900)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 0x3C, 0x80)
        data[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<H", data, 0x86, 4)
        struct.pack_into("<H", data, 0x94, 0xF0)
        opt = 0x98
        struct.pack_into("<H", data, opt, 0x20B)
        struct.pack_into("<Q", data, opt + 24, self.base)
        struct.pack_into("<I", data, opt + 108, 16)
        entries = {9: (0x2100, 0x28), 10: (0x2200, 0x140), 13: (0x2400, 0x40)}
        entries.update(directories or {})
        entries[3] = (0x4000, 12 if unwind else 0)
        for index, (rva, size) in entries.items():
            struct.pack_into("<II", data, opt + 112 + index * 8, rva, size)
        names = names or [b".code", b".renamed", b".mutable", b".unwind"]
        for index, ((rva, size, raw, flags), name) in enumerate(
            zip(
                [
                    (0x1000, 0x400, 0x400, 0x60000020),
                    (0x2000, 0x1000, 0x800, constant_flags),
                    (0x3000, 0x1000, 0x1800, 0xC0000040),
                    (0x4000, 0x100, 0x2800, 0x40000040),
                ],
                names,
            )
        ):
            offset = opt + 0xF0 + index * 40
            data[offset : offset + 8] = name.ljust(8, b"\0")
            struct.pack_into("<IIII", data, offset + 8, size, rva, size, raw)
            struct.pack_into("<I", data, offset + 36, flags)
        data[0x400 : 0x400 + len(code)] = code
        if unwind:
            struct.pack_into("<III", data, 0x2800, 0x1000, 0x1080, 0)
        self.sequence += 1
        path = self.path.with_name(f"sample-{self.sequence}.exe")
        path.write_bytes(data)
        result = PE(path)
        self.addCleanup(result.close)
        result.method_starts = [self.base + 0x1000, self.base + 0x1100]
        return result

    def test_three_directories_locate_constants_after_section_renaming(self):
        pe = self.image()
        self.assertTrue(pe.read_only(self.base + 0x2000, 4))
        self.assertFalse(pe.read_only(self.base + 0x3000, 4))
        self.assertTrue(pe.read_only(self.base + 0x4000, 4))
        self.assertFalse(pe.read_only(self.base + 0x2FFE, 4))

    def test_old_section_name_alone_does_not_authorize_mutable_memory(self):
        pe = self.image(
            names=[b".code", b".sdata", b".mutable", b".unwind"],
            directories={13: (0, 0)},
        )
        self.assertFalse(pe.read_only(self.base + 0x2100, 4))

    def test_directory_ranges_must_be_complete_and_in_same_nonexecuting_section(self):
        for changes in [
            dict(directories={13: (0x3100, 0x40)}),
            dict(directories={13: (0x2FF0, 0x40)}),
            dict(constant_flags=0xE0000040),
        ]:
            with self.subTest(changes=changes):
                pe = self.image(**changes)
                self.assertFalse(pe.read_only(self.base + 0x2100, 4))

    def test_closed_leaf_stops_before_unreachable_thunk_and_data(self):
        pe = self.image(
            bytes.fromhex("31c0c3cccccccccccccccccccccccce9") + b"\x90" * 80
        )
        self.assertEqual(pe.end(self.base + 0x1000), self.base + 0x1003)

    def test_all_conditional_paths_are_kept_after_the_first_ret(self):
        pe = self.image(bytes.fromhex("85c07406b801000000c331c0c3") + b"\xcc" * 16)
        self.assertEqual(pe.end(self.base + 0x1000), self.base + 0x100D)

    def test_unresolved_indirect_jump_keeps_conservative_bound(self):
        pe = self.image(bytes.fromhex("ffe031c0c3"))
        self.assertEqual(pe.end(self.base + 0x1000), self.base + 0x1100)

    def test_unwind_range_is_not_shortened_at_an_early_ret(self):
        pe = self.image(bytes.fromhex("31c0c3"), unwind=True)
        self.assertEqual(pe.end(self.base + 0x1000), self.base + 0x1080)

    def test_original_evidence_span_cannot_shrink_with_the_new_leaf_boundary(self):
        pe = self.image(bytes.fromhex("31c0c3") + b"\xcc" * 16)
        self.assertEqual(_function_end(pe, self.base + 0x1000, 16), self.base + 0x1010)

    def test_short_function_locator_window_can_include_neighbors_without_extending_proof(
        self,
    ):
        pe = self.image(
            bytes.fromhex("44890244894a04c3")
            + b"\xcc" * 8
            + bytes.fromhex("41837804007401c3")
            + b"\xcc" * 16
        )
        start = self.base + 0x1000
        self.assertEqual(pe.end(start), start + 8)
        self.assertGreaterEqual(len(masked_pattern(pe, start, 24)) // 2, 24)
        self.assertEqual(pe.end(start), start + 8)

    def test_changed_reachable_code_changes_digest_but_neighbor_bytes_do_not(self):
        pe = self.image(bytes.fromhex("31c0c3") + b"\xcc" * 16)
        original = normalized_digest(pe, self.base + 0x1000)
        other = self.image(bytes.fromhex("31c0c3") + b"\x90" * 16)
        self.assertEqual(original, normalized_digest(other, self.base + 0x1000))
        changed = self.image(bytes.fromhex("b801000000c3") + b"\xcc" * 16)
        self.assertNotEqual(original, normalized_digest(changed, self.base + 0x1000))


if __name__ == "__main__":
    unittest.main()
