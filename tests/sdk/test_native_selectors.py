"""Verify selector PCs from native instructions rather than array spacing."""

import hashlib
from importlib.util import find_spec
import unittest
from unittest.mock import Mock, patch


@unittest.skipUnless(find_spec("capstone"), "离线原生测试需要 SDK 的 Capstone 依赖")
class NativeSelectorTests(unittest.TestCase):
    def machine(self, hexadecimal):
        from sdk.enemy_logic_exporter.shared.btable_machine import Machine

        native = bytes.fromhex(hexadecimal)
        row = dict(
            type="fixture",
            address="0x1000",
            nativeSha256=hashlib.sha256(native).hexdigest(),
        )
        return Machine(row, native, None, {}, [], {}, {})

    def test_candidate_mapping_follows_nonconsecutive_native_pc_writes(self):
        from sdk.enemy_logic_exporter.shared.selectors import _dispatch_pc

        machine = self.machine(
            "83 f9 01 74 07 b8 12 00 00 00 eb 05 b8 04 00 00 00 "
            "41 80 bf c6 00 00 00 00 c3"
        )
        self.assertEqual(
            [
                _dispatch_pc(machine, 0x1000, selected_register="rcx", selected_index=i)
                for i in range(2)
            ],
            [18, 4],
        )

    def test_unknown_runtime_branch_does_not_become_a_candidate(self):
        from sdk.enemy_logic_exporter.shared.selectors import (
            _dispatch_pc,
            SelectorBoundary,
        )

        machine = self.machine(
            "83 fa 01 74 07 b8 12 00 00 00 eb 05 b8 04 00 00 00 "
            "41 80 bf c6 00 00 00 00 c3"
        )
        with self.assertRaises(SelectorBoundary):
            _dispatch_pc(machine, 0x1000, selected_register="rcx", selected_index=1)

    def test_outer_pc_uses_the_actual_native_register(self):
        from sdk.enemy_logic_exporter.shared.selectors import _dispatch_pc

        machine = self.machine(
            "83 f9 01 74 07 bd 12 00 00 00 eb 05 bd 04 00 00 00 "
            "41 80 bf c6 00 00 00 00 c3"
        )
        self.assertEqual(
            _dispatch_pc(
                machine,
                0x1000,
                selected_register="rcx",
                selected_index=1,
                pc_register="rbp",
            ),
            4,
        )

    def test_candidate_copy_is_executed_before_native_index_comparisons(self):
        from sdk.enemy_logic_exporter.shared.selectors import _dispatch_pc

        machine = self.machine(
            "48 63 d1 83 fa 02 74 07 b8 12 00 00 00 eb 05 b8 04 00 00 00 "
            "41 80 bf c6 00 00 00 00 c3"
        )
        self.assertEqual(
            _dispatch_pc(machine, 0x1000, selected_register="rcx", selected_index=2),
            4,
        )

    def test_unknown_call_in_dispatch_keeps_the_boundary(self):
        from sdk.enemy_logic_exporter.shared.selectors import (
            _dispatch_pc,
            SelectorBoundary,
        )

        machine = self.machine(
            "e8 00 00 00 00 b8 04 00 00 00 41 80 bf c6 00 00 00 00 c3"
        )
        with self.assertRaises(SelectorBoundary):
            _dispatch_pc(machine, 0x1000, selected_register="rcx", selected_index=1)

    def test_per_candidate_arguments_follow_native_base_and_increment(self):
        from sdk.enemy_logic_exporter.shared.selectors import _filter_arguments

        machine = self.machine("41 bd 30 01 00 00 4a 8b 44 e8 20 49 ff c5 c3")
        block = (
            "lVar16 = 0x130; x = *(p + 0x18) + 0x20 + lVar16 * 8; "
            "pool + 0x24; lVar16 = lVar16 + 1; draw = x % y;"
        )
        skip_type = "app.btable.EmCommonCommand.cSetSkipActionTblArg"
        body = {"_CommandArgArray": [{skip_type: {}} for _ in range(306)]}
        mode, arguments, evidence = _filter_arguments(
            machine,
            block,
            {"entries": [{}, {}]},
            {"poolSizeGuard": "0xfff", "filterLoopEnd": "0x100e"},
            body,
        )
        self.assertEqual(mode, "per_candidate")
        self.assertEqual([argument["index"] for argument in arguments], [304, 305])
        self.assertEqual(evidence["indexRegister"], "r13")

    def test_parameter_array_order_cannot_override_a_native_base_mismatch(self):
        from sdk.enemy_logic_exporter.shared.selectors import (
            _filter_arguments,
            SelectorBoundary,
        )

        machine = self.machine("41 bd 31 01 00 00 4a 8b 44 e8 20 49 ff c5 c3")
        block = (
            "lVar16 = 0x130; x = *(p + 0x18) + 0x20 + lVar16 * 8; "
            "pool + 0x24; lVar16 = lVar16 + 1; draw = x % y;"
        )
        skip_type = "app.btable.EmCommonCommand.cSetSkipActionTblArg"
        body = {"_CommandArgArray": [{skip_type: {}} for _ in range(306)]}
        with self.assertRaises(SelectorBoundary):
            _filter_arguments(
                machine,
                block,
                {"entries": [{}, {}]},
                {"poolSizeGuard": "0xfff", "filterLoopEnd": "0x100e"},
                body,
            )


