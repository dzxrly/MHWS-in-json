"""Reject stores without the reviewed operator provenance or constant value."""

import importlib.util
import unittest

from sdk.enemy_logic_exporter.shared.resources.requests import packed_request_stores


@unittest.skipUnless(importlib.util.find_spec("capstone"), "需要离线 SDK 的 capstone")
class RequestStoreTests(unittest.TestCase):
    def test_abi_operator_and_packed_command_argument_indices(self):
        # mov rbx,r9; movabs rax,0x23800000004; mov [rbx+0xb0],rax
        body = bytes.fromhex("4c89cb48b80400000038020000488983b0000000")
        result = packed_request_stores(body, 0x1000)
        self.assertEqual(len(result), 1)
        self.assertEqual(
            (result[0]["commandIndex"], result[0]["argumentIndex"]), (4, 568)
        )
        self.assertEqual(result[0]["address"], "0x100d")

    def test_same_offset_on_an_unrelated_object_is_not_an_action(self):
        # Same store, but rbx was copied from rcx, not the operator parameter.
        body = bytes.fromhex("4889cb48b80400000038020000488983b0000000")
        self.assertEqual(packed_request_stores(body, 0x1000), [])

    def test_conditional_branch_discards_nonlocal_constant(self):
        body = bytes.fromhex("4c89cb48b804000000380200007500488983b0000000")
        self.assertEqual(packed_request_stores(body, 0x1000), [])

    def test_call_invalidates_the_volatile_value(self):
        body = bytes.fromhex("4c89cb48b80400000038020000e800000000488983b0000000")
        self.assertEqual(packed_request_stores(body, 0x1000), [])

    def test_epilogue_restore_does_not_discard_prior_request(self):
        body = bytes.fromhex("4c89cb48b80400000038020000488983b00000005bc3")
        self.assertEqual(len(packed_request_stores(body, 0x1000)), 1)

    def test_operator_alias_created_only_on_one_branch_is_rejected(self):
        body = bytes.fromhex("75034c89cb48b80400000038020000488983b0000000")
        self.assertEqual(packed_request_stores(body, 0x1000), [])

    def test_join_target_does_not_inherit_previous_constant(self):
        body = bytes.fromhex("4c89cb48b80400000038020000488983b0000000")
        self.assertEqual(packed_request_stores(body, 0x1000, block_starts=[0x100D]), [])

    def test_operator_register_reused_after_request_preserves_prior_store(self):
        # mov rdi,r9; mov qword [rdi+0xb0],4; mov rdi,rcx; ret.
        # ReturnAreaCenter similarly reuses rdi for ReturnStack after its B0 store.
        body = bytes.fromhex("4c89cf48c787b0000000040000004889cfc3")
        result = packed_request_stores(body, 0x1000)
        self.assertEqual(
            [(r["address"], r["packedValue"]) for r in result], [("0x1003", 4)]
        )

    def test_back_edge_from_clobbered_alias_rejects_prior_store(self):
        # The same store can be reached again after rdi became an unrelated object.
        body = bytes.fromhex("4c89cf48c787b0000000040000004889cfebf0")
        self.assertEqual(packed_request_stores(body, 0x1000), [])
