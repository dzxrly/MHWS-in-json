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
