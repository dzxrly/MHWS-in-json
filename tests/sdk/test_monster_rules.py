import unittest

from sdk.enemy_logic_exporter.shared.logic.monster_rules import rule_kinds


class MonsterRuleTests(unittest.TestCase):
    """Monster-specific kinds live in their monster modules, not in shared."""


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
