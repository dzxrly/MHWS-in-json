"""Verify selector PCs from native instructions rather than array spacing."""

import hashlib
from importlib.util import find_spec
import unittest
from unittest.mock import Mock, patch


@unittest.skipUnless(find_spec("capstone"), "离线原生测试需要 SDK 的 Capstone 依赖")
class NativeSelectorTests(unittest.TestCase):
    def machine(self, hexadecimal):
        from sdk.enemy_logic_exporter.shared.logic.machine import Machine

        native = bytes.fromhex(hexadecimal)
        row = dict(
            type="fixture",
            address="0x1000",
            nativeSha256=hashlib.sha256(native).hexdigest(),
        )
        return Machine(row, native, None, {}, [], {}, {})

    def test_candidate_mapping_follows_nonconsecutive_native_pc_writes(self):
        from sdk.enemy_logic_exporter.shared.logic.selectors import _dispatch_pc

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
        from sdk.enemy_logic_exporter.shared.logic.selectors import (
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
        from sdk.enemy_logic_exporter.shared.logic.selectors import _dispatch_pc

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
        from sdk.enemy_logic_exporter.shared.logic.selectors import _dispatch_pc

        machine = self.machine(
            "48 63 d1 83 fa 02 74 07 b8 12 00 00 00 eb 05 b8 04 00 00 00 "
            "41 80 bf c6 00 00 00 00 c3"
        )
        self.assertEqual(
            _dispatch_pc(machine, 0x1000, selected_register="rcx", selected_index=2),
            4,
        )

    def test_unknown_call_in_dispatch_keeps_the_boundary(self):
        from sdk.enemy_logic_exporter.shared.logic.selectors import (
            _dispatch_pc,
            SelectorBoundary,
        )

        machine = self.machine(
            "e8 00 00 00 00 b8 04 00 00 00 41 80 bf c6 00 00 00 00 c3"
        )
        with self.assertRaises(SelectorBoundary):
            _dispatch_pc(machine, 0x1000, selected_register="rcx", selected_index=1)

    def test_per_candidate_arguments_follow_native_base_and_increment(self):
        from sdk.enemy_logic_exporter.shared.logic.selectors import _filter_arguments

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

class SelectorCandidateContractTests(unittest.TestCase):
    def recover_shared_target(
        self, keys=(11, 22), candidate_pcs=(5, 7), *, reviewed_child=True
    ):
        from sdk.enemy_logic_exporter.shared.logic.selectors import recover_selectors

        boundary = "boundary-0x1010"
        machine = Mock()
        machine.row = {"address": "0x1000"}
        machine.nodes = {
            boundary: {"id": boundary, "kind": "unknown", "nativeSite": "0x1010"},
            "child-call": {
                "id": "child-call",
                "kind": "call" if reviewed_child else "unknown",
                "targetTable": "child",
                "nativeContinuation": {"tableIndex": 0, "programCounter": 30},
            },
            "fallback": {"id": "fallback", "kind": "return", "value": False},
        }
        machine.initial.side_effect = lambda pc: pc
        machine.walk.side_effect = lambda start, pc: (
            boundary if pc == 1 else "child-call"
        )
        machine.state.side_effect = lambda pc: "pc-" + str(pc)
        machine.states = {
            **{"pc-" + str(pc): "child-call" for pc in candidate_pcs},
            "pc-9": "fallback",
        }
        machine.build.side_effect = lambda: {
            "entry": boundary,
            "nodes": list(machine.nodes.values()),
        }
        code = "lRam000000015488da28 + 0x24"
        pool = {
            "entries": [
                {"nativeKey": keys[0], "weight": 35},
                {"nativeKey": keys[1], "weight": 5},
            ],
            "initializerEvidence": {"type": "fixture", "method": ".cctor"},
        }
        skip_type = "app.btable.EmCommonCommand.cSetSkipActionTblArg"
        with (
            patch(
                "sdk.enemy_logic_exporter.shared.logic.selectors._outer_blocks",
                return_value={1: code, **{pc: "" for pc in candidate_pcs}, 9: ""},
            ),
            patch("sdk.enemy_logic_exporter.shared.logic.selectors._selection_form"),
            patch(
                "sdk.enemy_logic_exporter.shared.logic.selectors._native_routes",
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
                "sdk.enemy_logic_exporter.shared.logic.selectors._filter_arguments",
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
                "sdk.enemy_logic_exporter.shared.logic.selectors._dispatch_pc",
                side_effect=[9, *candidate_pcs],
            ),
        ):
            result, accepted, boundaries = recover_selectors(
                machine, code, {"0x15488da28": pool}, {}
            )
        return result, accepted, boundaries, machine

    def test_convergent_slots_keep_ids_keys_weights_and_independent_filters(self):
        for keys in ((11, 22), (22, 22)):
            with self.subTest(keys=keys):
                result, accepted, boundaries, _ = self.recover_shared_target(keys)
                self.assertEqual(boundaries, [])
                self.assertEqual(len(accepted), 1)
                node = next(
                    n for n in result["nodes"] if n["kind"] == "weighted_random"
                )
                candidates = node["candidates"]
                self.assertEqual([c["id"] for c in candidates], ["slot:0", "slot:1"])
                self.assertEqual(
                    [c["nativeCandidateIndex"] for c in candidates], [0, 1]
                )
                self.assertEqual(
                    [c["nodeId"] for c in candidates], ["child-call", "child-call"]
                )
                self.assertEqual([c["nativeKey"] for c in candidates], list(keys))
                self.assertEqual([c["weight"] for c in candidates], [35, 5])
                self.assertEqual(
                    [c["nativeProgramCounter"] for c in candidates], [5, 7]
                )
                self.assertEqual(
                    [c["skipArgumentIndex"] for c in candidates], [304, 305]
                )
                self.assertEqual(node["fallback"], "fallback")
                self.assertEqual(sum(n["kind"] == "call" for n in result["nodes"]), 1)
                convergence = accepted[0]["candidateDispatchConvergences"]["child-call"]
                self.assertEqual([c["id"] for c in convergence], ["slot:0", "slot:1"])
                self.assertEqual(
                    [c["nativeProgramCounter"] for c in convergence], [5, 7]
                )

    def test_shared_native_pc_does_not_clone_the_call_or_invent_another_pc(self):
        result, accepted, boundaries, _ = self.recover_shared_target(
            candidate_pcs=(5, 5)
        )
        candidates = next(n for n in result["nodes"] if n["kind"] == "weighted_random")[
            "candidates"
        ]
        self.assertEqual(boundaries, [])
        self.assertEqual(accepted[0]["candidateStates"], [5, 5])
        self.assertEqual([c["nativeProgramCounter"] for c in candidates], [5, 5])
        self.assertEqual(
            [c["nodeId"] for c in candidates], ["child-call", "child-call"]
        )
        self.assertEqual([c["id"] for c in candidates], ["slot:0", "slot:1"])
        self.assertEqual(sum(n["kind"] == "call" for n in result["nodes"]), 1)

if __name__ == "__main__":
    unittest.main()
