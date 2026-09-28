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

    def test_hien_requires_the_collision_aerial_flag(self) -> None:
        effects = self.skills["HunterSkill_055"]["levels"][0]["effects"]
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0]["requiresActionTag"], "hien")
        self.assertEqual(effects[0]["value"], 1.1)

    def test_burst_reinforcement_is_a_separate_stat_addition(self) -> None:
        skill = self.skills["HunterSkill_186"]
        self.assertEqual(skill["verification"], "verified")
        self.assertEqual([(level["level"], level["effects"][0]["value"])
                          for level in skill["levels"]], [(2, 8), (4, 18)])
        for level in skill["levels"]:
            self.assertEqual(len(level["effects"]), 1)
            self.assertEqual(level["effects"][0]["stage"], "attack.stat.flat")
            self.assertIn("HunterSkill_160", level["effects"][0]["source"])

    def test_force_shot_uses_attack_slot_and_keeps_bow_arrow_scope(self) -> None:
        for level, addition in zip(self.skills["HunterSkill_197"]["levels"], [3, 6, 10]):
            effects = level["effects"]
            self.assertEqual([e["value"] for e in effects], [addition, 1.05, addition, 1.05])
            self.assertTrue(all(e["requiresShell"] for e in effects[:2]))
            self.assertTrue(all({"NORMAL", "GOSHA", "GOSHA_RAPID"}.issubset(e["arrowTypes"]) for e in effects[2:]))

    def test_charge_master_uses_bow_slot_and_excludes_inherited_false_handlers(self) -> None:
        for level in self.skills["HunterSkill_048"]["levels"]:
            effects = level["effects"]
            bow = next(effect for effect in effects if effect["weapons"] == ["bow"])
            melee = next(effect for effect in effects if "greatsword" in effect["weapons"])
            self.assertEqual(bow["value"], level["rawValues"][1] / 100)
            self.assertEqual(melee["value"], level["rawValues"][0] / 100)
            supported = {weapon for effect in effects for weapon in effect["weapons"]}
            self.assertTrue(supported.isdisjoint({"dualblades", "huntinghorn", "heavybowgun", "lightbowgun"}))

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

    def test_black_eclipse_overcome_does_not_invent_element_or_first_tier_attack(self) -> None:
        skill = self.skills["HunterSkill_183"]
        self.assertEqual(skill["verification"], "verified")
        self.assertEqual(skill["name"], "黑蚀一体")
        self.assertEqual(skill["groupName"], "黑蚀龙之力")
        self.assertEqual([(row["level"], row["name"]) for row in skill["levels"]],
                         [(2, "黑蚀一体Ⅰ"), (4, "黑蚀一体Ⅱ")])
        for level, expected in zip(skill["levels"], [0, 15]):
            self.assertEqual(level["openSkills"], ["HunterSkill_196"])
            self.assertEqual([(effect["stage"], effect["value"]) for effect in level["effects"]],
                             [("attack.stat.flat", expected)])

    def test_challenger_attribute_reads_unlocked_numeric_slots(self) -> None:
        skill = self.skills["HunterSkill_239"]
        self.assertEqual(skill["name"], "宣战呼应")
        self.assertEqual(skill["groupName"], "巨戟龙的默示录")
        self.assertEqual(skill["verification"], "verified")
        self.assertNotIn("candidateSources", skill)
        for level, rate, flat in zip(skill["levels"], [1.2, 1.3], [2, 4]):
            self.assertEqual(level["openSkills"], ["HunterSkill_242"])
            self.assertEqual([(effect["stage"], effect["value"]) for effect in level["effects"]],
                             [("element.stat.rate", rate), ("element.stat.flat", flat)])

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
