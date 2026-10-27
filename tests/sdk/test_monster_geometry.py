"""Scene facts stay separate from ray/capsule commands and timer thresholds."""

from pathlib import Path
import unittest

from sdk.enemy_logic_exporter.monster import em0046_00_0 as sea
from sdk.enemy_logic_exporter.monster import em0078_00_0 as hill
from sdk.enemy_logic_exporter.shared.logic.expressions import evaluate_expression
from sdk.enemy_logic_exporter.shared.models.player_view import (
    PlayerCompiler,
    build_player_view,
)
from sdk.enemy_logic_exporter.shared.resources.reader import Resources, typed


def evaluate(result, **facts):
    context = dict(enemy_command_work_valid=True, self_extend_valid=True)
    context.update(facts)
    return evaluate_expression(result["expression"], None, context).truth


class UniqueResources:
    def __init__(self, level2=40.0, level3=20.0):
        self.rates = dict(_Level2UpTimeRate=level2, _Level3UpTimeRate=level3)

    def package_value(self, enemy, spec):
        if enemy != sea.ENEMY_ID or spec != sea.SWIM_UNIQUE_SPEC:
            raise ValueError("wrong resource scope")
        return self.rates, ["stage-resident", "own-unique"]


def phase(mode, resources=None):
    return sea.recover_condition(
        dict(
            commandType=sea.SWIM_PHASE_COMMAND,
            argumentType=sea.SWIM_PHASE_ARGUMENT,
            argument={"_SwimCombatPhase": mode},
        ),
        sea.ENEMY_ID,
        resources or UniqueResources(),
    )


class FakeMetadata:
    def __init__(self, proof):
        self.records = {}
        for row in proof["methods"]:
            self.records.setdefault(row["type"], {}).setdefault("methods", {})[
                row["method"]
            ] = dict(
                function=row["address"],
                returns=dict(type=row["returns"]),
                params=[dict(type=name) for name in row["parameters"]],
            )
        for row in proof["fieldChecks"]:
            self.records.setdefault(row["type"], {}).setdefault("fields", {})[
                row["field"]
            ] = dict(
                type=row["fieldType"],
                offset_from_base=row["offset"],
            )
        for row in proof["enumChecks"]:
            self.records.setdefault(row["type"], {})["fields"] = {
                key: dict(default=value) for key, value in row["values"].items()
            }
        for index, row in enumerate(proof["classSymbols"]):
            self.records.setdefault(row["type"], {})["address"] = hex(
                0x10000 + index * 8
            )
        if "queryMethod" in proof:
            row = proof["queryMethod"]
            self.records.setdefault(row["type"], {}).setdefault("methods", {})[
                row["method"]
            ] = dict(
                function=row["address"],
                returns=dict(type="System.Boolean"),
                params=[
                    dict(type=name)
                    for name in (
                        "List<DATA_INFO>",
                        "via.Capsule",
                        "Func<DATA_INFO,bool>",
                    )
                ],
            )

    def get(self, owner):
        return self.records.get(owner)

    def fields(self, owner):
        return self.records.get(owner, {}).get("fields", {})


class FakePE:
    def __init__(self, proof, metadata):
        self.ranges = {
            int(row["address"], 16): bytes.fromhex(row["nativeBytes"])
            for row in [*proof["methods"], *proof["nativeProofs"], *proof["constants"]]
        }
        for row in proof["classSymbols"]:
            self.ranges[int(row["slot"], 16)] = int(
                metadata.get(row["type"])["address"], 16
            ).to_bytes(8, "little")

    def read(self, address, count):
        for start, value in self.ranges.items():
            if start <= address and address + count <= start + len(value):
                return value[address - start : address - start + count]
        return b""


