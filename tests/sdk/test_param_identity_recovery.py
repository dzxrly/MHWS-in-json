"""Typed Param lookup is separate from previous-random field assumptions."""

import hashlib
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sdk.enemy_logic_exporter.shared.config import symbol
from sdk.enemy_logic_exporter.shared.logic.machine import Machine
from sdk.enemy_logic_exporter.shared.logic.table_state import (
    DICT_TYPE,
    OPERATOR_TYPE,
    PARAM_TYPE,
    recover_table_history,
)


def existing_fixture():
    from tests.sdk.test_table_state import TableHistoryTests

    return TableHistoryTests().machine()


def with_setup(
    *,
    wrong_class=False,
    wrong_insert_key=False,
    unknown_field=False,
    throw_behavior=2,
    inline=False,
    wrong_inline_offset=False,
    wrong_inline_object=False,
    wrong_inline_value=False,
):
    fixture = existing_fixture()
    base = int(fixture.row["address"], 16)
    owner = fixture.row["type"]
    setup, slot, klass = base - 0x2000, base - 0x1000, base - 0x3000
    constructor = int(
        fixture.metadata.get(owner + ".Param")["methods"][".ctor1"]["function"], 16
    )
    lookup = next(
        ins.operands[0].imm for ins in fixture.ins.values() if ins.mnemonic == "call"
    )
    native = bytearray.fromhex(
        "5657534883ec304c89c34889d74889ce498b9098000000448b4730"
        if inline
        else "41565657534883ec284c89c34889d74889ce498b9098000000448b4730"
    )

    def call(target):
        native.extend(b"\xe8" + struct.pack("<i", target - setup - len(native) - 5))

    call(lookup)
    native.extend(bytes.fromhex("4885c07500"))
    present_jump = len(native) - 1
    native.extend(bytes.fromhex("488b9b980000008b7f30"))
    native.extend(b"\x48\x8b\x15" + struct.pack("<i", slot - setup - len(native) - 7))
    native.extend(bytes.fromhex("4889f14531c0"))
    call(symbol("managed_object_allocate"))
    if inline:
        native.extend(bytes.fromhex("48c740"))
        native.extend(bytes([0x14 if wrong_inline_offset else 0x10]))
        native.extend(struct.pack("<i", -2 if wrong_inline_value else -1))
    else:
        native.extend(bytes.fromhex("4989c64889f14889c2"))
        call(constructor)
    native.extend(bytes.fromhex("c6442420024889f14889da"))
    native.extend(bytes.fromhex("4189c8" if wrong_insert_key else "4189f8"))
    native.extend(
        bytes.fromhex("4989c9" if wrong_inline_object else "4989c1")
        if inline
        else bytes.fromhex("4d89f1")
    )
    call(symbol("btable_param_try_insert"))
    native[present_jump] = len(native) - present_jump - 1
    native.extend(
        bytes.fromhex("904883c4305b5f5ec3" if inline else "904883c4285b5f5e415ec3")
    )
    setup_bytes = bytes(native)
    original_get, original_read = fixture.metadata.get, fixture.pe.read
    param = dict(original_get(owner + ".Param"), address=hex(klass))
    if inline:
        param["fields"] = {
            name: field
            for name, field in param["fields"].items()
            if field.get("offset_from_base") in {"0x10", "0x14"}
        }
    param["methods"] = {
        ".ctor1": dict(function=hex(constructor)[2:], returns=dict(type="System.Void"))
    }
    if unknown_field:
        param["fields"] = dict(
            param["fields"],
            Unreviewed=dict(type="System.Single", offset_from_base="0x198"),
        )
    dictionary = original_get(DICT_TYPE)
    dictionary = dict(dictionary, methods=dict(dictionary["methods"]))
    dictionary["methods"]["TryInsert17"] = dict(
        function=hex(symbol("btable_param_try_insert"))[2:],
        params=[
            dict(type="System.Int32"),
            dict(type=PARAM_TYPE),
            dict(type="System.Collections.Generic.InsertionBehavior"),
        ],
        returns=dict(type="System.Boolean"),
    )
    records = {
        owner: dict(
            methods={
                "setupOperatorWork99": dict(
                    function=hex(setup)[2:],
                    params=[dict(type=OPERATOR_TYPE)],
                    returns=dict(type="System.Void"),
                )
            }
        ),
        owner + ".Param": param,
        DICT_TYPE: dictionary,
        "System.Collections.Generic.InsertionBehavior": dict(
            fields={"ThrowOnExisting": dict(default=throw_behavior)}
        ),
    }
    fixture.metadata = SimpleNamespace(
        get=lambda name: records.get(name, original_get(name)),
        fields=lambda name: records.get(name, original_get(name) or {}).get(
            "fields", {}
        ),
    )
    fixture.pe = SimpleNamespace(
        read=lambda address, size: (
            setup_bytes[:size]
            if address == setup
            else (
                struct.pack("<Q", klass + int(wrong_class))[:size]
                if address == slot
                else (
                    bytes.fromhex("48c74210ffffffffc3")[:size]
                    if inline and address == constructor
                    else original_read(address, size)
                )
            )
        ),
        end=lambda address: (
            setup + len(setup_bytes) if address == setup else address + 1
        ),
    )
    # Keep the real typed lookup prefix but do not read any private fields.
    last_call = next(ins for ins in fixture.ins.values() if ins.mnemonic == "call")
    prefix = b"".join(
        ins.bytes for ins in fixture.ins.values() if ins.address <= last_call.address
    )
    code = prefix + bytes.fromhex("b801000000c3")
    result = Machine(
        dict(
            fixture.row,
            end=hex(base + len(code)),
            nativeSha256=hashlib.sha256(code).hexdigest(),
        ),
        code,
        fixture.pe,
        {},
        [],
        {},
        {},
    )
    result.metadata = fixture.metadata
    return result