class SelectorCandidateContractTests(unittest.TestCase):
    def test_distinct_pool_slots_converging_on_one_node_remain_a_boundary(self):
        from sdk.enemy_logic_exporter.shared.selectors import recover_selectors

        boundary = "boundary-0x1010"
        machine = Mock()
        machine.row = {"address": "0x1000"}
        machine.nodes = {
            boundary: {"id": boundary, "kind": "unknown", "nativeSite": "0x1010"},
            "child-call": {
                "id": "child-call",
                "kind": "call",
                "targetTable": "child",
                "nativeContinuation": {"tableIndex": 0, "programCounter": 30},
            },
        }
        machine.initial.side_effect = lambda pc: pc
        machine.walk.side_effect = lambda start, pc: (
            boundary if pc == 1 else "child-call"
        )
        machine.state.side_effect = lambda pc: "pc-" + str(pc)
        machine.states = {"pc-5": "child-call", "pc-7": "child-call"}
        machine.build.side_effect = lambda: {
            "entry": boundary,
            "nodes": list(machine.nodes.values()),
        }
        code = "lRam000000015488da28 + 0x24"
        pool = {
            "entries": [
                {"nativeKey": 11, "weight": 35},
                {"nativeKey": 22, "weight": 5},
            ],
            "initializerEvidence": {"type": "fixture", "method": ".cctor"},
        }
        skip_type = "app.btable.EmCommonCommand.cSetSkipActionTblArg"
        with (
            patch(
                "sdk.enemy_logic_exporter.shared.selectors._outer_blocks",
                return_value={1: code, 5: "", 7: "", 9: ""},
            ),
            patch("sdk.enemy_logic_exporter.shared.selectors._selection_form"),
            patch(
                "sdk.enemy_logic_exporter.shared.selectors._native_routes",
                return_value=(
                    {
                        "start": 0x1050,
                        "selectedRegister": "rcx",
                        "programCounterRegister": "rax",
                        "poolSizeGuard": "0x1010",
                    },
                    0x1090,
                ),
            ),
            patch(
                "sdk.enemy_logic_exporter.shared.selectors._filter_arguments",
                return_value=(
                    "per_candidate",
                    [
                        {"index": 304, "type": skip_type},
                        {"index": 305, "type": skip_type},
                    ],
                    {"indexRegister": "r13"},
                ),
            ),
            patch(
                "sdk.enemy_logic_exporter.shared.selectors._dispatch_pc",
                side_effect=[9, 5, 7],
            ),
        ):
            result, accepted, boundaries = recover_selectors(
                machine, code, {"0x15488da28": pool}, {}
            )
        self.assertEqual(accepted, [])
        self.assertEqual(machine.nodes[boundary]["kind"], "unknown")
        self.assertFalse(
            any(node["kind"] == "weighted_random" for node in result["nodes"])
        )
        self.assertEqual(len(boundaries), 1)
        self.assertEqual(boundaries[0]["status"], "unreviewed_selector_boundary")
        collision = boundaries[0]["candidateDispatchCollisions"]["child-call"]
        self.assertEqual([candidate["nativeKey"] for candidate in collision], [11, 22])
        self.assertEqual(
            [candidate["nativeProgramCounter"] for candidate in collision], [5, 7]
        )
        self.assertEqual(
            [candidate["skipArgumentIndex"] for candidate in collision], [304, 305]
        )


if __name__ == "__main__":
    unittest.main()
