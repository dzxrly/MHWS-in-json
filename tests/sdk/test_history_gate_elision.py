"""A PC may omit history cases only after its unknown-Param path is proved."""

from copy import deepcopy
import hashlib
import struct
import unittest
from unittest.mock import patch

from sdk.enemy_logic_exporter.shared.logic.machine import Machine
from sdk.enemy_logic_exporter.shared.logic.table_state import (
    TableHistory,
    prove_history_free_pc,
)


class HistoryFreePcProofTests(unittest.TestCase):
    def fixture(self, continuation, *, table_type="fixture.Export"):
        # Preserve export/operator across the exact Dictionary.FindValue ABI.
        native = bytearray.fromhex("53574889d34c89cf488b9798000000448b4330")
        site = 0x1000 + len(native)
        native.extend(b"\xe8" + struct.pack("<i", 0x2000 - site - 5))
        native.extend(bytes.fromhex("480fbaf03f488b18"))
        native.extend(continuation)
        native = bytes(native)
        machine = Machine(
            dict(
                type=table_type,
                method="table_fixture",
                address="0x1000",
                end=hex(0x1000 + len(native)),
                nativeSha256=hashlib.sha256(native).hexdigest(),
            ),
            native,
            None,
            {},
            [],
            {},
            {},
        )
        machine.table_history = TableHistory(
            table_type,
            0x98,
            0x30,
            0x2000,
            {16: "BefoRandomMax_1", 20: "BefoRandomMin_1"},
        )
        return machine

    def test_only_the_pc_that_does_not_read_param_can_skip_its_gate(self):
        # PC12 returns false; every other PC reads a field, even if its value is
        # later discarded and all enumerated candidates could return alike.
        machine = self.fixture(
            bytes.fromhex("8b87a800000083f80c750531c05f5bc38b431031c05f5bc3")
        )
        before = {
            key: deepcopy(machine.__dict__[key])
            for key in ("nodes", "pending", "states", "event_contexts")
        }
        proof = prove_history_free_pc(machine, 12)
        self.assertEqual(proof["programCounter"], 12)
        self.assertFalse(proof["returnValue"])
        self.assertFalse(proof["tableEnded"])
        self.assertEqual(len(proof["lookupSites"]), 1)
        self.assertEqual(proof["nativePath"][-1]["nativeBytes"], "c3")
        self.assertIsNone(prove_history_free_pc(machine, 0))
        # The proof neither walks semantic nodes nor changes history/state.
        for key in ("nodes", "pending", "states", "event_contexts"):
            self.assertEqual(machine.__dict__[key], before[key])
        self.assertEqual(machine.table_history.candidates, {})

    def test_param_writes_untracked_fields_and_escapes_keep_the_gate(self):
        for continuation in (
            "c743102900000031c05f5bc3",  # tracked history write
            "8b83a001000031c05f5bc3",  # untracked field in the same Param
            "48895f1031c05f5bc3",  # escape through operator
            "4889dc5031c05f5bc3",  # Param disguised as the implicit push stack
            "4889d85f5bc3",  # return the Param pointer itself
        ):
            with self.subTest(continuation=continuation):
                self.assertIsNone(
                    prove_history_free_pc(self.fixture(bytes.fromhex(continuation)), 0)
                )

    def test_unknown_calls_branches_and_unsupported_instructions_keep_the_gate(self):
        for continuation in (
            "e80000000031c05f5bc3",  # no transparent-call guess
            "85c9740531c05f5bc3b8010000005f5bc3",  # unknown post-call ecx
            "ebfe",  # loop
            "0f0b31c05f5bc3",  # ud2 is not Machine.step's permissive fallback
        ):
            with self.subTest(continuation=continuation):
                self.assertIsNone(
                    prove_history_free_pc(self.fixture(bytes.fromhex(continuation)), 0)
                )

    def test_known_history_in_an_entry_override_is_not_an_independence_proof(self):
        machine = self.fixture(bytes.fromhex("31c05f5bc3"))
        original = machine.initial

        def initial(pc):
            state = original(pc)
            state["mem"][(machine.table_history.owner, 16, 4)] = 41
            return state

        machine.initial = initial
        self.assertIsNone(prove_history_free_pc(machine, 0))

    def test_cookie_check_can_be_preserved_but_cannot_receive_param(self):
        prefix = self.fixture(b"")
        start = int(prefix.row["end"], 16)
        for setup, accepted in (
            (bytes.fromhex("31c9"), True),
            (bytes.fromhex("4889d9"), False),
        ):
            site = start + len(setup)
            call = b"\xe8" + struct.pack("<i", 0x2100 - site - 5)
            machine = self.fixture(setup + call + bytes.fromhex("31c05f5bc3"))
            with patch(
                "sdk.enemy_logic_exporter.shared.config.FN_STACK_COOKIE_CHECK", 0x2100
            ):
                self.assertEqual(
                    prove_history_free_pc(machine, 0) is not None, accepted
                )

    def test_operator_end_write_is_retained_and_param_identity_is_not_guessed(self):
        machine = self.fixture(bytes.fromhex("c687c600000001b8010000005f5bc3"))
        proof = prove_history_free_pc(machine, 0)
        self.assertTrue(proof["returnValue"])
        self.assertTrue(proof["tableEnded"])
        self.assertIn(
            "export_runtime_id_dictionary_item_already_created", proof["preconditions"]
        )
        # A different dictionary identity fails the exact typed lookup; it is
        # not converted into a zero/history value or an assumed successful call.
        machine.table_history.dictionary_offset = 0x90
        self.assertIsNone(prove_history_free_pc(machine, 0))
        machine.table_history = None
        self.assertIsNone(prove_history_free_pc(machine, 0))

    def test_repeated_build_keeps_all_proofs_once_in_program_counter_order(self):
        machine = self.fixture(bytes.fromhex("31c05f5bc3"))
        history = machine.table_history
        history.read_offsets = {16, 20}
        history.candidates = {((16, 51), (20, 0)): {"0x3000"}}
        machine.state(12)
        machine.state(3)
        first = machine.build()
        second = machine.build()
        self.assertEqual(first["historyGateElisions"], second["historyGateElisions"])
        self.assertEqual(
            [proof["programCounter"] for proof in second["historyGateElisions"]],
            [0, 3, 12],
        )
        self.assertEqual(first["entry"], second["entry"])
        self.assertEqual(first["nodes"], second["nodes"])
        # Selector recovery can add more PCs between builds. Earlier evidence
        # remains, and the next build adds only the newly proved entry.
        machine.state(7)
        third = machine.build()
        self.assertEqual(
            [proof["programCounter"] for proof in third["historyGateElisions"]],
            [0, 3, 7, 12],
        )


if __name__ == "__main__":
    unittest.main()
