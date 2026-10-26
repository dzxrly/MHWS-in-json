"""Boundary regressions for reviewed count, terrain and state predicates."""

import unittest
from unittest.mock import patch

from sdk.enemy_logic_exporter.shared.logic.common_conditions import recover_condition
from sdk.enemy_logic_exporter.shared.logic.expressions import evaluate_expression
from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry
from sdk.enemy_logic_exporter.shared.logic.field_checks import (
    verify_recovered_conditions,
)


class UniqueParameters:
    def __init__(self, **values):
        self.values = values
        self.calls = []

    def package_value(self, enemy_id, spec):
        self.calls.append((enemy_id, spec))
        return self.values, ["StageResident.user.3.json", "Param_Unique.user.3.json"]


class RecoveredConditionTests(unittest.TestCase):
    def bind(self, command, argument=None, resources=None, enemy="EM0002_00_0"):
        return recover_condition(
            dict(commandType=command, argument=argument or {}), enemy, resources
        )

    def truth(self, node, **state):
        context = dict(
            enemy_command_work_valid=True,
            self_target_context_valid=True,
            self_extend_valid=True,
            **state,
        )
        return evaluate_expression(
            node["expression"], RuleRegistry.load(), context
        ).truth

    def test_reward_rank_is_separate_from_quest_and_legendary_rank(self):
        node = self.bind(
            "app.btable.EmCommonCommand.cCheckSelfType",
            {
                "_EditCategory": "[7] REWARD_RANK",
                "RewardRank": {"arg": {"_EditArg": "[10] REWARD_RANK_10"}},
            },
        )
        self.assertIsNone(
            self.truth(node, environment_current_rank=10, self_basic_legendary_id=10)
        )
        self.assertTrue(self.truth(node, self_effective_reward_rank=10))
        self.assertFalse(self.truth(node, self_effective_reward_rank=1))

    def test_depletion_readiness_is_not_active_or_tired(self):
        node = self.bind("app.btable.EmCommonCommand.cCheckDepletionReadyEnd")
        key = "context:Conditions.Depletion._IsReadyEndFrag"
        self.assertIsNone(self.truth(node, tired=True))
        self.assertTrue(self.truth(node, **{key: True, "tired": False}))
        self.assertFalse(self.truth(node, **{key: False, "tired": True}))
        state = dict(enemy_command_work_valid=False)
        self.assertFalse(
            evaluate_expression(node["expression"], RuleRegistry.load(), state).truth
        )

    def test_snow_squad_comparisons_include_equality_and_subtract_leader(self):
        for mode, expected in [
            (0, (False, True, True)),
            (1, (True, True, False)),
            (2, (False, True, False)),
        ]:
            node = self.bind(
                "app.btable.Em0022_00BTableCommand.cCheckEm1023Count",
                {"_EditCheckType": mode, "_EditCheckCount": {"int": 2}},
            )
            for index in (-1, 7):
                for actual, truth in zip((1, 2, 3), expected):
                    with self.subTest(mode=mode, leader=index, actual=actual):
                        self.assertIs(
                            self.truth(
                                node,
                                em0022_squad_extend_valid=True,
                                em0022_squad_member_count=actual + (index != -1),
                                em0022_squad_leader_system_index=index,
                            ),
                            truth,
                        )
        self.assertFalse(self.truth(node, em0022_squad_extend_valid=False))

    def test_servant_count_is_owned_valid_members(self):
        node = self.bind(
            "app.btable.Em0022_00BTableCommand.cCheckServantCount",
            {"_EditCheckType": 0, "_EditCheckCount": {"int": 1}},
        )
        self.assertFalse(self.truth(node, em0022_corps_found=False))
        self.assertIsNone(self.truth(node, em0022_corps_found=True))
        self.assertFalse(
            self.truth(node, em0022_corps_found=True, em0022_owned_servant_count=0)
        )
        self.assertTrue(
            self.truth(node, em0022_corps_found=True, em0022_owned_servant_count=1)
        )

    def test_frozen_wall_requires_successful_query_and_unmasked_wall(self):
        node = self.bind(
            "app.btable.Em0162_00BTableCommand.cCheckDestWall",
            {"_CheckDest": {"float": 8.0}},
        )
        self.assertFalse(self.truth(node, em0162_active_wall_query_found=False))
        self.assertFalse(
            self.truth(
                node, em0162_active_wall_query_found=True, em0162_eligible_wall_count=0
            )
        )
        state = dict(em0162_active_wall_query_found=True, em0162_eligible_wall_count=1)
        self.assertTrue(
            self.truth(node, **state, em0162_nearest_eligible_wall_distance=8.0)
        )
        self.assertFalse(
            self.truth(node, **state, em0162_nearest_eligible_wall_distance=8.01)
        )

    def test_frozen_gimmick_uses_self_horizontal_distance_inclusive(self):
        node = self.bind(
            "app.btable.Em0162_00BTableCommand.cCheckDestShutterGimmick",
            {"_CheckDest": {"float": 10.0}},
        )
        self.assertFalse(self.truth(node, em0162_shutter_gimmick_count=0))
        self.assertTrue(
            self.truth(
                node,
                em0162_shutter_gimmick_count=1,
                em0162_nearest_shutter_gimmick_xz=10.0,
            )
        )
        self.assertFalse(
            self.truth(
                node,
                em0162_shutter_gimmick_count=1,
                em0162_nearest_shutter_gimmick_xz=10.01,
            )
        )
        self.assertEqual(
            node["gimmickTypes"], ["GM607_000_00", "GM607_001_00", "GM601_000_00"]
        )

    def test_sea_hunter_count_is_not_total_quest_members(self):
        exact = self.bind(
            "app.btable.Em0046_00BTableCommand.cCheckSwimHunterNum",
            {"_CheckHunterNum": {"int": 1}},
        )
        any_hunter = self.bind("app.btable.Em0046_00BTableCommand.cCheckHunterInWater")
        self.assertIsNone(self.truth(exact, quest_members=1))
        self.assertTrue(self.truth(exact, em0046_hunters_in_water=1))
        self.assertFalse(self.truth(exact, em0046_hunters_in_water=2))
        self.assertTrue(self.truth(any_hunter, em0046_hunters_in_water=2))
        self.assertFalse(self.truth(any_hunter, em0046_hunters_in_water=0))

    def test_sea_story_is_one_specific_enabled_mission(self):
        node = self.bind("app.btable.Em0046_00BTableCommand.cIsStroyQuest")
        self.assertTrue(self.truth(node, enabled_main_mission_id=524))
        self.assertFalse(self.truth(node, enabled_main_mission_id=523))

    def test_doshaguma_health_threshold_is_strict_and_bound_to_stage_unique(self):
        resources = UniqueParameters(
            ModeChangeThreshold_Lower=45,
            ModeChangeThreshold_Upper=45,
            ModeChangeThreshold_Legendary=65,
        )
        node = self.bind(
            "app.btable.Em0150_00BTableCommand.cCheckModeChange",
            resources=resources,
            enemy="EM0150_00_0",
        )
        mode = "extend:app.cEm0150_00Extend.Mode"
        base = {mode: 0, "environment_current_rank": 1, "self_basic_legendary_id": 0}
        self.assertFalse(self.truth(node, **base, health_percent=45))
        self.assertTrue(self.truth(node, **base, health_percent=44.99))
        base["self_basic_legendary_id"] = 1
        self.assertTrue(self.truth(node, **base, health_percent=64.99))
        self.assertFalse(self.truth(node, **base, health_percent=65))
        base[mode] = 1
        self.assertFalse(self.truth(node, **base, health_percent=1))
        self.assertEqual(resources.calls[0][1]["fields"], ["_Unique", "_SpeciesInfo"])
        self.assertEqual(
            node["parameterSources"],
            ["StageResident.user.3.json", "Param_Unique.user.3.json"],
        )

    def test_arkveld_king_guard_and_strict_health_threshold(self):
        resources = UniqueParameters(UnleashModeChangeThreshold=75)
        node = self.bind(
            "app.Em0160_00BTableCommand.cCheckChangeMode",
            resources=resources,
            enemy="EM0160_50_0",
        )
        mode = "extend:app.cEm0160Extend._Mode"
        self.assertFalse(
            self.truth(
                node, **{mode: 0, "self_basic_legendary_id": 0, "health_percent": 1}
            )
        )
        self.assertFalse(
            self.truth(
                node, **{mode: 0, "self_basic_legendary_id": 2, "health_percent": 75}
            )
        )
        self.assertTrue(
            self.truth(
                node, **{mode: 0, "self_basic_legendary_id": 2, "health_percent": 74.99}
            )
        )
        self.assertFalse(
            self.truth(
                node, **{mode: 1, "self_basic_legendary_id": 2, "health_percent": 1}
            )
        )
        self.assertEqual(resources.calls[0][1]["fields"], ["_Unique", "_GenusInfo"])

    def test_mode_threshold_below_native_epsilon_disables_transition(self):
        node = self.bind(
            "app.Em0160_00BTableCommand.cCheckChangeMode",
            resources=UniqueParameters(UnleashModeChangeThreshold=0.0005),
            enemy="EM0160_00_0",
        )
        self.assertFalse(
            self.truth(
                node,
                **{
                    "extend:app.cEm0160Extend._Mode": 0,
                    "self_basic_legendary_id": 2,
                    "health_percent": 0,
                },
            )
        )

    def test_rey_dau_charge_requires_no_fatigue(self):
        node = self.bind("app.Em0156_00BTableCommand.cCheckTransRailgunChargeMax")
        key = "extend:app.cEm0156_00Extend._IsCanTransMaxRailgunCharge"
        self.assertTrue(self.truth(node, **{key: True, "tired": False}))
        self.assertFalse(self.truth(node, **{key: True, "tired": True}))
        self.assertFalse(self.truth(node, **{key: False, "tired": False}))

    def test_ajarakan_accumulation_threshold_is_inclusive(self):
        node = self.bind(
            "app.btable.Em0159_00BTableCommand.cCheckEnterBlazingMode",
            resources=UniqueParameters(BlazingModeThreshold=200),
            enemy="EM0159_00_0",
        )
        mode = "extend:app.cEm0159_00Extend._IsBlazingMode"
        value = "extend:app.cEm0159_00Extend._BlazingModeAccumulatedValue"
        self.assertTrue(self.truth(node, **{mode: False, value: 200, "tired": False}))
        self.assertFalse(
            self.truth(node, **{mode: False, value: 199.99, "tired": False})
        )
        self.assertFalse(self.truth(node, **{mode: True, value: 200, "tired": False}))
        self.assertFalse(self.truth(node, **{mode: False, value: 200, "tired": True}))

    def test_gore_first_health_branch_and_clamped_accumulation_levels(self):
        resources = UniqueParameters(
            SafeTransVital=45,
            SafeTransVital_Fes=53,
            TransformPointInfo=[
                {"level": {"TransformValue": v}} for v in (220, 210, 200)
            ],
        )
        node = self.bind(
            "app.btable.Em0071_00BTableCommand.cCheckStateChange",
            {"_EditArg": "[1] SUPER"},
            resources,
            "EM0071_00_0",
        )
        prefix = "extend:app.cEm0071_00Extend."
        base = {
            prefix + "_TransformedCount": 0,
            prefix + "<VirusValue>k__BackingField": 0,
            prefix + "<State>k__BackingField": 0,
            "tired": False,
            "em0071_basic_option_tag_low_bit": 0,
        }
        self.assertTrue(self.truth(node, **base, health_percent=44.99))
        self.assertFalse(self.truth(node, **base, health_percent=45))
        base["em0071_basic_option_tag_low_bit"] = 1
        self.assertTrue(self.truth(node, **base, health_percent=52.99))
        self.assertFalse(self.truth(node, **base, health_percent=53))
        for count, threshold in ((0, 220), (1, 210), (2, 200), (10, 200)):
            base[prefix + "_TransformedCount"] = count
            base[prefix + "<VirusValue>k__BackingField"] = threshold
            self.assertTrue(self.truth(node, **base, health_percent=100))
            base[prefix + "<VirusValue>k__BackingField"] = threshold - 0.01
            self.assertFalse(self.truth(node, **base, health_percent=100))
        base[prefix + "<State>k__BackingField"] = 2
        self.assertFalse(self.truth(node, **base, health_percent=1))

    def test_missing_required_inputs_stay_unknown_and_wrong_work_stops(self):
        node = self.bind(
            "app.btable.Em0162_00BTableCommand.cCheckDestWall",
            {"_CheckDest": {"float": 8.0}},
        )
        self.assertIsNone(self.truth(node))
        self.assertFalse(
            evaluate_expression(
                node["expression"],
                RuleRegistry.load(),
                {"enemy_command_work_valid": False},
            ).truth
        )

    def test_native_verifier_rejects_method_relocation_changed_bytes_and_fields(self):
        document = dict(
            evidence={
                "sample": [
                    dict(type="T", method="execute", address="0x100", end="0x103")
                ]
            },
            nativeProofs={
                "sample": [dict(address="0x100", end="0x103", bytes="b001c3")]
            },
            fieldChecks=[
                dict(type="T", field="Flag", fieldType="System.Boolean", offset="0x10")
            ],
        )

        class Metadata:
            address = "100"
            offset = "0x10"

            def get(self, name):
                return dict(methods={"execute": dict(function=self.address)})

            def fields(self, name):
                return {
                    "Flag": dict(type="System.Boolean", offset_from_base=self.offset)
                }

        class Binary:
            body = bytes.fromhex("b001c3")

            def read(self, address, length):
                return self.body

        metadata, binary = Metadata(), Binary()
        with patch(
            "sdk.enemy_logic_exporter.shared.logic.field_checks._recovered_document",
            return_value=document,
        ):
            verify_recovered_conditions(binary, metadata)
            metadata.address = "200"
            with self.assertRaisesRegex(ValueError, "方法身份"):
                verify_recovered_conditions(binary, metadata)
            metadata.address = "100"
            binary.body = bytes.fromhex("b000c3")
            with self.assertRaisesRegex(ValueError, "原生字节"):
                verify_recovered_conditions(binary, metadata)
            binary.body = bytes.fromhex("b001c3")
            metadata.offset = "0x11"
            with self.assertRaisesRegex(ValueError, "字段布局"):
                verify_recovered_conditions(binary, metadata)


if __name__ == "__main__":
    unittest.main()