class ParamIdentityTests(unittest.TestCase):
    def test_matching_setup_keeps_typed_identity_without_field_defaults(self):
        subject = with_setup()
        history = recover_table_history(subject)
        self.assertIsNotNone(history)
        self.assertEqual(history.fields, {})
        self.assertEqual(history.history_cases(), [])
        self.assertEqual(history.input_definitions(), {})
        self.assertEqual(history.candidates, {})
        proof = history.identity_evidence[0]
        self.assertEqual(proof["type"], subject.row["type"])
        self.assertEqual(proof["method"], "setupOperatorWork99")
        self.assertEqual(proof["fieldValues"], "not_assumed")
        self.assertEqual(proof["insertion"]["behavior"], "ThrowOnExisting")
        self.assertIn(proof, history.evidence)

    def test_changed_class_symbol_cannot_supply_typed_identity(self):
        self.assertIsNone(recover_table_history(with_setup(wrong_class=True)))

    def test_inline_setup_proves_identity_but_not_current_field_values(self):
        history = recover_table_history(with_setup(inline=True))
        self.assertIsNotNone(history)
        self.assertEqual(history.fields, {})
        self.assertEqual(history.history_cases(), [])
        proof = history.identity_evidence[0]
        self.assertTrue(proof["constructor"]["inlined"])
        self.assertEqual(
            proof["constructorEvidence"]["nativeBytes"], "48c74210ffffffffc3"
        )
        self.assertEqual(proof["existingItem"], "preserved")
        self.assertEqual(proof["fieldValues"], "not_assumed")

    def test_inline_setup_rejects_changed_object_initialization_or_layout(self):
        for change in (
            {"wrong_inline_offset": True},
            {"wrong_inline_value": True},
            {"wrong_inline_object": True},
            {"wrong_class": True},
            {"unknown_field": True},
        ):
            with self.subTest(change=change):
                self.assertIsNone(
                    recover_table_history(with_setup(inline=True, **change))
                )

    def test_changed_dictionary_key_dataflow_cannot_supply_typed_identity(self):
        self.assertIsNone(recover_table_history(with_setup(wrong_insert_key=True)))

    def test_changed_insertion_enum_cannot_supply_typed_identity(self):
        self.assertIsNone(recover_table_history(with_setup(throw_behavior=1)))

    def test_unreviewed_private_layout_keeps_a_boundary(self):
        self.assertIsNone(recover_table_history(with_setup(unknown_field=True)))

    def test_missing_setup_does_not_invent_a_param_identity(self):
        subject = with_setup()
        previous = subject.metadata.get
        subject.metadata.get = lambda name: (
            None if name == subject.row["type"] else previous(name)
        )
        self.assertIsNone(recover_table_history(subject))


class ReviewedVariableDiscoveryTests(unittest.TestCase):
    def fixture(self):
        original = existing_fixture()
        base = int(original.row["address"], 16)
        sequence = list(original.ins.values())
        insert = next(
            ins
            for ins in sequence
            if ins.mnemonic == "mov" and ins.op_str == "eax, dword ptr [r12 + 0x10]"
        ).address
        native = bytearray(b"".join(ins.bytes for ins in sequence))
        # The missing-item branch crosses the insertion and must retain its target.
        for ins in sequence:
            if (
                ins.mnemonic.startswith("j")
                and ins.operands[0].type == 2
                and ins.address < insert <= ins.operands[0].imm
            ):
                offset = ins.address - base + ins.imm_offset
                native[offset] += 5
        offset = insert - base
        call = b"\xe8" + struct.pack("<i", base + 0x900 - insert - 5)
        native[offset:offset] = call
        code = bytes(native)
        result = Machine(
            dict(
                original.row,
                end=hex(base + len(code)),
                nativeSha256=hashlib.sha256(code).hexdigest(),
            ),
            code,
            original.pe,
            {},
            [],
            {},
            {},
        )
        result.metadata = original.metadata
        return result

    def test_single_pair_second_pass_crosses_only_reviewed_variable_write(self):
        subject = self.fixture()
        with patch.object(
            Machine, "bind", return_value=dict(commandType="fixture.write")
        ), patch(
            "sdk.enemy_logic_exporter.shared.logic.command_effects.reviewed_command_effect",
            return_value=dict(effect="set_timer_state"),
        ):
            self.assertIsNone(recover_table_history(subject))
            history = recover_table_history(subject, local=True)
        self.assertIsNotNone(history)
        self.assertEqual(history.read_offsets, {0x10, 0x14})
        self.assertEqual(len(history.history_cases()), 3)
        actual_reads = {
            off for offsets in history.read_sites.values() for off in offsets
        }
        self.assertEqual(actual_reads, {0x10, 0x14})
        for site in history.read_sites:
            instruction = subject.ins[site]
            self.assertNotEqual(instruction.operands[-1].type, 2)

    def test_other_command_effect_still_stops_before_history_reads(self):
        subject = self.fixture()
        with patch.object(
            Machine, "bind", return_value=dict(commandType="fixture.request")
        ), patch(
            "sdk.enemy_logic_exporter.shared.logic.command_effects.reviewed_command_effect",
            return_value=dict(effect="request_dynamic_action"),
        ):
            self.assertIsNone(recover_table_history(subject, local=True))


if __name__ == "__main__":
    unittest.main()
