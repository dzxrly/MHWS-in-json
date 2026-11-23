"""Real targets with distinct attack rolls, elemental routing and role overrides."""

import unittest

from config import NATIVES_DIR
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource
from src.site_data.missions import build_site_data


class MissionRateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = build_site_data(
            repository=SourceRepository(natives_dir=NATIVES_DIR),
            text_source=TextSource.from_natives(natives_dir=NATIVES_DIR),
        )
        cls.quests = {quest["id"]: quest for quest in data["quests"]}

    def test_low_rank_damage_and_hp_use_different_draws(self):
        target = self.quests["MISSION_101000"]["targets"][0]
        combat = target["combat"]
        self.assertEqual(
            first=[(item["grade"], item["probability"]) for item in combat["grades"]],
            second=[(-2, 10), (-1, 20), (0, 40), (1, 20), (2, 10)],
        )
        self.assertEqual(
            first=[item["hp"] for item in combat["parties"][0]["health"]],
            second=[3840, 3920, 4000, 4080, 4160],
        )
        self.assertEqual(
            first=[item["hp"] for item in combat["parties"][3]["health"]],
            second=[9216, 9409, 9600, 9792, 9984],
        )
        solo = combat["parties"][0]["states"]
        self.assertEqual(
            first=solo["normal"]["physical"],
            second=[0.776, 0.788, 0.8, 0.812, 0.824],
        )
        self.assertEqual(
            first=solo["tired"]["speed"],
            second=0.85,
        )

    def test_rey_dau_elemental_attack_and_multiplayer_parts(self):
        # Non-Hard King on 8 stars: its extra attack factor only affects physical.
        angry = self.quests["MISSION_600100"]["targets"][0]["combat"]["parties"][0][
            "states"
        ]["angry"]
        self.assertEqual(
            first=(angry["physical"], angry["element"]),
            second=([7.53825], [6.555]),
        )
        # Hard King on 10 stars: same factors on both channels.
        party = self.quests["MISSION_109005"]["targets"][0]["combat"]["parties"][3]
        angry = party["states"]["angry"]
        self.assertEqual(
            first=(angry["physical"], angry["element"], angry["speed"]),
            second=([10.0625], [10.0625], 1.2096),
        )
        self.assertEqual(
            first=party["parts"],
            second=33.6,
        )
        # The four-player multiplier applies before any HP rounding:
        # taking three times the displayed solo total would give 120726.
        nu_udra = self.quests["MISSION_109005"]["targets"][2]["combat"]["parties"]
        self.assertEqual(
            first=(nu_udra[0]["health"][0]["hp"], nu_udra[3]["health"][0]["hp"]),
            second=(40242, 120724),
        )

    def test_arch_tempered_arkveld_selects_action_and_replaces_angry_rate(self):
        target = self.quests["MISSION_650000"]["targets"][0]["combat"]
        ordinary = target["parties"][0]["states"]
        actions = {item["name"]: item for item in target["actions"]}
        self.assertEqual(first=ordinary["normal"]["speed"], second=1.08)
        self.assertEqual(first=ordinary["angry"]["speed"], second=1.134)
        self.assertEqual(first=actions["头部攻击"]["speed"]["normal"], second=1.161)
        cross = actions["双锁刃交叉攻击"]["speed"]
        self.assertEqual(first=cross["normal"], second=1.188)
        self.assertEqual(first=cross["angry"], second=1.38996)
        self.assertEqual(first=ordinary["normal"]["physical"][2], second=8.4)
        tempered = self.quests["MISSION_109011"]["targets"]
        other = next(item["combat"] for item in tempered if item["id"] == "EM0160_00_0")
        self.assertNotIn(
            member="头部攻击", container=[item["name"] for item in other["actions"]]
        )

    def test_frenzied_blangonga_uses_its_role_condition_parameters(self):
        state = self.quests["MISSION_010115"]["targets"][1]["combat"]["parties"][0][
            "states"
        ]
        self.assertEqual(
            first=(state["angry"]["speed"], state["tired"]["speed"]),
            second=(1.15, 1.0),
        )
        self.assertEqual(
            first=(state["angry"]["slash"], state["angry"]["shot"]),
            second=(1.1, 1.1),
        )

    def test_final_phase_motion_rate_depends_on_species_and_rank(self):
        zoh = self.quests["MISSION_650006"]["targets"][0]["combat"]
        self.assertEqual(first=zoh["phases"]["第四阶段战斗"], second=1.04)
        low_zoh = self.quests["MISSION_005390"]["targets"][0]["combat"]
        self.assertEqual(first=low_zoh["phases"], second={})
        gog = self.quests["MISSION_740025"]["targets"][0]["combat"]
        self.assertEqual(first=gog["phases"]["最终阶段战斗"], second=1.075)

    def test_rompopolo_shells_use_fixed_id_and_actual_emitter(self):
        shells = self.quests["MISSION_650001"]["targets"][0]["combat"]["shells"]
        self.assertEqual(
            first=[(s["id"], s["attack"]) for s in shells],
            second=[(0, 1.6), (1, 1.6), (2, 1.85), (40, 1.6), (41, 1.6), (44, 1.0)],
        )
        self.assertEqual(
            first=shells[0]["sources"],
            second=[{"name": "面前舌部喷气", "attack": 1.0}],
        )
        self.assertEqual(
            first=shells[1]["sources"],
            second=[{"name": "毒气漂移", "attack": 1.0}],
        )
        self.assertEqual(
            first=shells[-1]["name"],
            second="自动喷气预兆（活动）",
        )
        self.assertTrue(expr=shells[-1]["ignoreAction"])

    def test_species_damage_conditions_follow_layout_and_quest_rank(self):
        for quest, rate in (("MISSION_107002", 1.3), ("MISSION_630007", 1.65)):
            condition = self.quests[quest]["targets"][0]["combat"]["damageConditions"][
                0
            ]
            self.assertEqual(
                first=(condition["physical"], condition["element"]),
                second=(rate, rate),
            )
        for quest, rate in (("MISSION_005390", 1.35), ("MISSION_700025", 1.2)):
            condition = self.quests[quest]["targets"][0]["combat"][
                "incomingConditions"
            ][0]
            self.assertEqual(
                first=(condition["slash"], condition["shot"]),
                second=(rate, rate),
            )
