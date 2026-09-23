import unittest

from config import NATIVES_DIR
from src.processed_data.damage_calculator.exporter import build_catalog, validate_catalog
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource


class DamageCalculatorDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = build_catalog(
            NATIVES_DIR, SourceRepository(NATIVES_DIR), TextSource.from_natives(NATIVES_DIR)
        )

    def test_real_part_and_scar_references(self) -> None:
        monsters = {monster["id"]: monster for monster in self.catalog["monsters"]}
        head = next(part for part in monsters["EM0001_00_0"]["parts"] if part["type"] == "HEAD")
        self.assertEqual(head["variants"][0]["meat"]["slash"], 70)
        self.assertEqual(head["variants"][0]["meat"]["shot"], 65)
        self.assertEqual(head["variants"][0]["meat"]["ice"], 15)
        self.assertEqual(head["scars"][0]["meat"]["slash"], 80)
        self.assertEqual(head["scars"][0]["normalVital"], [220.0])
        self.assertNotEqual(head["id"], head["scars"][0]["id"])

    def test_missing_alternate_meat_is_explicit(self) -> None:
        monster = next(item for item in self.catalog["monsters"] if item["id"] == "EM5102_00_0")
        missing = [
            variant for part in monster["parts"] for variant in part["variants"]
            if variant["meat"] is None
        ]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["key"], "break")
        validate_catalog(self.catalog)

    def test_hit_profile_rates_keep_exact_request_set_identity(self) -> None:
        profiles = self.catalog["hitProfiles"]
        self.assertGreater(len(profiles), 1000)
        self.assertEqual(len({profile["id"] for profile in profiles}), len(profiles))
        self.assertTrue(any(profile["rates"]["PartsBreak"] == 0.9 for profile in profiles))
        self.assertTrue(any(profile["rates"]["PartsBreak"] == 1.5 for profile in profiles))

    def test_player_action_names_and_bonuses_keep_source_values(self) -> None:
        profile = next(row for row in self.catalog["hitProfiles"] if row["id"] == (
            "Wp00|Wp00/Collision/Collider/Wp00_Attack.rcol.38.json|0|2844005733|0"
        ))
        self.assertEqual(profile["sourceAttack"], 81)
        self.assertIn("直斩", profile["actionNames"])
        self.assertGreater(sum(bool(row["actionNames"]) for row in self.catalog["hitProfiles"]), 700)
        attack = next(row for row in self.catalog["skills"] if row["name"] == "攻击")
        self.assertEqual(attack["levels"][-1], {"level": 5, "percent": 104, "flat": 9})
        item = next(row for row in self.catalog["items"] if row["name"] == "力量护符")
        self.assertEqual(item["flat"], 6)
