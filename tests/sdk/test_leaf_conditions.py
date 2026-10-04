import unittest
from sdk.enemy_logic_exporter.shared.leaf_conditions import recover_leaf


class Metadata:
    def fields(self, name):
        return {
            "app.cEm0166_00Extend": {
                "_CurrentPhase": {
                    "offset_from_base": "0x22c",
                    "type": "app.Em0166_00_Def.BATTLE_PHASE",
                }
            },
            "app.PhaseArg": {
                "_EditArg": {
                    "offset_from_base": "0x10",
                    "type": "ace.btable.cEditFieldEnum",
                }
            },
        }.get(name, {})


class LeafConditionTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(
            type="app.btable.Em0166_00BTableCommand.cCheckBattlePhase",
            method="onExecute1234575",
            address="0x143ba54d0",
            end="0x143ba5520",
            nativeSha256="a" * 64,
            parameters=[{"type": "ace.btable.cCommandWork"}, {"type": "app.PhaseArg"}],
        )
        self.code = """undefined4 test(void) {
        if (param_3 != 0 &&
          (puVar1 = *(undefined8 **)(*(longlong *)(*(longlong *)(param_3 + 0x28) + 0x78) + 0x10),puVar1 != 0) && *(longlong *)*puVar1 == _DAT_1547183a0) {
          return CONCAT31((int3)((uint)*(int *)((longlong)puVar1 + 0x22c) >> 8),
            *(int *)((longlong)puVar1 + 0x22c) == *(int *)(*(longlong *)(param_4 + 0x10) + 0x10));
        } return 0; }"""

    def test_phase_comparison_binds_actual_field_and_argument(self):
        rule = recover_leaf(self.row, self.code, Metadata())
        self.assertEqual(rule["contextField"], "_CurrentPhase")
        self.assertEqual(rule["argumentField"], "_EditArg")
        self.assertEqual(rule["operator"], "==")

    def test_helper_calls_prevent_leaf_recovery(self):
        self.assertIsNone(
            recover_leaf(
                self.row,
                self.code.replace("return 0;", "FUN_123456789(); return 0;"),
                Metadata(),
            )
        )

    def test_extra_data_condition_prevents_leaf_recovery(self):
        code = self.code.replace(
            "return CONCAT31",
            "if (*(int *)((longlong)puVar1 + 0x20) == 1) return 0; return CONCAT31",
        )
        self.assertIsNone(recover_leaf(self.row, code, Metadata()))

    def test_unmapped_offset_prevents_field_name_guess(self):
        self.assertIsNone(
            recover_leaf(self.row, self.code.replace("0x22c", "0x230"), Metadata())
        )

    def test_extend_holder_chain_is_required(self):
        self.assertIsNone(
            recover_leaf(self.row, self.code.replace("0x78", "0x80"), Metadata())
        )
