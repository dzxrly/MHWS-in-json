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

    def test_player_action_names_and_items_keep_source_values(self) -> None:
        self.assertEqual(self.catalog["schemaVersion"], 10)
        profile = next(row for row in self.catalog["hitProfiles"] if row["id"] == (
            "Wp00|Wp00/Collision/Collider/Wp00_Attack.rcol.38.json|0|2844005733|0"
        ))
        self.assertEqual(profile["sourceAttack"], 81)
        self.assertTrue(profile["usesAttackPower"])
        self.assertTrue(profile["usesElementPower"])
        self.assertFalse(profile["ignoresSharpness"])
        self.assertFalse(profile["forcesSharpnessAttackRate"])
        self.assertIn("直斩", profile["actionNames"])
        self.assertGreater(sum(bool(row["actionNames"]) for row in self.catalog["hitProfiles"]), 700)
        self.assertTrue(any(row["elementRate"] == 0.3 for row in self.catalog["hitProfiles"] if row["actionNames"]))
        self.assertNotIn("skills", self.catalog)
        item = next(row for row in self.catalog["items"] if row["name"] == "力量护符")
        self.assertEqual(item["flat"], 6)

    def test_native_attack_limits_are_required_and_finite(self) -> None:
        self.assertEqual(self.catalog["rules"]["attackRateLimit"], 4)
        self.assertEqual(self.catalog["rules"]["attackAddLimit"], 400)
        for value in (None, 0, -1, True, float("nan"), float("inf")):
            broken = {**self.catalog, "rules": {**self.catalog["rules"], "attackAddLimit": value}}
            with self.assertRaisesRegex(ValueError, "attackAddLimit"):
                validate_catalog(broken)

    def test_elemental_ammo_physical_curve_preserves_native_knots(self) -> None:
        action = next(item for item in self.catalog["actions"] if item["name"] == "电击弹")
        profile = next(item for item in self.catalog["hitProfiles"] if item["id"] == action["profileId"])
        points = profile["multiHit"]["physicalCurvePoints"]
        self.assertEqual([point["count"] for point in points], [0, 1, 3, 4, 30])
        for point, rate in zip(points, [1, 1, 0.8, 0.5, 0.5]):
            self.assertAlmostEqual(point["rate"], rate)
        self.assertFalse(profile["multiHit"]["statusCurve"])

    def test_normal_ammo_shared_levels_and_pierce_curve(self) -> None:
        normal = next(a for a in self.catalog["actions"] if a["shell"] and a["shell"]["type"] == "NORMAL")
        self.assertEqual(normal["name"], "通常弹")
        self.assertEqual(normal["ammoLevels"], [1, 2, 3])
        pierce = next(a for a in self.catalog["actions"] if a["shell"] and a["shell"]["type"] == "PENETRATE")
        profile = next(p for p in self.catalog["hitProfiles"] if p["id"] == pierce["profileId"])
        points = profile["multiHit"]["physicalCurvePoints"]
        self.assertEqual([p["count"] for p in points], [0, 1, 2, 3, 4, 30])
        for point, expected in zip(points, [1, 1, .9, .8, .7, .7]):
            self.assertAlmostEqual(point["rate"], expected)

    def test_sharpness_rates_and_action_flags(self) -> None:
        colors = self.catalog["sharpness"]
        self.assertEqual([row["name"] for row in colors], [
            "红斩", "橙斩", "黄斩", "绿斩", "蓝斩", "白斩", "紫斩",
        ])
        self.assertEqual((colors[0]["physical"], colors[0]["element"]), (0.5, 0.25))
        self.assertEqual((colors[-1]["physical"], colors[-1]["element"]), (1.39, 1.25))
        flags = {(row["ignoresSharpness"], row["forcesSharpnessAttackRate"])
                 for row in self.catalog["hitProfiles"]}
        self.assertIn((True, True), flags)
        self.assertIn((True, False), flags)

    def test_ammunition_resources_and_shared_source_contract(self) -> None:
        from src.processed_data.skill_effects.exporter import build_catalog as build_skills
        from src.processed_data.skill_effects.specs import WEAPONS
        profiles = {row["id"]: row for row in self.catalog["hitProfiles"]}
        actions = self.catalog["actions"]
        fire = [row for row in actions if row["name"] == "火炎弹"]
        self.assertTrue(fire)
        for action in fire:
            hit = profiles[action["profileId"]]
            self.assertEqual(hit["elementSource"], "attack_scaled")
            self.assertEqual((hit["sourceAttack"], hit["sourceElement"]), (8, 20))
            self.assertEqual(hit["elementType"], "fire")
            self.assertFalse(hit["usesElementPower"])
            self.assertEqual(set(action["weapons"]), {"heavybowgun", "lightbowgun"})
            self.assertEqual(action["shell"]["parameters"]["_Attr_Rate_Light"], 0.7)
        for weapon in WEAPONS:
            self.assertTrue(any(weapon in row["weapons"] for row in actions), weapon)
        self.assertTrue(any(row["sourceFixed"] > 0 for row in profiles.values()))
        skills = build_skills(NATIVES_DIR, SourceRepository(NATIVES_DIR), TextSource.from_natives(NATIVES_DIR))
        self.assertEqual(skills["sourceContract"], self.catalog["sourceContract"])

    def test_rejects_corrupt_contract_and_dangling_action(self) -> None:
        from copy import deepcopy
        catalog = deepcopy(self.catalog)
        catalog["sourceContract"]["id"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            validate_catalog(catalog)
        catalog = deepcopy(self.catalog)
        catalog["actions"][0]["profileId"] = "missing"
        with self.assertRaisesRegex(ValueError, "action reference"):
            validate_catalog(catalog)

    def test_multihit_curve_reference_is_preserved(self) -> None:
        fire = next(row for row in self.catalog["actions"] if row["name"] == "火炎弹")
        profile = next(row for row in self.catalog["hitProfiles"] if row["id"] == fire["profileId"])
        self.assertIn("WpGunElement_MultiHitCurve", profile["multiHit"]["physicalCurve"])

    def test_shared_spread_levels_and_arrow_scope_are_exported(self) -> None:
        spread = next(row for row in self.catalog["actions"] if row["shell"] and row["shell"]["type"] == "SHOT_GUN")
        self.assertEqual(spread["ammoLevels"], [1, 2, 3])
        self.assertEqual(spread["shell"]["parameters"]["_Lv3_AttackRate"], 1.4)
        arrows = [row for row in self.catalog["actions"] if row["arrowType"]]
        self.assertTrue(arrows)
        self.assertTrue(all(row["weapons"] == ["bow"] for row in arrows))

    def test_element_ammo_keeps_both_levels_and_native_rates(self) -> None:
        elements = [row for row in self.catalog["actions"] if row["shell"] and row["shell"]["type"] == "ELEMENT"]
        self.assertTrue(elements)
        for action in elements:
            self.assertEqual(action["ammoLevels"], [1, 2])
            self.assertEqual(action["shell"]["parameters"]["_Lv2_AttackRate"], 1.25)
            self.assertEqual(action["shell"]["parameters"]["_Lv2_SpecialRate"], 1.25)

    def test_mapping_names_match_database_and_unnamed_hits_are_not_selectable(self) -> None:
        from config import ACTION_MAP_PATH, ZH_HANS_LANGUAGE_ID
        from src.database.action_values.build import build_action_value_workbook, load_action_value_catalog
        from src.processed_data.damage_calculator.actions import profile_id
        source = load_action_value_catalog(NATIVES_DIR, ACTION_MAP_PATH)
        texts = TextSource.from_natives(NATIVES_DIR).build(ZH_HANS_LANGUAGE_ID)
        workbook = build_action_value_workbook(source, texts.get)
        mapping_names = {}
        for rows in workbook.sheets.values():
            for row in rows:
                if row["MappingName"]:
                    mapping_names.setdefault(row["MappingIdentity"], set()).add(row["MappingName"])
        actions = self.catalog["actions"]
        internal = [action for action in actions if action["name"] == "cSlash3"]
        self.assertTrue(internal)
        for action in actions:
            self.assertNotEqual(action["kind"], "Unmapped")
            names = mapping_names[action["mappingIdentity"]]
            self.assertTrue(any(action["name"] in {name, f"{name} Lv{action['ammoLevel']}"}
                                for name in names), action["name"])
        selectable = {action["profileId"] for action in actions}
        unnamed = {profile_id(record.key) for records in source.records.values() for record in records
                   if not any(binding.display_name(texts.get)
                              for binding in source.bindings.get(record.key, ()))}
        self.assertTrue(unnamed)
        self.assertTrue(selectable.isdisjoint(unnamed))
