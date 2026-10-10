"""Check the source-to-effect contract on real extracted game data."""

import unittest
from copy import deepcopy

from config import NATIVES_DIR
from src.processed_data.skill_effects.exporter import build_catalog, validate_catalog
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource


class SkillEffectExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = build_catalog(
            NATIVES_DIR, SourceRepository(NATIVES_DIR), TextSource.from_natives(NATIVES_DIR)
        )
        cls.skills = {skill["id"]: skill for skill in cls.catalog["skills"]}

    def test_bladescale_honing_exports_sharpness_floors(self) -> None:
        skill = self.skills["HunterSkill_217"]
        self.assertEqual(skill["name"], "刃鳞研装")
        self.assertEqual(skill["verification"], "verified")
        effects = skill["levels"][0]["effects"]
        self.assertEqual([(e["stage"], e["value"]) for e in effects],
                         [("sharpness.physical.min", 1.4), ("sharpness.element.min", 1.25)])
        self.assertTrue(all(e["requiresActionTag"] == "sharpness" and e["unit"] == "multiplier" for e in effects))

    def test_complete_identity_and_separate_effect_status(self) -> None:
        self.assertEqual(len(self.skills), 217)
        self.assertEqual(self.catalog["assumptions"]["criticalMode"], "selected_hit")
        self.assertEqual(self.catalog["rules"]["physicalCriticalBase"], 1.25)
        self.assertEqual(self.skills["HunterSkill_000"]["levels"][-1]["effects"][:2], [
            {"stage": "attack.stat.rate", "value": 1.04, "source": "SkillData._value[0]", "requiresCritical": False, "unit": "multiplier"},
            {"stage": "attack.stat.flat", "value": 9, "source": "SkillData._value[1]", "requiresCritical": False, "unit": "true_value"},
        ])
        self.assertEqual(self.skills["HunterSkill_204"]["verification"], "parameter_found")
        self.assertFalse(self.skills["HunterSkill_204"]["levels"][0]["effects"])

    def test_projectile_motion_skills_keep_native_type_scope_and_source(self) -> None:
        special = self.skills["HunterSkill_037"]["levels"][1]["effects"]
        self.assertEqual([e["value"] for e in special], [1.2, 1.2])
        self.assertTrue(all(e["stage"] == "attack.motion.rate" for e in special))
        gun, bow = special
        self.assertIn("GATLING", gun["shellTypes"])
        self.assertNotIn("NORMAL", gun["shellTypes"])
        self.assertIn("SPECIAL", bow["arrowTypes"])
        self.assertNotIn("NORMAL", bow["arrowTypes"])
        loading = self.skills["HunterSkill_218"]["levels"][0]["effects"]
        self.assertEqual([e["value"] for e in loading], [1.4, 1.25])
        self.assertTrue(loading[0]["requiresShell"])
        self.assertTrue(loading[1]["requiresArrow"])
        invalid = deepcopy(self.catalog)
        next(s for s in invalid["skills"] if s["id"] == "HunterSkill_218")["levels"][0]["effects"][1]["requiresArrow"] = False
        with self.assertRaisesRegex(ValueError, "requirement"):
            validate_catalog(invalid)

    def test_zero_slot_skills_read_weapon_and_element_parameters(self) -> None:
        critical = self.skills["HunterSkill_003"]["levels"][-1]
        self.assertEqual(critical["rawValues"], [0, 0, 0, 0])
        self.assertEqual([item["value"] for item in critical["effects"]], [1.15, 1.21])
        self.assertIn("greatsword", critical["effects"][1]["weapons"])
        burst = self.skills["HunterSkill_114"]["levels"][-1]
        self.assertEqual(burst["rawValues"], [0, 0, 0, 0])
        greatsword = [effect for effect in burst["effects"] if effect["weapons"] == ["greatsword"]]
        self.assertEqual([(effect["stage"], effect["value"]) for effect in greatsword], [
            ("attack.stat.flat", 18),
            ("element.stat.flat", 20),
        ])
        ballistic = self.skills["HunterSkill_019"]["levels"][-1]["effects"]
        self.assertEqual({effect["weapons"][0]: effect["value"] for effect in ballistic}, {
            "bow": 5, "heavybowgun": 5, "lightbowgun": 5,
        })
        validate_catalog(self.catalog)

    def test_first_shot_preserves_weapon_slots_and_explicit_projectile_condition(self) -> None:
        self.assertEqual(self.catalog["schemaVersion"], 7)
        skill = self.skills["HunterSkill_198"]
        self.assertEqual(skill["verification"], "verified")
        for level, attack in zip(skill["levels"], [5, 10, 15]):
            for weapon in ["lightbowgun", "heavybowgun"]:
                effects = [e for e in level["effects"] if e["weapons"] == [weapon]]
                self.assertEqual([(e["stage"], e["value"]) for e in effects],
                                 [("attack.hit.flat", attack), ("element.hit.rate", 1.1)])
                self.assertTrue(all(e["requiresFirstShot"] and e["requiresShell"] for e in effects))
        broken = deepcopy(self.catalog)
        effect = next(s for s in broken["skills"] if s["id"] == "HunterSkill_198")["levels"][0]["effects"][0]
        effect.pop("requiresShell")
        with self.assertRaisesRegex(ValueError, "requires a shell"):
            validate_catalog(broken)

    def test_reject_invalid_effect_scope_and_missing_source_hash(self) -> None:
        catalog = deepcopy(self.catalog)
        skill = next(item for item in catalog["skills"] if item["id"] == "HunterSkill_114")
        skill["levels"][0]["effects"][0]["state"] = "unknown"
        with self.assertRaisesRegex(ValueError, "Unknown effect state"):
            validate_catalog(catalog)
        catalog = deepcopy(self.catalog)
        catalog["sourceHashes"].pop(next(iter(catalog["sourceHashes"])))
        with self.assertRaisesRegex(ValueError, "source hashes"):
            validate_catalog(catalog)

    def test_projectile_skills_and_group_unlocked_name(self) -> None:
        for skill_id, shell in [("HunterSkill_038", "NORMAL"), ("HunterSkill_039", "PENETRATE"), ("HunterSkill_040", "SHOT_GUN")]:
            effects = self.skills[skill_id]["levels"][0]["effects"]
            self.assertEqual(effects[0]["shellTypes"], [shell])
            self.assertEqual(effects[0]["value"], 1.05)
            self.assertEqual(effects[1]["weapons"], ["bow"])
            self.assertTrue(effects[1]["arrowTypes"])
        guts = self.skills["HunterSkill_205"]
        self.assertEqual(guts["name"], "毅力【果断】")
        self.assertEqual(guts["groupName"], "霸主之魂")
        self.assertEqual(guts["levels"][0]["openSkills"], ["HunterSkill_206"])
        self.assertEqual(guts["levels"][0]["effects"][0]["value"], 1.05)

    def test_coalescence_uses_weapon_specific_element_slots(self) -> None:
        effects = self.skills["HunterSkill_113"]["levels"][-1]["effects"]
        expected = {"greatsword": 1.3, "heavybowgun": 1.3, "lightbowgun": 1.3,
                    "bow": 1.15, "swordshield": 1.15, "dualblades": 1.15,
                    "longsword": 1.15, "lance": 1.15, "insectglaive": 1.15}
        for weapon, value in expected.items():
            matches = [effect for effect in effects if weapon in effect["weapons"]]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["value"], value)


if __name__ == "__main__":
    unittest.main()
