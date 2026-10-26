"""Regress actual variable arithmetic, timer modes, and dynamic action identity."""

from copy import deepcopy
import json
import unittest

from sdk.enemy_logic_exporter.shared.config import EVIDENCE_DIR
from sdk.enemy_logic_exporter.shared.logic.command_effects import (
    BOOL_COMMAND,
    FLOAT_COMMAND,
    SELECTED_COMMAND,
    SWITCH_COMMAND,
    TIMER_COMMAND,
    action_switch_details,
    apply_variable_update,
    dynamic_request_details,
    pack_action_id,
    receipt,
    reviewed_command_effect,
    storage_effect,
    verify_command_effects,
)
from sdk.enemy_logic_exporter.shared.logic.values import MissingState
from sdk.enemy_logic_exporter.monster.em0164_50_0 import recover_phase_apply


class Metadata:
    def __init__(self, proof):
        self.records = {}
        rows = (
            proof.get("methods", [])
            + list(proof.get("commands", {}).values())
            + list(proof.get("helpers", {}).values())
        )
        for row in rows:
            if "type" in row:
                self.records.setdefault(row["type"], {}).setdefault("methods", {})[
                    row["method"]
                ] = dict(
                    function=row["address"],
                    returns=dict(type=row.get("returns")),
                    params=[dict(type=t) for t in row.get("parameters", [])],
                )
        for owner, fields in proof.get("layouts", {}).items():
            self.records.setdefault(owner, {})["fields"] = {
                name: dict(type=value["type"], offset_from_base=value["offset"])
                for name, value in fields.items()
            }
        for owner, values in proof.get("enums", {}).items():
            self.records.setdefault(owner, {})["fields"] = {
                name: dict(default=value) for name, value in values.items()
            }

    def get(self, owner):
        return self.records.get(owner)

    def fields(self, owner):
        return self.records.get(owner, {}).get("fields", {})


class PE:
    def __init__(self, rows):
        self.ranges = {
            int(row["address"], 16): bytes.fromhex(row["nativeBytes"]) for row in rows
        }

    def read(self, address, count):
        for start, content in self.ranges.items():
            if start <= address and address + count <= start + len(content):
                return content[address - start : address - start + count]
        return b""


def bound(command, **argument):
    return dict(commandType=command, argumentType=command + "Arg", argument=argument)


class ReviewedCommandEffectTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {
            "float": dict(kind="float", life="GLOBAL", default=0, min=0, max=10),
            "bool": dict(kind="bool", life="LOCAL", default=False),
            "timer": dict(kind="timer", life="GLOBAL", default=12),
        }

    def effect(self, command, **argument):
        return reviewed_command_effect(
            bound(command, **argument), receipt()["commands"][command], self.catalog
        )["variableUpdate"]

    def test_float_assign_add_and_subtract_clamp_to_resource_limits(self):
        for method, value, old, expected in (
            (0, 20, 3, 10),
            (1, 8, 5, 10),
            (2, 7, 2, 0),
        ):
            with self.subTest(method=method):
                update = self.effect(
                    FLOAT_COMMAND,
                    _TargetVariableIndex="float",
                    _Method=method,
                    _Value=value,
                )
                self.assertEqual(
                    apply_variable_update(update, {"value": old})["value"], expected
                )

    def test_float_update_rounds_single_precision_before_clamping(self):
        self.catalog["float"].update(max=100000000)
        update = self.effect(
            FLOAT_COMMAND, _TargetVariableIndex="float", _Method=1, _Value=1
        )
        self.assertEqual(
            apply_variable_update(update, {"value": 16777216})["value"], 16777216
        )

    def test_constant_is_not_written_and_missing_live_value_is_not_zero(self):
        self.catalog["float"]["life"] = "CONSTANT"
        update = self.effect(
            FLOAT_COMMAND, _TargetVariableIndex="float", _Method=1, _Value=2
        )
        self.assertEqual(apply_variable_update(update, {"value": 7}), {"value": 7})
        self.catalog["float"]["life"] = "GLOBAL"
        update = self.effect(
            FLOAT_COMMAND, _TargetVariableIndex="float", _Method=1, _Value=2
        )
        with self.assertRaises(MissingState):
            apply_variable_update(update, {})

    def test_unknown_variable_does_not_invent_bounds_or_success(self):
        result = reviewed_command_effect(
            bound(FLOAT_COMMAND, _TargetVariableIndex="unknown", _Method=0, _Value=2),
            receipt()["commands"][FLOAT_COMMAND],
            self.catalog,
        )
        self.assertFalse(result["commandEffectsComplete"])
        self.assertNotIn("min", result["variableUpdate"])
        with self.assertRaises(MissingState):
            apply_variable_update(result["variableUpdate"], {"value": 4})

    def test_timer_activate_deactivate_and_no_reset_are_distinct(self):
        for mode, expected in (
            (0, {"value": 12.0, "active": True}),
            (1, {"value": 3, "active": False}),
            (2, {"value": 3, "active": True}),
        ):
            with self.subTest(mode=mode):
                update = self.effect(
                    TIMER_COMMAND, _TargetVariableIndex="timer", _SetType=mode
                )
                self.assertEqual(
                    apply_variable_update(update, {"value": 3, "active": False}),
                    expected,
                )
        address = int(receipt()["helpers"]["timer"]["address"], 16)
        update = storage_effect(address, "timer", 9, 0, variable_catalog=self.catalog)[
            "variableUpdate"
        ]
        self.assertEqual(
            apply_variable_update(update, {"value": 3, "active": False}),
            {"value": 9.0, "active": False},
        )

    def test_bool_command_and_direct_storage_require_boolean(self):
        update = self.effect(BOOL_COMMAND, _TargetVariableIndex="bool", _Value=True)
        self.assertEqual(
            apply_variable_update(update, {"value": False}), {"value": True}
        )
        address = int(receipt()["helpers"]["bool"]["address"], 16)
        with self.assertRaises(MissingState):
            storage_effect(address, "bool", 1, variable_catalog=self.catalog)

    def test_mismatched_implementation_and_argument_type_are_rejected(self):
        evidence = deepcopy(receipt()["commands"][FLOAT_COMMAND])
        evidence["address"] = "0x1000"
        with self.assertRaises(ValueError):
            reviewed_command_effect(bound(FLOAT_COMMAND), evidence)
        bad = bound(FLOAT_COMMAND)
        bad["argumentType"] = "ace.btable.cSetTimerValueArg"
        with self.assertRaises(ValueError):
            reviewed_command_effect(bad, receipt()["commands"][FLOAT_COMMAND])

    def test_dynamic_action_preserves_source_guard_and_void_continuation(self):
        result = dynamic_request_details(
            bound(SELECTED_COMMAND, _EditArg="[2] OBSTACLE"),
            receipt()["commands"][SELECTED_COMMAND],
        )
        self.assertEqual(result["actionSource"]["field"], "Obstacle.ObstacleType")
        self.assertTrue(result["actionSource"]["resourceSelection"])
        self.assertEqual(result["returnType"], "System.Void")
        self.assertEqual(result["requestGuard"]["kind"], "all")
        self.assertNotIn("actionGuid", result)
        self.assertNotIn("actorRequestGuard", result)

    def test_action_switch_is_integer_and_packs_only_known_width(self):
        result = action_switch_details(
            bound(SWITCH_COMMAND, _EditArg="[1] DAMAGE"),
            receipt()["commands"][SWITCH_COMMAND],
        )
        self.assertEqual(result["runtimeKey"], "action_dispatch:damage")
        self.assertEqual(result["returnType"], "System.Int32")
        self.assertEqual(result["valueRepresentation"], "uint32")
        self.assertTrue(result["convertAction"])
        self.assertEqual(pack_action_id(3, 21), 0x30015)
        self.assertEqual(pack_action_id(-1, 21), 0xFFFFFFFF)
        with self.assertRaises(MissingState):
            pack_action_id(65536, 21)

    def test_native_receipt_rejects_byte_layout_and_enum_changes(self):
        proof = receipt()
        rows = list(proof["commands"].values()) + list(proof["helpers"].values())
        pe, metadata = PE(rows), Metadata(proof)
        self.assertTrue(verify_command_effects(pe, metadata))
        start = int(rows[0]["address"], 16)
        pe.ranges[start] = b"\x00" + pe.ranges[start][1:]
        with self.assertRaisesRegex(ValueError, "原生字节"):
            verify_command_effects(pe, metadata)
        pe = PE(rows)
        metadata.fields("ace.btable.cSetFloatValueArg")["_Value"][
            "offset_from_base"
        ] = "0x30"
        with self.assertRaisesRegex(ValueError, "字段布局"):
            verify_command_effects(pe, metadata)
        metadata = Metadata(proof)
        metadata.fields("ace.btable.cVariableStorage.VARIABLE_METHOD")["ADD"][
            "default"
        ] = 3
        with self.assertRaisesRegex(ValueError, "枚举"):
            verify_command_effects(pe, metadata)

    def test_em0164_phase_copy_uses_its_own_tail_and_retains_boundary(self):
        proof = json.loads(
            (EVIDENCE_DIR / "em0164_phase_apply.v1.json").read_text(encoding="utf8")
        )
        pe, metadata = PE(proof["methods"]), Metadata(proof)
        command = proof["methods"][0]
        effects = recover_phase_apply(command, metadata, pe)
        self.assertEqual(effects[0]["destination"]["field"], "_CurrentPhase")
        self.assertEqual(effects[0]["value"]["field"], "_RequestPhase")
        self.assertIn("仍保留边界", effects[0]["guard"])
        helper = proof["methods"][1]
        pe.ranges[int(helper["address"], 16)] = b"\x00" * len(
            bytes.fromhex(helper["nativeBytes"])
        )
        with self.assertRaisesRegex(ValueError, "原生字节"):
            recover_phase_apply(command, metadata, pe)


if __name__ == "__main__":
    unittest.main()
