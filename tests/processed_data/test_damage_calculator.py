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

    def test_sharpness_skill_scope_follows_native_collision_flags(self) -> None:
        profiles = {p["id"]: p for p in self.catalog["hitProfiles"]}
        for action in self.catalog["actions"]:
            profile = profiles[action["profileId"]]
            expected = profile["scope"] in {f"Wp{i:02d}" for i in range(11)} and (
                not profile["ignoresSharpness"] or profile["forcesSharpnessAttackRate"])
            self.assertEqual("sharpness" in action["skillTags"], expected, action["id"])

    def test_runtime_weapon_states_keep_source_values_and_aliases(self) -> None:
        profiles = {p["id"]: p for p in self.catalog["hitProfiles"]}
        spirit = profiles["Wp03|Wp03/Collision/Collider/Wp03_Attack.rcol.38.json|7|4057751804|7"]
        self.assertEqual((spirit["sourceAttack"], spirit["renkiAttack"]), (14, 31))
        self.assertTrue(all(p.get("renkiAttack") is None for p in profiles.values() if p["scope"] != "Wp03"))
        arrows = [a for a in self.catalog["actions"] if a["profileId"] ==
                  "Wp11|Wp11/Collision/Shell/Wp11Shell_Gosha.rcol.38.json|4|3101219707|0"]
        self.assertGreater(len(arrows), 1)
        for arrow in arrows:
            self.assertEqual(arrow["bow"]["distanceRates"]["optimal"], 1.1)
            self.assertAlmostEqual(arrow["bow"]["coatingRates"]["close"], 1.4)
            self.assertAlmostEqual(arrow["bow"]["coatingRates"]["power"], 1.35)

    def test_insect_glaive_extract_table_is_scoped_and_validated(self) -> None:
        from src.processed_data.damage_calculator.weapon_states import validate_weapon_states
        profiles = self.catalog["hitProfiles"]
        for profile in profiles:
            if profile["scope"] == "Wp10":
                self.assertEqual(profile["insectglaive"]["extractRates"],
                                 {"none": 1, "redWhite": 1.1, "triple": 1.15})
            else:
                self.assertIsNone(profile["insectglaive"])
        profile = next(p for p in profiles if p["scope"] == "Wp10")
        with self.assertRaisesRegex(ValueError, "insect glaive"):
            validate_weapon_states({**profile, "scope": "Wp00"})
        with self.assertRaisesRegex(ValueError, "insect glaive"):
            validate_weapon_states({**profile, "insectglaive": {
                **profile["insectglaive"], "extractRates": {"none": 1, "redWhite": True, "triple": 1.15}}})

    def test_shared_melodies_preserve_official_names_and_source_rates(self) -> None:
        import copy
        from src.processed_data.damage_calculator.music import validate_music
        music = self.catalog["music"]
        self.assertEqual([entry["rate"] for entry in music["attack"]], [1.03, 1.05, 1.05, 1.1])
        self.assertEqual([entry["rate"] for entry in music["element"]], [1.08, 1.1])
        self.assertEqual(music["attack"][0]["name"], "攻击力提升【小】")
        self.assertEqual(music["element"][0]["name"], "属性攻击力提升")
        invalid = copy.deepcopy(music)
        invalid["element"][0]["rate"] = True
        with self.assertRaisesRegex(ValueError, "melody"):
            validate_music(invalid)

    def test_charge_blade_phials_keep_separate_shield_and_artillery_scope(self) -> None:
        from src.processed_data.damage_calculator.weapon_states import validate_weapon_states
        profiles = [p for p in self.catalog["hitProfiles"] if p.get("chargebladePhial")]
        self.assertEqual(len(profiles), 22)
        for profile in profiles:
            impact = profile["chargebladePhial"]["kind"] == "impact"
            self.assertEqual(profile["support"]["status"], "basic_hit")
            self.assertEqual(profile["physicalMeatMode"], "independent")
            self.assertEqual(profile["chargebladePhial"]["shieldMotionRate"], 1.2 if impact else 1)
            self.assertEqual(profile["chargebladePhial"]["shieldElementRate"], 1 if impact else 1.3)
            for action in (a for a in self.catalog["actions"] if a["profileId"] == profile["id"]):
                self.assertEqual("chargeblade_artillery" in action["skillTags"], impact)
            with self.assertRaisesRegex(ValueError, "charge blade phial"):
                validate_weapon_states({**profile, "canCritical": True})
            with self.assertRaisesRegex(ValueError, "charge blade phial"):
                validate_weapon_states({**profile, "scope": "Wp00"})

    def test_real_trace_runtime_overrides_are_not_claimed_as_basic_hits(self) -> None:
        profiles = {p["id"]: p for p in self.catalog["hitProfiles"]}
        # Manual capture 20260926_132827: laser 152, sword 374, pile 396.
        for identity in (
            "Ammo|WpGunCommon/Collision/Collider/WpGunShell_Laser.rcol.38.json|0|3751903411|0",
        ):
            self.assertEqual(profiles[identity]["support"]["status"], "unsupported")
            self.assertTrue(profiles[identity]["support"]["reasons"])
        # The verified ordinary axe hit remains available (capture hit 368).
        axe = profiles["Wp08|Wp08/Collision/Collider/Wp08_Attack.rcol.38.json|18|910774104|17"]
        self.assertEqual(axe["support"]["status"], "basic_hit")
        sword = profiles["Wp08|Wp08/Collision/Collider/Wp08_Attack.rcol.38.json|30|3204436267|20"]
        self.assertEqual(sword["support"]["status"], "basic_hit")
        self.assertEqual(sword["switchaxe"]["elementSeedRate"], 1.45)
        self.assertEqual(axe["switchaxe"]["powerAttackRate"], 1.17)
        self.assertTrue(all(p.get("switchaxe") is None for p in profiles.values() if "_Shell.rcol" in p["rcol"]))

    def test_gunlance_tables_preserve_native_levels_and_projectile_branches(self) -> None:
        from copy import deepcopy
        data = self.catalog["gunlance"]
        normal = data["shellTypes"]["normal"]
        self.assertEqual(data["levelIndexBase"], 0)
        self.assertEqual(normal["tables"]["_AttackInfoList"][2], {"Attack": 9, "FireAttack": 8})
        self.assertEqual(normal["tables"]["_RyuugekiAttackInfoList"][2], {"Attack": 47, "FireAttack": 26})
        self.assertEqual(normal["tables"]["_PileBlastAttackInfoList"][2], {"Attack": 28, "FireAttack": 23})
        self.assertEqual(normal["tables"]["_PileAttackList"][2], 7)
        self.assertEqual(normal["rates"]["_FullBurst_BF_AttackRate"], 1.25)
        self.assertEqual(data["rbfPileBlastRate"], 1.1)
        actions = [a for a in self.catalog["actions"] if a.get("gunlance")]
        self.assertTrue({"SHOT", "FULL_BURST", "PILE_CONST", "RBF_PILE_BLAST"}.issubset(
            {a["gunlance"]["type"] for a in actions}))
        profiles = {p["id"]: p for p in self.catalog["hitProfiles"]}
        self.assertTrue(all(profiles[a["profileId"]]["support"]["status"] == "basic_hit"
                            for a in actions if a["gunlance"]["type"] in {"SHOT", "FULL_BURST", "PILE_CONST", "RBF_PILE_BLAST"}))
        for bad in (float("nan"), -1, True):
            broken = deepcopy(self.catalog)
            broken["gunlance"]["shellTypes"]["normal"]["tables"]["_AttackInfoList"][2]["Attack"] = bad
            with self.assertRaisesRegex(ValueError, "gunlance"):
                validate_catalog(broken)

    def test_weapon_state_validation_rejects_wrong_scope_and_invalid_rates(self) -> None:
        from copy import deepcopy
        broken = deepcopy(self.catalog)
        profile = next(p for p in broken["hitProfiles"] if p.get("renkiAttack"))
        profile["scope"] = "Wp00"
        profile["longsword"] = None  # Isolate consumed-motion validation from the separate aura guard.
        with self.assertRaisesRegex(ValueError, "consumed spirit"):
            validate_catalog(broken)
        broken = deepcopy(self.catalog)
        action = next(a for a in broken["actions"] if a.get("bow"))
        action["bow"]["distanceRates"]["near"] = float("nan")
        with self.assertRaisesRegex(ValueError, "bow distanceRates"):
            validate_catalog(broken)

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
        self.assertEqual(self.catalog["schemaVersion"], 15)
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

    def test_mapping_names_match_database_and_unnamed_hits_keep_exact_identity(self) -> None:
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
            if action["kind"] == "Unmapped":
                self.assertTrue(action["name"].startswith("未命名命中 "))
                self.assertEqual(action["confidence"], "profile_only")
                self.assertFalse(action.get("bow"))
                continue
            names = mapping_names[action["mappingIdentity"]]
            self.assertTrue(any(action["name"] in {name, f"{name} Lv{action['ammoLevel']}"}
                                for name in names), action["name"])
        selectable = {action["profileId"] for action in actions}
        unnamed = {profile_id(record.key) for records in source.records.values() for record in records
                   if not any(binding.display_name(texts.get)
                              for binding in source.bindings.get(record.key, ()))}
        self.assertTrue(unnamed)
        player_unnamed = {identity for identity in unnamed if identity.startswith("Wp")}
        self.assertTrue(player_unnamed.issubset(selectable))
        fallback = [a for a in actions if a["kind"] == "Unmapped"]
        self.assertEqual(len(fallback), len({a["profileId"] for a in fallback}))
