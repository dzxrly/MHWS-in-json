"""Skill modules (sdk/skill_effect_exporter/skills) and the link JSON they annotate."""

import json
import unittest

from sdk.skill_effect_exporter.config import DEFAULT_OUTPUT
from sdk.skill_effect_exporter.skills import annotations, get_skill, skill_ids


class SkillModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = json.loads(
            (DEFAULT_OUTPUT / "index.json").read_text(encoding="utf-8")
        )

    def test_every_module_names_its_own_skill(self):
        for skill_id in skill_ids():
            self.assertEqual(get_skill(skill_id).SKILL_ID, skill_id)

    def test_committed_links_carry_the_modules(self):
        # The link JSON holds what the modules say; after editing a module,
        # run "python -m sdk.skill_effect_exporter annotate".
        catalog = [s for s, v in self.index["skills"].items() if v["inSkillCommonData"]]
        meanings, notes, missing, extra = annotations(catalog, self.index["skills"])
        self.assertEqual((missing, extra), ([], []))
        self.assertEqual(self.index["meanings"], meanings)
        self.assertEqual(self.index["notes"]["skills"], notes)


if __name__ == "__main__":
    unittest.main()