class MonsterGeometryTests(unittest.TestCase):
    def test_water_uses_all_contact_classifications_without_inventing_names(self):
        result = sea.recover_condition(
            dict(commandType=sea.ON_WATER_COMMAND), sea.ENEMY_ID, None
        )
        fields = result["queryContracts"][0]["resultFields"]
        for code in ("hasUserDataCode1", "hasUserDataCode2"):
            facts = {fields["hasContacts"]: True, fields[code]: True}
            self.assertIs(evaluate(result, **facts), True)
        self.assertIs(evaluate(result, **{fields["hasContacts"]: False}), False)
        self.assertIsNone(evaluate(result, **{fields["hasContacts"]: True}))
        self.assertIs(
            evaluate(
                result,
                **{
                    fields["hasContacts"]: True,
                    fields["hasUserDataCode1"]: False,
                    fields["hasUserDataCode2"]: False,
                }
            ),
            False,
        )
        contract = result["queryContracts"][0]
        self.assertEqual(contract["startOffset"], [0, 3, 0])
        self.assertEqual(contract["endOffset"], [0, -3, 0])
        self.assertEqual(contract["filterOverrides"], dict(Layer=14, MaskBits=0))
        self.assertFalse(contract["userdataCategoryNamesVerified"])
        self.assertEqual(contract["optionsEnabled"], ["NearSort", "AllHits"])

    def test_hill_checks_nearest_eligible_item_after_query_not_any_hill(self):
        result = hill.recover_condition(
            dict(commandType=hill.HILL_COMMAND), hill.ENEMY_ID, None
        )
        contract = result["queryContracts"][0]
        fields = contract["resultFields"]
        facts = {key: True for key in fields.values()}
        self.assertIs(evaluate(result, **facts), True)
        for key in fields.values():
            with self.subTest(failed=key):
                self.assertIs(evaluate(result, **dict(facts, **{key: False})), False)
        self.assertIsNone(evaluate(result, **{fields["targetAvailable"]: True}))
        self.assertEqual(
            contract["capsule"],
            dict(startOffset=[0, 0, 0], endOffset=[0, -3, 0], radius=4.5),
        )
        self.assertTrue(contract["attributeTest"]["selectedItemOnly"])
        self.assertEqual(contract["attributeTest"]["mask"], 0x2000)
        self.assertIn("严格小于", contract["nearestSelection"])
        self.assertIn("Q.y <= P.y + 1", contract["candidateHeight"])

    def test_swim_phase_time_boundaries_levels_and_missing_values(self):
        for mode, boundary in ((0, 40.0), (1, 20.0)):
            result = phase(mode)
            facts = {
                sea.SWIM_PHASE_KEY: True,
                sea.SWIM_LEVEL_KEY: 1,
                sea.SWIM_REMAINING_KEY: boundary,
            }
            self.assertIs(evaluate(result, **facts), True)
            self.assertIs(
                evaluate(
                    result, **dict(facts, **{sea.SWIM_REMAINING_KEY: boundary + 0.001})
                ),
                False,
            )
            missing = dict(facts)
            del missing[sea.SWIM_REMAINING_KEY]
            self.assertIsNone(evaluate(result, **missing))
            self.assertIs(evaluate(result, **{sea.SWIM_PHASE_KEY: False}), False)
        self.assertIs(
            evaluate(
                phase(0),
                **{
                    sea.SWIM_PHASE_KEY: True,
                    sea.SWIM_LEVEL_KEY: 2,
                    sea.SWIM_REMAINING_KEY: 0,
                }
            ),
            False,
        )
        for level in (0, 1, 2):
            self.assertIs(
                evaluate(
                    phase(1),
                    **{
                        sea.SWIM_PHASE_KEY: True,
                        sea.SWIM_LEVEL_KEY: level,
                        sea.SWIM_REMAINING_KEY: -10,
                    }
                ),
                True,
            )
        self.assertIs(
            evaluate(
                phase(1),
                **{
                    sea.SWIM_PHASE_KEY: True,
                    sea.SWIM_LEVEL_KEY: 3,
                    sea.SWIM_REMAINING_KEY: -10,
                }
            ),
            False,
        )

    def test_swim_finish_uses_timeout_flag_and_preserves_unknown(self):
        result = phase(2)
        facts = {sea.SWIM_PHASE_KEY: True, sea.SWIM_LEVEL_KEY: 3}
        self.assertIsNone(evaluate(result, **facts))
        self.assertIs(
            evaluate(result, **dict(facts, **{sea.SWIM_TIMEOUT_KEY: True})), True
        )
        self.assertIs(
            evaluate(result, **dict(facts, **{sea.SWIM_TIMEOUT_KEY: False})), False
        )

    def test_timer_contract_and_resource_thresholds_are_not_hardcoded_results(self):
        result = phase(0, UniqueResources(level2=37.5))
        facts = {
            sea.SWIM_PHASE_KEY: True,
            sea.SWIM_LEVEL_KEY: 1,
            sea.SWIM_REMAINING_KEY: 38,
        }
        self.assertIs(evaluate(result, **facts), False)
        contract = result["queryContracts"][0]
        self.assertEqual(contract["epsilon"], 1.1920928955078125e-7)
        self.assertEqual(
            [row["condition"] for row in contract["progressBranches"]],
            ["t <= epsilon", "L <= epsilon", "otherwise"],
        )
        self.assertEqual(
            contract["remainingRate"], "float32(100.0 - double(progress) * 100.0)"
        )
        self.assertFalse(contract["clamped"])
        definition = result["inputDefinitions"][sea.SWIM_REMAINING_KEY]
        self.assertLess(definition["numericRange"]["min"], 0)
        self.assertIsNone(definition["numericRange"]["max"])

    def test_remaining_rate_threshold_options_survive_actual_player_compile(self):
        result = phase(1)
        view = build_player_view(
            dict(
                enemyId=sea.ENEMY_ID,
                entry="t",
                tables=[
                    dict(
                        tableGuid="t",
                        entry="n",
                        nodes=[dict(result, kind="condition", id="n")],
                    )
                ],
                rules=dict(rules=[]),
            )
        )
        definition = view["inputs"][sea.SWIM_REMAINING_KEY]
        values = [option["value"] for option in definition["options"]]
        self.assertTrue(values)
        for point in (20, 40):
            self.assertIn(
                dict(min=point, max=point, minClosed=True, maxClosed=True), values
            )
        self.assertTrue(
            any(
                value["min"] < 0 and value["max"] == 0 and not value["maxClosed"]
                for value in values
            )
        )
        self.assertIn(dict(min=40, max=None, minClosed=False, maxClosed=False), values)
        self.assertEqual(
            definition["numericRange"], dict(min=-3.4028234663852886e38, max=None)
        )
        self.assertEqual(definition["unit"], "%")

    def test_phase_thresholds_follow_own_stage_resident_unique_reference(self):
        root = Path(__file__).resolve().parents[2] / "MHWS-in-json/natives"
        resources = Resources(root)
        result = phase(0, resources)
        source = result["thresholdSources"][0]
        self.assertEqual(source["values"]["_Level2UpTimeRate"], 40)
        self.assertEqual(source["values"]["_Level3UpTimeRate"], 20)
        self.assertEqual(len(source["resources"]), 2)
        self.assertIn("Em0046_00_0_StageResident", source["resources"][0])
        self.assertIn("Em0046_00_Param_Unique", source["resources"][1])
        source = (
            "STM/GameDesign/Enemy/Em0046/00/BTable/Em0046_00_BTable_Combat.user.3.json"
        )
        table = resources.read(source)
        for index, mode in ((9, "[1] ELECTRIC_LEVEL_3"), (11, "[2] FINISH")):
            argument_type, argument = typed(table["_CommandArgArray"][index])
            self.assertEqual(argument_type, sea.SWIM_PHASE_ARGUMENT)
            self.assertEqual(argument, {"_SwimCombatPhase": mode})
            node = dict(
                commandType=sea.SWIM_PHASE_COMMAND,
                argumentType=argument_type,
                argument=argument,
                argumentIndex=index,
                sourceResource=source,
            )
            recovered = sea.recover_condition(node, sea.ENEMY_ID, resources)
            self.assertIsNotNone(recovered)
            expected = sea.SWIM_REMAINING_KEY if index == 9 else sea.SWIM_TIMEOUT_KEY
            self.assertIn(expected, recovered["inputDefinitions"])

    def test_swim_phase_rejects_wrong_argument_shape_without_compatibility(self):
        node = dict(
            commandType=sea.SWIM_PHASE_COMMAND,
            argumentType=sea.SWIM_PHASE_ARGUMENT,
            argument={"_EditArg": "[1] ELECTRIC_LEVEL_3"},
        )
        self.assertIsNone(sea.recover_condition(node, sea.ENEMY_ID, UniqueResources()))
        node.update(
            argumentType="ace.btable.cCommandArgument1OnlyByEnum",
            argument={"_SwimCombatPhase": "[1] ELECTRIC_LEVEL_3"},
        )
        self.assertIsNone(sea.recover_condition(node, sea.ENEMY_ID, UniqueResources()))

    def test_conditions_compile_to_declared_inputs_without_final_result_boolean(self):
        for result in (
            phase(0),
            phase(2),
            sea._recover_on_water(dict(commandType=sea.ON_WATER_COMMAND)),
            hill._recover_dest_hill(dict(commandType=hill.HILL_COMMAND)),
        ):
            node = dict(result, kind="condition", id="n")
            compiler = PlayerCompiler(
                dict(tables=[dict(tableGuid="t", nodes=[node])], rules=dict(rules=[]))
            )
            expression = compiler.expression(result["expression"])
            self.assertEqual(expression["op"], "all")
            self.assertTrue(set(result["inputDefinitions"]).issubset(compiler.inputs))

    def test_native_bytes_fields_enums_and_constants_reject_changes(self):
        for module, proof in ((sea, sea._geometry_proof()), (hill, hill._hill_proof())):
            with self.subTest(module=module.ENEMY_ID):
                metadata = FakeMetadata(proof)
                pe = FakePE(proof, metadata)
                self.assertTrue(module.verify_native_recipes(pe, metadata))
                start = int(proof["constants"][0]["address"], 16)
                original = pe.ranges[start]
                pe.ranges[start] = bytes([original[0] ^ 1]) + original[1:]
                with self.assertRaises(ValueError):
                    module.verify_native_recipes(pe, metadata)
                pe = FakePE(proof, metadata)
                field = proof["fieldChecks"][0]
                metadata.fields(field["type"])[field["field"]][
                    "offset_from_base"
                ] = "0xffff"
                with self.assertRaises(ValueError):
                    module.verify_native_recipes(pe, metadata)
                metadata = FakeMetadata(proof)
                row = proof["enumChecks"][0]
                name = next(iter(row["values"]))
                metadata.fields(row["type"])[name]["default"] = -99
                with self.assertRaises(ValueError):
                    module.verify_native_recipes(pe, metadata)


if __name__ == "__main__":
    unittest.main()
