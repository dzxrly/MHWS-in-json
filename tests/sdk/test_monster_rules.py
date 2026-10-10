import unittest

from sdk.enemy_logic_exporter.shared.logic.monster_rules import rule_kinds
from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry


class MonsterRuleTests(unittest.TestCase):
    """Monster-specific kinds live in their monster modules, not in shared."""

    def setUp(self):
        self.registry = RuleRegistry.load()

    def evaluate(self, command, values, state):
        rule = self.registry.by_command[command]
        argument = {field: values[role] for role, field in rule["bindings"].items()}
        bound = self.registry.bind(command, rule["argumentType"], argument)
        binding = rule["contextBinding"]
        context = dict(
            valid_command_work=True,
            objects={binding["type"]: dict(valid=True, **state)},
        )
        return self.registry.evaluate(bound, context).truth

    def test_kinds_are_registered_by_their_monster_modules(self):
        owners = {
            kind: handler["compile"].__module__.rsplit(".", 1)[-1]
            for kind, handler in rule_kinds().items()
        }
        self.assertEqual(
            owners,
            dict(
                mushroom="em0021_00_0",
                catch_mushroom="em0021_00_0",
                fang_count="em0022_00_0",
                electric="em0046_00_0",
                phase_after_area_move="em0078_00_0",
                battle_phase="em0166_00_0",
            ),
        )

    def test_monster_kinds_evaluate_through_the_registry(self):
        command = "app.btable.Em0021_00BTableCommand.cCheckMushroomType"
        self.assertTrue(self.evaluate(command, dict(value=3), dict(_EatMushroomType=5)))
        self.assertFalse(
            self.evaluate(command, dict(value=0), dict(_EatMushroomType=5))
        )
        command = "app.btable.Em0022_00BTableCommand.cCheckBreakFangCount"
        self.assertTrue(
            self.evaluate(command, dict(compare=0, value=1), dict(_FangBreakCount=2))
        )
        command = "app.btable.Em0046_00BTableCommand.cCheckElectricLevel"
        self.assertTrue(self.evaluate(command, dict(value=2), dict(_ElectricLevel=3)))
        command = "app.btable.Em0078_00BTableCommand.cCheckPhase"
        final = dict(_Phase=2, _IsFinishAreaMove=False)
        self.assertTrue(self.evaluate(command, dict(value=1), final))
        self.assertFalse(self.evaluate(command, dict(value=2), final))
        self.assertTrue(
            self.evaluate(command, dict(value=2), dict(final, _IsFinishAreaMove=True))
        )
        # The generic equality kind stays in shared.
        command = "app.btable.Em0071_00BTableCommand.cCheckStateType"
        self.assertTrue(
            self.evaluate(command, dict(value=4), {"<State>k__BackingField": 4})
        )
