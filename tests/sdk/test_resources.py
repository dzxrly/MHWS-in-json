"""Keep resource identities distinct from the selected action-parameter type."""

import copy
import unittest
from unittest.mock import Mock

from sdk.enemy_logic_exporter.shared.resources.reader import (
    EMPTY_GUID,
    ActionBindingError,
    Resources,
)


def wrapped(name, body):
    return {name: body}


def reference(path):
    return wrapped("via.UserData", {"path": path})


class ResourceActionTests(unittest.TestCase):
    def setUp(self):
        self.guid = "11111111-1111-1111-1111-111111111111"
        self.variant = "22222222-2222-2222-2222-222222222222"
        self.info = {
            "_ActionGuid": self.guid,
            "_IsBaseAction": False,
            "_OverrideOwnerAction": False,
            "_OverrideSourceActionParamGuid": EMPTY_GUID,
        }
        self.parameter = {
            "_IsUseBranchedParam": True,
            "_ActionInfoList": [wrapped("ace.user_data.ActionParam.cInfo", self.info)],
            "_ActionClassList": [wrapped("app.TestAction.cRequested", {"value": 1})],
            "_BranchedParamsList": [
                wrapped(
                    "ace.user_data.ActionParam.cBranchedParams",
                    {
                        "_Params": [
                            wrapped(
                                "ace.user_data.ActionParam.cBranchedParam",
                                {
                                    "_Guid": self.variant,
                                    "_ActionClass": wrapped(
                                        "app.TestAction.cDifferent", {"value": 2}
                                    ),
                                },
                            )
                        ]
                    },
                )
            ],
        }
        self.data = {
            "id.user": {
                "_ActionIDArray": wrapped(
                    "ace.cInstanceGuidArray<ace.user_data.ActionID.cID>",
                    {
                        "_DataArray": [
                            wrapped(
                                "ace.user_data.ActionID.cID",
                                {
                                    "_Class": "cRequested",
                                    "_InstanceGuid": self.guid,
                                    "_BaseActionGuid": EMPTY_GUID,
                                },
                            )
                        ]
                    },
                )
            },
            "param.user": self.parameter,
            "bank.user": {
                "_CommandArgumentSettingList": [
                    wrapped(
                        "app.btable.AppBTableUtil.cSelectActionArgSetting",
                        {
                            "_AssetDataList": [
                                wrapped(
                                    "app.btable.AppBTableUtil.cSelectActionArgSetting.cAsset",
                                    {
                                        "_Asset": wrapped(
                                            "ace.cActionIDHolder",
                                            {"_ActionID": reference("id.user")},
                                        ),
                                        "_ParamAsset": reference("param.user"),
                                    },
                                )
                            ]
                        },
                    )
                ]
            },
        }
        self.resources = Resources.__new__(Resources)
        self.resources.resolve = lambda source: source
        self.resources.read = lambda source: self.data[source]
        self.table = {"_OrderBank": reference("bank.user")}

    def action(self, variant=EMPTY_GUID):
        return self.resources.action(
            self.table,
            {
                "_EditAssetIndex": wrapped("System.Int32", 0),
                "_EditActionGuid": wrapped("System.Guid", self.guid),
                "_EditBranchedParamGuid": wrapped("System.Guid", variant),
            },
        )

    def test_owned_branch_keeps_requested_action_and_distinct_parameter_class(self):
        action = self.action(self.variant)
        self.assertEqual(action["actionClass"], "cRequested")
        self.assertEqual(action["actionIdClass"], "cRequested")
        self.assertEqual(action["parameterClass"], "cDifferent")
        self.assertEqual(action["defaultParameterType"], "app.TestAction.cRequested")
        self.assertEqual(action["parameters"], {"value": 2})
        self.assertEqual(action["parameterSelection"], "branched")
        self.assertEqual(
            action["parameterClassRelation"], "distinct_branched_parameter_class"
        )
        self.assertFalse(action["parameterApplicationReviewed"])
        self.assertEqual(len(action["parameterBindingEvidence"]), 2)

    def test_default_parameter_remains_the_requested_class(self):
        action = self.action()
        self.assertEqual(action["parameterClass"], "cRequested")
        self.assertEqual(action["parameters"], {"value": 1})
        self.assertEqual(action["parameterSelection"], "default")
        self.assertEqual(action["parameterClassRelation"], "same_class")

    def test_disabled_branched_parameters_select_default(self):
        self.parameter["_IsUseBranchedParam"] = False
        action = self.action(self.variant)
        self.assertEqual(action["parameters"], {"value": 1})
        self.assertEqual(action["parameterVariantGuid"], self.variant)
        self.assertEqual(action["parameterSelection"], "default")

    def test_distinct_default_parameter_is_bound_without_replacing_action_class(self):
        self.parameter["_ActionClassList"][0] = wrapped(
            "app.TestAction.cOtherDefault", {"value": 3}
        )
        action = self.action()
        self.assertEqual(action["actionClass"], "cRequested")
        self.assertEqual(action["parameterClass"], "cOtherDefault")
        self.assertEqual(action["parameters"], {"value": 3})
        self.assertEqual(
            action["parameterClassRelation"], "distinct_default_parameter_class"
        )
        self.assertFalse(action["parameterApplicationReviewed"])
        self.assertEqual(len(action["parameterBindingEvidence"]), 1)

    def test_branch_of_another_action_does_not_bind_by_guid_elsewhere(self):
        own = self.parameter["_BranchedParamsList"][0]
        self.parameter["_BranchedParamsList"].append(copy.deepcopy(own))
        own["ace.user_data.ActionParam.cBranchedParams"]["_Params"] = []
        with self.assertRaisesRegex(ValueError, "不属于请求的动作"):
            self.action(self.variant)

    def test_duplicate_variant_guids_do_not_bind(self):
        values = self.parameter["_BranchedParamsList"][0][
            "ace.user_data.ActionParam.cBranchedParams"
        ]["_Params"]
        values.append(copy.deepcopy(values[0]))
        with self.assertRaisesRegex(ValueError, "不属于请求的动作"):
            self.action(self.variant)

    def test_missing_action_info_guid_stays_unbound(self):
        self.info["_ActionGuid"] = "33333333-3333-3333-3333-333333333333"
        with self.assertRaisesRegex(
            ActionBindingError, "无法通过动作 GUID 唯一绑定"
        ) as raised:
            self.action()
        error = raised.exception
        self.assertEqual(error.reason, "missing_action_parameter_guid")
        self.assertEqual(error.context["actionGuid"], self.guid)
        self.assertEqual(error.context["parameterAsset"], "param.user")
        self.assertEqual(error.context["actionIdRecord"]["_Class"], "cRequested")
        self.assertEqual(error.context["matchingParameterEntries"], 0)
        self.assertIn("_EditActionGuid", error.context["rawArgument"])

    def test_duplicate_action_info_is_a_hard_error_not_a_missing_binding(self):
        self.parameter["_ActionInfoList"].append(
            copy.deepcopy(self.parameter["_ActionInfoList"][0])
        )
        with self.assertRaises(ValueError) as raised:
            self.action()
        self.assertNotIsInstance(raised.exception, ActionBindingError)

    def test_requested_variant_requires_an_explicit_enable_flag(self):
        del self.parameter["_IsUseBranchedParam"]
        with self.assertRaisesRegex(ValueError, "变体启用状态"):
            self.action(self.variant)

    def test_declared_base_parameter_chain_selects_owner_variant(self):
        base = copy.deepcopy(self.parameter)
        self.data["base.user"] = base
        self.parameter["_BaseActionParam"] = reference("base.user")
        self.info["_IsBaseAction"] = True
        self.parameter["_BranchedParamsList"][0][
            "ace.user_data.ActionParam.cBranchedParams"
        ]["_Params"] = []
        action = self.action(self.variant)
        self.assertEqual(action["parameterAsset"], "base.user")
        self.assertEqual(
            action["parameterResolutionChain"], ["param.user", "base.user"]
        )
        self.assertEqual(action["parameters"], {"value": 2})


class LargeEnemyIdentityTests(unittest.TestCase):
    def identities(self, values):
        resources = Resources.__new__(Resources)
        resources.read = Mock(
            return_value={
                "_Values": [
                    wrapped("app.EnemyData.cValue", {"_enemyId": "EnemyId " + value})
                    for value in values
                ]
            }
        )
        return resources.large_enemy_ids()

    def test_base_below_1000_preserves_complete_variant_identity(self):
        self.assertEqual(
            self.identities(
                ["EM0002_00_0", "EM0150_00_0", "EM0150_50_0", "EM0999_01_2"]
            ),
            {"EM0002_00_0", "EM0150_00_0", "EM0150_50_0", "EM0999_01_2"},
        )

    def test_training_and_small_monsters_are_excluded(self):
        self.assertEqual(
            self.identities(
                ["EM0165_00_0", "EM1000_00_0", "EM1022_00_0", "EM0002_00_0"]
            ),
            {"EM0002_00_0"},
        )

    def test_duplicate_full_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "身份重复"):
            self.identities(["EM0150_50_0", "EM0150_50_0"])


if __name__ == "__main__":
    unittest.main()
