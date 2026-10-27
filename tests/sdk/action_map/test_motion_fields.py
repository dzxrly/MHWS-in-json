from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import struct
import tempfile
import unittest

from sdk.action_map_exporter.il2cpp_methods import Il2CppMethodCatalog, MotionField
from sdk.action_map_exporter.models import Il2CppMethod, MotionTarget
from sdk.action_map_exporter.motion_catalogs import MotionTargetCatalog
from sdk.action_map_exporter.motion_fields import ConstructorMotionScanner


@dataclass
class CodeImage:
    functions: dict[int, bytes]

    def read_function_bytes(self, address: int, size: int) -> bytes:
        return self.functions.get(address, b"")[:size]


def store(offset: int, value: int) -> bytes:
    return b"\xc7\x82" + struct.pack("<II", offset, value)


def branch(address: int, target: int, opcode: bytes = b"\xe8") -> bytes:
    return opcode + struct.pack("<i", target - address - 5)


class ConstructorMotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.method = Il2CppMethod("Child", ".ctor1", 0x1000)
        self.parent = Il2CppMethod("Parent", ".ctor2", 0x2000)
        self.members = (
            MotionField("Parent", "_LeftMotionID", 0x100),
            MotionField("Parent", "_RightMotionID", 0x104),
        )
        self.targets = MotionTargetCatalog(
            {
                ("Wp00", n): MotionTarget(
                    "Wp00", n, 20, n & 0xFFF, "test.json", "test", ()
                )
                for n in range(0x14001, 0x14005)
            },
            [],
        )

    def scan(self, child: bytes, parent: bytes = b"\xc3", *, members=None, others=()):
        methods = {
            "Child": [self.method],
            "Parent": [self.parent],
            **{m.type_name: [m] for m in others},
        }
        catalog = Il2CppMethodCatalog(
            methods,
            [0x1000, 0x2000, 0x3000],
            {"Child": "Parent"},
            {"Parent": self.members if members is None else members},
        )
        scanner = ConstructorMotionScanner(
            CodeImage({0x1000: child, 0x2000: parent}), catalog, self.targets, 4096
        )
        return scanner.scan("Wp00", self.method)

    def test_recovers_both_typed_lanes_through_register_move(self) -> None:
        code = (
            b"\x48\x89\xd6\x48\xb8"
            + struct.pack("<Q", 0x1400200014001)
            + b"\x49\x89\xc0\x4c\x89\x86\x00\x01\x00\x00\xc3"
        )
        hits = self.scan(code)
        self.assertEqual([h.target.motion_set_id for h in hits], [0x14001, 0x14002])
        self.assertEqual(dict(hits[1].field_evidence)["laneByteOffset"], 4)
        self.assertEqual(dict(hits[1].field_evidence)["fieldName"], "_RightMotionID")

    def test_does_not_split_pointer_or_untyped_neighbor(self) -> None:
        code = (
            b"\x48\xb8"
            + struct.pack("<Q", 0x1400200014001)
            + b"\x48\x89\x82\x00\x01\x00\x00\xc3"
        )
        self.assertEqual(self.scan(code, members=self.members[:1]), [])
        self.assertEqual(
            self.scan(b"\x48\xb8" + struct.pack("<Q", 0x1400200014001) + b"\xc3"), []
        )

    def test_parent_initialization_child_override_and_shared_address(self) -> None:
        code = (
            b"\x48\x89\xd6"
            + branch(0x1003, 0x2000)
            + b"\x48\x89\xf2"
            + store(0x104, 0x14003)
            + b"\xc3"
        )
        parent = store(0x100, 0x14001) + store(0x104, 0x14002) + b"\xc3"
        hits = self.scan(
            code, parent, others=(Il2CppMethod("Unrelated", ".ctor0", 0x2000),)
        )
        self.assertEqual([h.target.motion_set_id for h in hits], [0x14001, 0x14003])
        self.assertEqual(dict(hits[0].field_evidence)["initializerType"], "Parent")
        self.assertEqual(hits[0].constructor_chain[0][3], 0x1003)
        self.assertEqual(hits[1].constructor_chain, ())

    def test_tail_constructor_preserves_untouched_child_field(self) -> None:
        code = store(0x104, 0x14002) + branch(0x100A, 0x2000, b"\xe9")
        hits = self.scan(code, store(0x100, 0x14001) + b"\xc3")
        self.assertEqual([h.target.motion_set_id for h in hits], [0x14001, 0x14002])

    def test_other_object_constructor_does_not_inherit(self) -> None:
        code = b"\x48\x89\xc2" + branch(0x1003, 0x2000) + b"\xc3"
        self.assertEqual(self.scan(code, store(0x100, 0x14001) + b"\xc3"), [])

    def test_partial_or_unknown_write_invalidates_field(self) -> None:
        for overwrite in (b"\xc6\x82\x01\x01\x00\x00\x00", b"\x89\x82\x00\x01\x00\x00"):
            self.assertEqual(self.scan(store(0x100, 0x14001) + overwrite + b"\xc3"), [])

    def test_branch_disagreement_is_unknown(self) -> None:
        code = (
            store(0x100, 0x14001)
            + b"\x85\xc0\x74\x0a"
            + store(0x100, 0x14002)
            + b"\xc3"
        )
        self.assertEqual(self.scan(code), [])

    def test_unknown_call_on_this_invalidates_values(self) -> None:
        code = store(0x100, 0x14001) + branch(0x100A, 0x3000) + b"\xc3"
        self.assertEqual(self.scan(code), [])

    def test_recursive_constructor_and_loop_terminate(self) -> None:
        self.assertEqual(self.scan(branch(0x1000, 0x1000) + b"\xc3"), [])
        self.assertEqual(self.scan(b"\xeb\xfe"), [])

    def test_metadata_loads_parent_closure_and_filters_width_and_static(self) -> None:
        def member(name, type_name="System.UInt32", flags="Private"):
            return {"type": type_name, "flags": flags, "offset_from_base": "0x100"}

        document = {
            "Child": {"parent": "Parent", "methods": {".ctor1": {"function": "1000"}}},
            "Unrelated": {"methods": {".ctor3": {"function": "2000"}}},
            "Parent": {
                "parent": "Child",
                "methods": {".ctor2": {"function": "2000"}},
                "fields": {
                    "_LandMotionID": member("valid"),
                    "_PointerMotionID": member("pointer", "System.UInt64"),
                    "_StaticMotionID": member("static", flags="Static"),
                    "_MotionFrameCount": member("count"),
                },
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dump.json"
            path.write_text(json.dumps(document), encoding="utf8")
            catalog = Il2CppMethodCatalog.load(path, {"Child"})
        self.assertEqual(set(catalog.target_methods), {"Child", "Parent"})
        self.assertEqual(catalog.lineage("Child"), ("Child", "Parent"))
        self.assertEqual(catalog.motion_fields("Child")[0x100].name, "_LandMotionID")


if __name__ == "__main__":
    unittest.main()
