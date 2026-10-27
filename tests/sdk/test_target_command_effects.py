"""Target writes keep native guards, exception exits, and distinct angle units."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sdk.enemy_logic_exporter.monster import em0070_00_0 as spider
from sdk.enemy_logic_exporter.monster import em0154_00_0 as flower_spider
from sdk.enemy_logic_exporter.shared.logic.expressions import evaluate_expression
from sdk.enemy_logic_exporter.shared.logic import target_command_effects as targets


def evidence(name):
    row = targets.target_receipt(name)["methods"][0]
    return {key: row[key] for key in ("type", "method", "address", "end")}


def side_walk(module=spider, angle=30.0):
    bound = dict(
        commandType=module.SIDE_WALK_COMMAND,
        argumentType=module.SIDE_WALK_ARGUMENT,
        argument={"_EditSideWalkAngle": {"ace.btable.cEditFieldFloat": angle}},
    )
    return module.recover_target_command_effect(
        bound, evidence(module.SIDE_WALK_RECEIPT)
    )


def obstacle():
    return targets.reviewed_target_command_effect(
        dict(commandType=targets.OBSTACLE_COMMAND, argumentType="", argument={}),
        evidence(targets.OBSTACLE_RECEIPT),
    )


def truth(expression, **facts):
    return evaluate_expression(expression, None, facts).truth


class ProofMetadata:
    def __init__(self, proof):
        self.records = {}
        for row in proof["methods"]:
            self.records.setdefault(row["type"], {}).setdefault("methods", {})[
                row["method"]
            ] = dict(
                function=row["address"],
                returns=dict(type=row["returns"]),
                params=[dict(type=value) for value in row["parameters"]],
            )
        for row in proof["fieldChecks"]:
            self.records.setdefault(row["type"], {}).setdefault("fields", {})[
                row["field"]
            ] = dict(type=row["fieldType"], offset_from_base=row["offset"])
        for row in proof["enumChecks"]:
            self.records.setdefault(row["type"], {})["fields"] = {
                key: dict(default=value) for key, value in row["values"].items()
            }
        for index, row in enumerate(proof["classSymbols"]):
            self.records.setdefault(row["type"], {})["address"] = hex(
                0x10000 + index * 8
            )

    def get(self, owner):
        return self.records.get(owner)

    def fields(self, owner):
        return self.records.get(owner, {}).get("fields", {})


class ProofPE:
    def __init__(self, proof, metadata):
        self.ranges = {
            int(row["address"], 16): bytes.fromhex(row["nativeBytes"])
            for row in [*proof["methods"], *proof["nativeProofs"], *proof["constants"]]
        }
        for row in proof["classSymbols"]:
            if "sourceType" in row:
                from capstone import Cs, CS_ARCH_X86, CS_MODE_64

                source = next(
                    method
                    for method in proof["methods"]
                    if method["type"] == row["sourceType"]
                    and method["method"].startswith(row["sourceMethod"])
                )
                offset = int(row["instructionOffset"], 16)
                decoder = Cs(CS_ARCH_X86, CS_MODE_64)
                decoder.detail = True
                ins = next(
                    decoder.disasm(
                        bytes.fromhex(source["nativeBytes"])[offset : offset + 16],
                        int(source["address"], 16) + offset,
                    )
                )
                slot = ins.address + ins.size + ins.operands[1].mem.disp
            else:
                slot = int(row["slot"], 16)
            self.ranges[slot] = int(metadata.get(row["type"])["address"], 16).to_bytes(
                8, "little"
            )

    def read(self, address, size):
        for start, data in self.ranges.items():
            if start <= address < start + len(data):
                return data[address - start : address - start + size]
        return b""


class TargetCommandEffectsTests(unittest.TestCase):
    def target_graph(self, native):
        from sdk.enemy_logic_exporter.shared.logic.machine import Machine

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
        entry = machine.target_command_nodes(
            "command",
            dict(nativeSite="0xffb"),
            side_walk(),
            dict(arguments=[None]),
            0x1000,
            machine.initial(0),
        )
        return machine, entry

    def test_native_caller_result_branch_and_exception_do_not_rejoin(self):
        # test al,al; jz false; mov eax,1; ret; xor eax,eax; ret
        machine, entry = self.target_graph(bytes.fromhex("84c07406b801000000c331c0c3"))
        guard = machine.nodes[entry]
        references = machine.nodes[guard["true"]]
        update = machine.nodes[references["true"]]
        self.assertIs(machine.nodes[guard["false"]]["value"], False)
        self.assertIs(machine.nodes[update["next"]]["value"], True)
        failure = machine.nodes[references["false"]]
        self.assertEqual(failure["boundaryKind"], "native_exception")
        self.assertNotIn("next", failure)
        self.assertNotIn("resume", failure)

    def test_ignored_callee_boolean_rejoins_actual_caller(self):
        machine, entry = self.target_graph(bytes.fromhex("b801000000c3"))
        guard = machine.nodes[entry]
        references = machine.nodes[guard["true"]]
        update = machine.nodes[references["true"]]
        self.assertEqual(guard["false"], update["next"])

    def test_side_walk_guard_mismatch_is_false_without_invented_success_input(self):
        result = side_walk()
        self.assertIs(
            truth(result["returnExpression"], enemy_command_work_valid=False), False
        )
        self.assertIs(
            truth(
                result["returnExpression"],
                enemy_command_work_valid=True,
                self_extend_valid=False,
            ),
            False,
        )
        self.assertIsNone(truth(result["returnExpression"]))
        self.assertEqual(result["returnType"], "System.Boolean")
        self.assertNotIn("side_walk_success", result["inputDefinitions"])

    def test_side_walk_transform_failure_is_an_exception_after_true_guard(self):
        result = side_walk()
        facts = dict(enemy_command_work_valid=True, self_extend_valid=True)
        self.assertIs(truth(result["returnExpression"], **facts), True)
        self.assertIsNone(truth(result["normalPrecondition"], **facts))
        self.assertIs(
            truth(
                result["normalPrecondition"],
                **{targets.TRANSFORM_KEY: False},
            ),
            False,
        )
        self.assertTrue(result["exceptionBoundary"])
        self.assertIn("不是普通 false", result["exceptionBoundary"])
        self.assertEqual(result["exceptionContract"]["explicitNullErrorCode"], 70)

    def test_two_writes_preserve_original_target_and_order(self):
        mutation = side_walk()["targetMutation"]
        self.assertEqual(mutation["effect"], "update_target_positions")
        self.assertTrue(mutation["invalidateTargetSnapshot"])
        first, second = mutation["targetUpdates"]
        self.assertEqual(
            [(row["order"], row["category"]) for row in (first, second)],
            [(0, 18), (1, 18)],
        )
        self.assertEqual(first["position"]["kind"], "native_vector_formula")
        self.assertIn("f32(T + f32(P - T))", first["position"]["formula"])
        self.assertTrue(second["position"]["capturedBeforeFirstWrite"])
        for row in (first, second):
            self.assertEqual(row["booleanOptions"], [False])
            self.assertEqual(row["targetSubCategory"], 0)
            self.assertIsNone(row["nullableUInt32"])

    def test_native_angle_operations_are_not_unified_between_monsters(self):
        def angle(result):
            return result["targetMutation"]["targetUpdates"][0]["position"]["angle"]

        spider_angle = angle(side_walk(spider, 30))
        flower_spider_angle = angle(side_walk(flower_spider, 0.8))
        self.assertEqual(len(spider_angle["operations"]), 3)
        self.assertEqual(len(flower_spider_angle["operations"]), 1)
        self.assertAlmostEqual(spider_angle["radians"], 1.6449341773986816)
        self.assertAlmostEqual(flower_spider_angle["radians"], 2.5132741928100586)
        self.assertLess(angle(side_walk(spider, -30))["radians"], 0)
        self.assertEqual(angle(side_walk(flower_spider, 0))["radians"], 0)

    def test_side_walk_evidence_only_names_its_six_dependencies_and_own_methods(self):
        expected = {
            ("app.cEnemyBTableCommandWork", "get_TargetPosition577920"),
            ("app.cEnemyBTableCommandWork", "setTargetPosition577942"),
            ("app.cEmModuleTarget", "setTarget544366"),
            ("via.MathEx", "rotationAxis1028658"),
            ("via.vec3", "op_Addition1752"),
            ("via.vec3", "op_Subtraction1754"),
        }
        for module in (spider, flower_spider):
            rows = side_walk(module)["targetMutation"]["semanticEvidence"]
            own = {
                (row["type"], row["method"])
                for row in targets.target_receipt(module.SIDE_WALK_RECEIPT)["methods"]
            }
            self.assertEqual(len(rows), 8)
            self.assertEqual(
                {(row["type"], row["method"]) for row in rows}, expected | own
            )
            self.assertFalse(
                any(row["type"] == targets.OBSTACLE_COMMAND for row in rows)
            )
            self.assertFalse(
                any(
                    row["method"] in {"getParam268556", "op_Multiply1756"}
                    for row in rows
                )
            )

    def test_missing_side_walk_dependency_is_rejected(self):
        original = targets.target_receipt
        incomplete = deepcopy(original(targets.OBSTACLE_RECEIPT))
        incomplete["methods"] = [
            row
            for row in incomplete["methods"]
            if row["method"] != "get_TargetPosition577920"
        ]
        with patch.object(
            targets,
            "target_receipt",
            side_effect=lambda name: (
                incomplete if name == targets.OBSTACLE_RECEIPT else original(name)
            ),
        ):
            with self.assertRaisesRegex(ValueError, "六项辅助方法证据不完整"):
                side_walk()

    def test_real_resources_bind_their_own_parameter_type_and_angle(self):
        root = (
            Path(__file__).resolve().parents[2]
            / "MHWS-in-json/natives/STM/GameDesign/Enemy"
        )
        for module, enemy, index, expected in (
            (spider, "Em0070", 191, -30),
            (flower_spider, "Em0154", 134, -0.8),
        ):
            source = (
                root
                / enemy
                / "00/BTable"
                / f"{enemy}_00_BTable_CommonAttack.user.3.json"
            )
            body = next(iter(json.loads(source.read_text(encoding="utf8"))[0].values()))
            argument_type, argument = next(
                iter(body["_CommandArgArray"][index].items())
            )
            self.assertEqual(argument_type, module.SIDE_WALK_ARGUMENT)
            result = module.recover_target_command_effect(
                dict(
                    commandType=module.SIDE_WALK_COMMAND,
                    argumentType=argument_type,
                    argument=argument,
                ),
                evidence(module.SIDE_WALK_RECEIPT),
            )
            actual = result["targetMutation"]["targetUpdates"][0]["position"]["angle"]
            self.assertEqual(actual["resourceValue"], expected)

    def test_obstacle_guard_only_uses_native_reference_checks_and_type(self):
        result = obstacle()
        valid = dict(
            enemy_command_work_valid=True,
            **{
                targets.CHARACTER_KEY: True,
                targets.GAME_OBJECT_KEY: True,
                targets.OBSTACLE_TYPE_KEY: 3,
            },
        )
        self.assertIs(truth(result["returnExpression"], **valid), True)
        self.assertIs(
            truth(
                result["returnExpression"],
                **dict(valid, **{targets.OBSTACLE_TYPE_KEY: 2}),
            ),
            False,
        )
        self.assertIs(
            truth(
                result["returnExpression"],
                **dict(valid, **{targets.CHARACTER_KEY: False}),
            ),
            False,
        )
        self.assertIsNone(truth(result["normalPrecondition"]))
        self.assertTrue(result["exceptionBoundary"])
        self.assertIs(
            truth(result["normalPrecondition"], **{targets.CURRENT_NODE_KEY: False}),
            False,
        )

    def test_obstacle_formula_preserves_unknown_height_source(self):
        mutation = obstacle()["targetMutation"]
        self.assertEqual(len(mutation["targetUpdates"]), 1)
        update = mutation["targetUpdates"][0]
        self.assertEqual((update["category"], update["order"]), (10, 0))
        self.assertEqual(update["booleanOptions"], [False, True])
        position = update["position"]
        self.assertEqual(position["sources"]["N"], "Context.Obstacle.WallNode.Normal")
        height = position["sources"]["h"]
        self.assertFalse(height["fieldNameVerified"])
        self.assertEqual(height["path"][-1]["readFloatOffset"], "0x78")
        self.assertTrue(mutation["invalidateTargetSnapshot"])

    def test_wrong_command_or_native_evidence_is_not_accepted(self):
        self.assertIsNone(
            targets.reviewed_target_command_effect(dict(commandType="other"), {})
        )
        self.assertIsNone(
            spider.recover_target_command_effect(
                dict(commandType=flower_spider.SIDE_WALK_COMMAND),
                evidence(flower_spider.SIDE_WALK_RECEIPT),
            )
        )
        wrong = evidence(targets.OBSTACLE_RECEIPT)
        wrong["address"] = "0x0"
        with self.assertRaises(ValueError):
            targets.reviewed_target_command_effect(
                dict(commandType=targets.OBSTACLE_COMMAND), wrong
            )
        with self.assertRaises(ValueError):
            spider.recover_target_command_effect(
                dict(
                    commandType=spider.SIDE_WALK_COMMAND,
                    argumentType=flower_spider.SIDE_WALK_ARGUMENT,
                    argument={},
                ),
                evidence(spider.SIDE_WALK_RECEIPT),
            )

    def test_current_recipe_contract_rejects_changed_native_and_metadata(self):
        for name in (
            targets.OBSTACLE_RECEIPT,
            spider.SIDE_WALK_RECEIPT,
            flower_spider.SIDE_WALK_RECEIPT,
        ):
            proof = deepcopy(targets.target_receipt(name))
            metadata = ProofMetadata(proof)
            pe = ProofPE(proof, metadata)
            self.assertTrue(targets.verify_target_receipt(pe, metadata, name))
            address = int(proof["methods"][0]["address"], 16)
            original = pe.ranges[address]
            pe.ranges[address] = bytes([original[0] ^ 1]) + original[1:]
            with self.assertRaises(ValueError):
                targets.verify_target_receipt(pe, metadata, name)
            pe.ranges[address] = original
            row = proof["fieldChecks"][0]
            metadata.fields(row["type"])[row["field"]]["offset_from_base"] = "0x1"
            with self.assertRaises(ValueError):
                targets.verify_target_receipt(pe, metadata, name)


if __name__ == "__main__":
    unittest.main()
