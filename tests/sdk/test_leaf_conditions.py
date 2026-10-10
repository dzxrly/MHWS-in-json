import unittest
from sdk.enemy_logic_exporter.shared.logic.commands import recover_leaf
from sdk.enemy_logic_exporter.shared.logic.formula import Unsupported, evaluate

class Metadata:
    def fields(self, name):
        return {
            "app.cEm0166_00Extend": {
                "_CurrentPhase": {
                    "offset_from_base": "0x22c",
                    "type": "app.Em0166_00_Def.BATTLE_PHASE",
                }
            },
            "app.cEm0159_00Extend": {
                "_IsBlazingMode": {
                    "offset_from_base": "0xba",
                    "type": "System.Boolean",
                },
                "_Stage": {"offset_from_base": "0x10c", "type": "System.Int32"},
            },
            "app.cEm0160_00Extend": {
                "_AbsorbCocoonState": {
                    "offset_from_base": "0xa8",
                    "type": "System.Int32",
                }
            },
            "app.cEnemyExtendBase": {
                "_UniqueStateFixedID": {"offset_from_base": "0x28", "type": "Continue"}
            },
            "Continue": {"_Value": {"offset_from_base": "0x10", "type": "Changed"}},
            "Changed": {"_Value": {"offset_from_base": "0x18", "type": "Nullable"}},
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


class LeafVariantTests(unittest.TestCase):
    holder = "puVar1 = *(undefined8 **)(*(longlong *)(param_3[5] + 0x78) + 0x10); "

    def row(self, owner, name):
        return dict(
            type=f"app.btable.{owner}BTableCommand.{name}",
            method="onExecute1",
            address="0x140000000",
            end="0x140000010",
            nativeSha256="a" * 64,
            parameters=[{"type": "ace.btable.cCommandWork"}],
        )

    def test_type_checked_alias_and_integer_constant(self):
        code = (
            "undefined8 f(void) { if (param_3 != 0) { "
            + self.holder
            + "puVar2 = (undefined8 *)0x0; if (*(longlong *)*puVar1 == _DAT_154718298) "
            "{ puVar2 = puVar1; } return CONCAT71((int7)((ulonglong)puVar1 >> 8),"
            "*(char *)((longlong)puVar2 + 0xba) != '\\0'); } return 0; }"
        )
        rule = recover_leaf(
            self.row("Em0159_00", "cCheckBlazingMode"), code, Metadata()
        )
        self.assertEqual(
            (rule["contextField"], rule["operator"]), ("_IsBlazingMode", "!=")
        )
        code = code.replace(
            "*(char *)((longlong)puVar2 + 0xba) != '\\0'",
            "*(int *)((longlong)puVar2 + 0x10c) < 2",
        )
        rule = recover_leaf(self.row("Em0159_00", "cCheckStage"), code, Metadata())
        self.assertEqual(
            (rule["contextField"], rule["operator"], rule["constant"]),
            ("_Stage", "<", 2),
        )
        # The alias must come from the holder's own type check.
        other = code.replace("puVar2 = puVar1;", "puVar2 = puVar3;")
        self.assertIsNone(
            recover_leaf(self.row("Em0159_00", "cCheckStage"), other, Metadata())
        )

    def test_class_check_and_direct_boolean_return(self):
        code = (
            "bool f(void) { if (param_3 != 0 && ("
            + self.holder.strip()[:-1]
            + ", puVar1 != 0) && (cVar2 = func_0x00014b0212b0(*(undefined8 *)*puVar1,"
            "_DAT_1547182b0), cVar2 != '\\0')) { return *(int *)(puVar1 + 0x15) != 0; } return false; }"
        )
        rule = recover_leaf(
            self.row("Em0160_00", "cCheckAbsorbedCocoon"), code, Metadata()
        )
        self.assertEqual(
            (rule["contextField"], rule["operator"], rule["constant"]),
            ("_AbsorbCocoonState", "!=", 0),
        )
        unchecked = code.replace("func_0x00014b0212b0", "FUN_1234")
        self.assertIsNone(
            recover_leaf(
                self.row("Em0160_00", "cCheckAbsorbedCocoon"), unchecked, Metadata()
            )
        )

    def test_unique_state_requires_has_value_and_fixed_value(self):
        code = (
            "undefined8 f(void) { if (param_3 != 0) { "
            + self.holder
            + "uVar1 = *(undefined8 *)(*(longlong *)(puVar1[5] + 0x10) + 0x18); "
            "return CONCAT71((uint7)((ulonglong)uVar1 >> 0x28),"
            "(int)((ulonglong)uVar1 >> 0x20) == -0x71caef00 && (char)uVar1 != '\\0'); } return 0; }"
        )
        rule = recover_leaf(
            self.row("Em0070_00", "cCheckStateDoubleFloor"), code, Metadata()
        )
        self.assertEqual(
            (rule["kind"], rule["constant"]), ("unique_state", -0x71CAEF00)
        )
        no_flag = code.replace(" && (char)uVar1 != '\\0'", "")
        self.assertIsNone(
            recover_leaf(
                self.row("Em0070_00", "cCheckStateDoubleFloor"), no_flag, Metadata()
            )
        )


class ContextFieldTests(unittest.TestCase):
    """Common commands that compare one cEnemyContext module field."""

    class Metadata:
        def fields(self, name):
            return {
                "app.cEnemyContext": {
                    "Lead": {"offset_from_base": "0x190", "type": "Lead"}
                },
                "Lead": {"Chase": {"offset_from_base": "0x18", "type": "Chase"}},
                "Chase": {
                    "_CurrentPhase": {"offset_from_base": "0x54", "type": "PHASE"}
                },
                "PhaseArg": {"_EditType": {"offset_from_base": "0x10", "type": "Enum"}},
            }.get(name, {})

    row = dict(
        type="app.btable.EmCommonCommand.cCheckLeadChasePhase",
        method="onExecute1",
        address="0x140000000",
        end="0x140000010",
        nativeSha256="a" * 64,
        parameters=[{"type": "ace.btable.cCommandWork"}, {"type": "PhaseArg"}],
    )
    # Ghidra line breaks are kept to check the whitespace normalization.
    code = """undefined4 f(void) {
  if ((param_3 != (undefined8 *)0x0) && (*(longlong *)*param_3 == _DAT_15471e840)) {
    iVar1 = *(int *)(*(longlong *)
                      (*(longlong *)(*(longlong *)(*(longlong *)(param_3[5] + 0x68) + 0x40) + 400) +
                      0x18) + 0x54);
    return CONCAT31((int3)((uint)iVar1 >> 8),iVar1 == *(int *)(*(longlong *)(param_4 + 0x10) + 0x10)
                   );
  }
  return 0; }"""

    def test_field_path_and_argument_are_resolved(self):
        from sdk.enemy_logic_exporter.shared.logic.commands import recover_context_leaf

        rule = recover_context_leaf(self.row, self.code, self.Metadata())
        self.assertEqual(rule["contextField"], "Lead.Chase._CurrentPhase")
        self.assertEqual((rule["operator"], rule["argumentField"]), ("==", "_EditType"))

    def test_unresolved_offsets_or_helper_calls_are_rejected(self):
        from sdk.enemy_logic_exporter.shared.logic.commands import recover_context_leaf

        self.assertIsNone(
            recover_context_leaf(
                self.row, self.code.replace("0x54", "0x58"), self.Metadata()
            )
        )
        self.assertIsNone(
            recover_context_leaf(
                self.row,
                self.code.replace("return 0;", "FUN_1234(); return 0;"),
                self.Metadata(),
            )
        )

    def test_extra_branch_conditions_are_not_dropped(self):
        from sdk.enemy_logic_exporter.shared.logic.commands import recover_context_leaf

        extra = self.code.replace(
            "== _DAT_15471e840))",
            "== _DAT_15471e840) && (*(int *)(*(longlong *)(param_4 + 0x18) + 0x10) == 2))",
        )
        self.assertIsNone(recover_context_leaf(self.row, extra, self.Metadata()))


class FieldFormulaTests(unittest.TestCase):
    HEAD = "undefined8 f(undefined8 param_1,undefined8 param_2,undefined8 *param_3)\n"

    def formula(self, body):
        return evaluate(self.HEAD + body)[0]

    def test_assignment_in_skipped_operand_does_not_leak(self):
        # x is reassigned only when a fails; b must read the new x then.
        result = self.formula(
            "{ longlong x; x = param_3[5];"
            " if ((*(int *)(x + 4) == 1) || (x = *(longlong *)(x + 8), *(char *)(x + 2) != '\0'))"
            " { return 1; } return 0; }"
        )
        a = (
            "cmp",
            "==",
            ("load", 4, ("load", 8, ("param", "param_3"), 40), 4),
            ("const", 1),
        )
        b = (
            "cmp",
            "!=",
            ("load", 1, ("load", 8, ("load", 8, ("param", "param_3"), 40), 8), 2),
            ("const", 0),
        )
        self.assertEqual(result, ("or", (a, b)))

    def test_trap_paths_are_false_and_calls_are_rejected(self):
        result = self.formula(
            "{ code *pcVar1; undefined8 uVar2;"
            " if (*(char *)(param_3[5] + 3) == '\0') { FUN_1(param_1,0x46,0);"
            " pcVar1 = (code *)swi(3); uVar2 = (*pcVar1)(); return uVar2; }"
            " return 1; }"
        )
        self.assertEqual(result[0], "cmp")
        self.assertEqual(result[1], "!=")
        with self.assertRaises(Unsupported):
            self.formula("{ char c; c = FUN_2(param_1); return c != '\0'; }")
