"""Prevent false resource bindings across ABI clobbers and divergent paths."""

import unittest
from importlib.util import find_spec
from sdk.enemy_logic_exporter.shared.native.bindings import bind_native, pointer


@unittest.skipUnless(find_spec("capstone"), "离线原生测试需要 SDK 的 Capstone 依赖")
class NativeBindingTests(unittest.TestCase):
    def bind(self, hexadecimal):
        code = bytes.fromhex(hexadecimal)
        flow = {
            "blocks": [
                {
                    "id": "0",
                    "start": "0x1000",
                    "end": hex(0x1000 + len(code) - 1),
                    "successors": [],
                }
            ]
        }
        return bind_native(code, 0x1000, flow)

    def calls(self, result):
        return [
            e
            for events in result["blocks"].values()
            for e in events
            if e["kind"] == "call"
        ]

    def test_virtual_command_and_argument_follow_actual_abi(self):
        result = self.bind(
            "49 89 d2 4d 8b 4a 18 4d 8b 49 28 49 8b 42 10 48 8b 50 20 48 8b 02 ff 50 70 c3"
        )
        call = self.calls(result)[0]
        self.assertEqual(call["target"], ("command_method", 0, 0x70))
        self.assertEqual(call["arguments"][1], pointer(("command", 0)))
        self.assertEqual(call["arguments"][3], pointer(("argument", 1)))

    def test_call_clears_volatile_command_alias(self):
        result = self.bind("48 8b 42 10 48 8b 50 20 48 8b 02 ff 50 70 ff d0 c3")
        self.assertIsNone(self.calls(result)[1]["arguments"][1])

    def test_conditional_branch_references_exact_call_result_comparison(self):
        result = self.bind("e8 00 00 00 00 84 c0 74 00 c3")
        branch = next(
            e
            for events in result["blocks"].values()
            for e in events
            if e["kind"] == "branch"
        )
        self.assertEqual(branch["comparison"][0], "0x1005")
        self.assertEqual(branch["comparison"][2][0], ("call_result", "0x1000"))

    def test_loop_discards_changing_values_and_converges(self):
        result = self.bind("b9 01 00 00 00 83 c1 01 85 c0 75 f9 e8 00 00 00 00 c3")
        self.assertEqual(result["status"], "converged")
        self.assertIsNone(self.calls(result)[0]["arguments"][0])


if __name__ == "__main__":
    unittest.main()
