import unittest
from sdk.enemy_logic_exporter.shared.logic.commands import recover_writes
from sdk.enemy_logic_exporter.shared.logic.commands import annotate_effects


class Metadata:
    def fields(self, name):
        return {
            "app.cEm0166_00Extend": {
                "_CurrentPhase": {"offset_from_base": "0x22c", "type": "Phase"},
                "_RequestPhase": {"offset_from_base": "0x254", "type": "Phase"},
            }
        }.get(name, {})


class CommandEffectTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(
            type="app.btable.Em0166_00BTableCommand.cApplyRequestBattlePhase",
            method="onExecute1",
            address="0x1000",
            end="0x1100",
            nativeSha256="a" * 64,
        )
        self.code = "puVar2 = *(undefined8 **)(*(longlong *)(*(longlong *)(param_3 + 0x28) + 0x78) + 0x10); *(undefined4 *)((longlong)puVar2 + 0x22c) = *(undefined4 *)((longlong)puVar2 + 0x254); FUN_123456789();"

    def test_copy_is_partial_effect_and_retains_other_calls(self):
        effects = recover_writes(self.row, self.code, Metadata())
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0]["destination"]["field"], "_CurrentPhase")
        self.assertEqual(effects[0]["value"]["field"], "_RequestPhase")
        annotation = dict(
            kind="command", commandType=self.row["type"], summary="原生命令"
        )
        annotate_effects(
            annotation,
            {"commands": {self.row["type"]: [dict(recoveredWrites=effects)]}},
        )
        self.assertFalse(annotation["commandEffectsComplete"])
        self.assertIn("其他条件和副作用", annotation["summary"])

    def test_wrong_object_and_unknown_offset_are_rejected(self):
        self.assertEqual(
            recover_writes(
                self.row,
                self.code.replace("puVar2 + 0x22c", "puVar3 + 0x22c"),
                Metadata(),
            ),
            [],
        )
        self.assertEqual(
            recover_writes(self.row, self.code.replace("0x22c", "0x228"), Metadata()),
            [],
        )

    def test_resource_value_requires_matching_argument_type(self):
        effect = dict(
            destination={"field": "Phase"},
            value=dict(
                kind="resource_argument_field", argumentType="Arg", field="_EditArg"
            ),
        )
        annotation = dict(
            kind="command",
            commandType="Command",
            argumentType="Wrong",
            argument={"_EditArg": 3},
            summary="命令",
        )
        annotate_effects(
            annotation, {"commands": {"Command": [dict(recoveredWrites=[effect])]}}
        )
        self.assertEqual(annotation["partialImplementationEffects"], [])

    def test_second_update_does_not_duplicate_summary(self):
        effects = recover_writes(self.row, self.code, Metadata())
        catalog = {"commands": {self.row["type"]: [dict(recoveredWrites=effects)]}}
        annotation = dict(kind="command", commandType=self.row["type"], summary="命令")
        annotate_effects(annotation, catalog)
        summary = annotation["summary"]
        annotate_effects(annotation, catalog)
        self.assertEqual(annotation["summary"], summary)
