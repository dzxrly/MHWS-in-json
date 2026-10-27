from pathlib import Path
import struct
import unittest

from sdk.action_map_exporter.external_collisions import scan_external_collisions
from sdk.action_map_exporter.models import Il2CppMethod


class _Image:
    def __init__(self, code: bytes) -> None:
        self.code = code

    def read_function_bytes(self, _address: int, length: int) -> bytes:
        return self.code[:length]


def call(ip: int, target: int) -> bytes:
    return b"\xe8" + struct.pack("<i", target - (ip + 5))


class ExternalCollisionScanTests(unittest.TestCase):
    target = Il2CppMethod("app.Weapon", "activateExternalAttackCollision1", 0x2000)

    def scan(self, code: bytes):
        method = Il2CppMethod("app.cHunterWp09Handling", "doUpdate1", 0x1000)
        return scan_external_collisions(_Image(code), method, self.target, len(code))

    def test_literal_r8d_before_call(self):
        code = b"\x41\xb8\x63\x00\x00\x00" + call(0x1006, 0x2000) + b"\xc3"
        self.assertEqual([hit.request_set_id for hit in self.scan(code)], [99])

    def test_register_argument_is_not_a_literal(self):
        code = b"\x44\x8b\xc0" + call(0x1003, 0x2000) + b"\xc3"  # mov r8d,eax
        self.assertEqual(self.scan(code), [])

    def test_other_callee_is_ignored(self):
        code = b"\x41\xb8\x63\x00\x00\x00" + call(0x1006, 0x3000) + b"\xc3"
        self.assertEqual(self.scan(code), [])


if __name__ == "__main__":
    unittest.main()
