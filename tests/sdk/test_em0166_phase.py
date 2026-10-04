import unittest
from sdk.enemy_logic_exporter.monster.em0166_00_0 import recover_phase_apply
from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry


class Em166PhaseTests(unittest.TestCase):
    def test_phase_check_reads_applied_phase_and_requires_valid_context(self):
        registry = RuleRegistry.load()
        bound = registry.bind(
            "app.btable.Em0166_00BTableCommand.cCheckBattlePhase",
            "app.btable.Em0166_00BTableCommand.cCheckBattlePhaseArg",
            {"_EditArg": "[1] PHASE_2"},
        )
        state = {"valid": True, "_CurrentPhase": 0, "_RequestPhase": 1}
        context = {
            "valid_command_work": True,
            "objects": {"app.cEm0166_00Extend": state},
        }
        self.assertIs(registry.evaluate(bound, context).truth, False)
        state["_CurrentPhase"] = 1
        self.assertIs(registry.evaluate(bound, context).truth, True)
        del state["valid"]
        self.assertIsNone(registry.evaluate(bound, context).truth)

    def test_other_monsters_cannot_use_this_recipe(self):
        self.assertEqual(
            recover_phase_apply(
                {"type": "app.btable.Em0164_50BTableCommand.cApplyRequestBattlePhase"},
                None,
                None,
            ),
            [],
        )

    def test_changed_command_bytes_require_fresh_review(self):
        with self.assertRaisesRegex(ValueError, "入口字节变化"):
            recover_phase_apply(
                {
                    "type": "app.btable.Em0166_00BTableCommand.cApplyRequestBattlePhase",
                    "nativeSha256": "0" * 64,
                },
                None,
                None,
            )

    def test_changed_tail_bytes_are_rejected_even_with_matching_entry(self):
        class Metadata:
            def get(self, name):
                return {
                    "methods": {"applyRequestBattlePhase1": {"function": "143ddeca0"}}
                }

        class PE:
            def end(self, address):
                return address + 16

            def read(self, address, size):
                return b"\x90" * size

        with self.assertRaisesRegex(ValueError, "共享尾部变化"):
            recover_phase_apply(
                {
                    "type": "app.btable.Em0166_00BTableCommand.cApplyRequestBattlePhase",
                    "nativeSha256": "0bb35418a44985bc4c64dfd6141e189d1285544bc3eee2ab2962f25ac2d91477",
                },
                Metadata(),
                PE(),
            )
