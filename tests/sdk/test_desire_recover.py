"""Partial recovery requests retain unknown conversion and exact void exits."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from sdk.enemy_logic_exporter.shared.logic import desire_recover as desire
from sdk.enemy_logic_exporter.shared.logic.expressions import evaluate_expression

SOURCE_GUID = "92324cc4-6782-4060-919b-df2d67ca4ce5"
ZERO_GUID = "00000000-0000-0000-0000-000000000000"


def bound():
    return dict(
        commandType=desire.COMMAND,
        argumentType=desire.ARGUMENT,
        argument={
            "_EditAssetIndex": {"ace.btable.cEditFieldDropBox`1<System.Int32>": 0},
            "_EditActionGuid": {
                "ace.btable.cEditFieldDropBox`1<System.Guid>": SOURCE_GUID
            },
            "_EditBranchedParamGuid": {
                "ace.btable.cEditFieldDropBox`1<System.Guid>": ZERO_GUID
            },
            "_EditType": "[5] AREAMOVE",
        },
    )


def evidence():
    row = desire.receipt()["methods"][0]
    return dict(
        type=row["type"],
        method="onExecute1236520",
        address=row["address"],
        end=row["end"],
    )


def effect():
    return desire.desire_recover_effect(bound(), evidence())


def truth(expression, **facts):
    return evaluate_expression(expression, None, facts).truth


class ProofMetadata:
    def __init__(self):
        proof = desire.receipt()
        self.records = {}
        for index, row in enumerate(proof["methods"]):
            self.records.setdefault(row["type"], {}).setdefault("methods", {})[
                row["methodBaseName"] + str(9000 + index)
            ] = dict(
                function=row["address"],
                returns=dict(type=row["returns"]),
                impl_flags=row["implFlags"],
                params=[
                    dict(type=kind, **({"modifier": modifier} if modifier else {}))
                    for kind, modifier in zip(
                        row["parameters"], row["parameterModifiers"]
                    )
                ],
            )
        for row in proof["fieldChecks"]:
            self.records.setdefault(row["type"], {}).setdefault("fields", {})[
                row["field"]
            ] = dict(type=row["fieldType"], offset_from_base=row["offset"])
        for row in proof["enumChecks"]:
            self.records.setdefault(row["type"], {}).setdefault("fields", {})[
                row["field"]
            ] = dict(default=row["value"])
        self.records["app.cEnemyBTableCommandWork"]["address"] = "0x1234560"

    def get(self, name):
        return self.records.get(name)

    def fields(self, name):
        return self.records.get(name, {}).get("fields", {})


class ProofPE:
    def __init__(self):
        self.ranges = {
            int(row["address"], 16): bytes.fromhex(row["nativeBytes"])
            for row in desire.receipt()["methods"]
        }
        self.class_pointer = 0x1234560

    def read(self, address, size):
        for start, data in self.ranges.items():
            if start <= address < start + len(data):
                return data[address - start : address - start + size]
        if size == 8:
            return self.class_pointer.to_bytes(8, "little")
        return b""


class DesireRecoverTests(unittest.TestCase):
    def test_machine_keeps_boundary_before_normal_return_tail_writes(self):
        import hashlib
        from types import SimpleNamespace
        from sdk.enemy_logic_exporter.shared.logic.machine import Machine

        native = bytes.fromhex("b801000000c3")
        row = dict(
            type="fixture",
            method="caller",
            address="0x1000",
            end=hex(0x1000 + len(native)),
            nativeSha256=hashlib.sha256(native).hexdigest(),
        )
        machine = Machine(
            row, native, SimpleNamespace(read=lambda *_: b""), {}, [], {}, {}
        )
        detail = effect()
        entry = machine.desire_command_nodes(
            "request",
            dict(nativeSite="0xffb"),
            detail,
            dict(site="0xffb", arguments=[None]),
            0x1000,
            machine.initial(0),
        )
        guard = machine.nodes[entry]
        partial = machine.nodes[guard["true"]]
        boundary = machine.nodes[partial["next"]]
        tail = machine.nodes[boundary["next"]]
        self.assertNotIn("resume", boundary)
        self.assertEqual(boundary["continuationKind"], "normal_return")
        self.assertNotIn("stateUpdates", partial)
        self.assertFalse(partial["commandEffectsComplete"])
        self.assertEqual(boundary["kind"], "unknown")
        self.assertEqual(tail["stateUpdates"], desire.STATE_UPDATES)
        self.assertEqual(tail["next"], guard["false"])
        self.assertEqual(machine.nodes[guard["false"]]["kind"], "return")

    def test_request_guard_keeps_missing_state_and_mask_semantics(self):
        guard = effect()["requestGuard"]
        self.assertIsNone(truth(guard))
        self.assertIs(truth(guard, enemy_command_work_valid=False), False)
        self.assertIs(
            truth(
                guard, enemy_command_work_valid=True, btable_request_action_mask=True
            ),
            False,
        )
        self.assertIs(
            truth(
                guard, enemy_command_work_valid=True, btable_request_action_mask=False
            ),
            True,
        )

    def test_actor_network_ownership_only_controls_core_request(self):
        result = effect()
        guard = result["actorRequestGuard"]
        self.assertIsNone(truth(guard))
        self.assertIs(truth(guard, request_actor_net_info_exists=False), True)
        self.assertIs(
            truth(
                guard,
                request_actor_net_info_exists=True,
                request_actor_host_member_index=-1,
            ),
            True,
        )
        self.assertIs(
            truth(
                guard,
                request_actor_net_info_exists=True,
                request_actor_host_member_index=2,
                request_actor_self_member_index=2,
            ),
            True,
        )
        self.assertIs(
            truth(
                guard,
                request_actor_net_info_exists=True,
                request_actor_host_member_index=2,
                request_actor_self_member_index=1,
            ),
            False,
        )
        self.assertTrue(
            all(
                "independent of actorRequestGuard" in row["applyWhen"]
                for row in result["requestEffects"]
            )
        )

    def test_source_guid_never_becomes_final_action_identity(self):
        result = effect()
        self.assertEqual(result["requestSource"]["actionGuid"], SOURCE_GUID)
        self.assertFalse(result["requestSource"]["finalActionIdentityKnown"])
        self.assertEqual(result["convertedActionId"]["status"], "unknown")
        self.assertFalse(result["convertedActionId"]["resourceGuidIsFinalIdentity"])
        self.assertFalse(result["commandEffectsComplete"])
        for key in ("action", "dynamicAction", "resume", "success"):
            self.assertNotIn(key, result)

    def test_unread_edit_type_cannot_change_mode_or_labels(self):
        original = bound()
        changed = deepcopy(original)
        changed["argument"]["_EditType"] = "not even a valid enum"
        self.assertEqual(
            desire.desire_recover_effect(original, evidence()),
            desire.desire_recover_effect(changed, evidence()),
        )
        self.assertFalse(effect()["requestSource"]["editTypeReadByCommand"])
        self.assertNotIn("AREAMOVE", effect()["summary"])
        self.assertNotIn("SLEEP", effect()["summary"])

    def test_three_tail_writes_wait_for_normal_return_and_are_not_history(self):
        result = effect()
        self.assertEqual(
            result["stateUpdates"],
            {
                "context:_FlagArray[WAITING_REQUEST_ACTION_RANDOM_OPERATOR]": False,
                "context:Life._IsRequestClearLifeActInfo": True,
                "context:_FlagArray[NO_REQUEST_ACTION]": False,
            },
        )
        self.assertEqual(
            result["stateUpdateTiming"], "after_unresolved_boundary_normal_return"
        )
        self.assertFalse(result["stateUpdatesPersistent"])
        self.assertTrue(result["invalidateSnapshot"])
        self.assertEqual(
            {row["key"]: row["value"] for row in result["writeFacts"]},
            result["stateUpdates"],
        )
        self.assertEqual(result["returnType"], "System.Void")
        self.assertEqual(result["continuationStatus"], "native_caller_continuation")

    def test_queue_is_not_immediate_or_success_boolean(self):
        contract = effect()["actorRequestContract"]
        self.assertEqual(contract["arguments"]["branchedParamIndex"], -1)
        self.assertFalse(contract["arguments"]["immediate"])
        self.assertEqual(
            contract["queue"]["callee"]["methodBaseName"], "changeActionRequest"
        )
        self.assertFalse(contract["actionStartedOrCompleted"])

    def test_cache_and_field_pitfall_boundaries_remain_explicit(self):
        result = effect()
        self.assertEqual(result["argumentCacheBoundary"]["status"], "unresolved")
        self.assertEqual(result["conversionBoundary"]["status"], "unresolved")
        self.assertIn("FieldPitfall", result["implementationBoundary"])
        self.assertIn(
            "IsActivatedByScar=false",
            result["conversionBoundary"]["fieldPitfall"]["possibleWrites"],
        )
        self.assertTrue(result["implementationBoundary"])

    def test_exact_real_resource_argument_is_bound_without_relabeling_mode(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "MHWS-in-json/natives/STM/GameDesign/Enemy/Em0002/50/BTable/Em0002_50_BTable_DepletionRetryCharge.user.3.json"
        )
        body = next(iter(json.loads(source.read_text(encoding="utf8"))[0].values()))
        argument_type, argument = next(iter(body["_CommandArgArray"][7].items()))
        self.assertEqual(argument_type, desire.ARGUMENT)
        result = desire.desire_recover_effect(
            dict(
                commandType=desire.COMMAND,
                argumentType=argument_type,
                argument=argument,
            ),
            evidence(),
        )
        self.assertEqual(result["requestSource"]["actionGuid"], SOURCE_GUID)
        self.assertEqual(result["requestSource"]["assetIndex"], 0)
        self.assertEqual(result["convertedActionId"]["status"], "unknown")

    def test_invalid_evidence_or_arguments_are_rejected(self):
        self.assertIsNone(desire.desire_recover_effect(dict(commandType="other"), None))
        bad = evidence()
        bad["method"] = "different1234"
        with self.assertRaises(ValueError):
            desire.desire_recover_effect(bound(), bad)
        bad = bound()
        bad["argumentType"] = "app.btable.EmCommonCommand.cSelectActionArg"
        with self.assertRaises(ValueError):
            desire.desire_recover_effect(bad, evidence())
        bad = bound()
        bad["argument"].pop("_EditActionGuid")
        with self.assertRaises(desire.MissingState):
            desire.desire_recover_effect(bad, evidence())

    def test_verifier_accepts_changed_numeric_method_suffixes(self):
        metadata, pe = ProofMetadata(), ProofPE()
        self.assertTrue(desire.verify_desire_recover(pe, metadata))
        row = evidence()
        row["method"] = "onExecute999999"
        self.assertIsNotNone(
            desire.desire_recover_effect(bound(), row, metadata=metadata, pe=pe)
        )

    def test_verifier_rejects_changed_bytes_fields_enum_and_type_guard(self):
        metadata, pe = ProofMetadata(), ProofPE()
        first = desire.receipt()["methods"][0]
        start = int(first["address"], 16)
        pe.ranges[start] = b"\x90" + pe.ranges[start][1:]
        with self.assertRaises(ValueError):
            desire.verify_desire_recover(pe, metadata)
        metadata, pe = ProofMetadata(), ProofPE()
        row = desire.receipt()["fieldChecks"][0]
        metadata.fields(row["type"])[row["field"]]["offset_from_base"] = "0x1"
        with self.assertRaises(ValueError):
            desire.verify_desire_recover(pe, metadata)
        metadata, pe = ProofMetadata(), ProofPE()
        metadata.fields("app.EnemyDef.FLAG_BIT")["NO_REQUEST_ACTION"]["default"] = 51
        with self.assertRaises(ValueError):
            desire.verify_desire_recover(pe, metadata)
        metadata, pe = ProofMetadata(), ProofPE()
        pe.class_pointer = 0
        with self.assertRaises(ValueError):
            desire.verify_desire_recover(pe, metadata)


if __name__ == "__main__":
    unittest.main()
