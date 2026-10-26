"""SkillDetails.xlsx joins the committed skill link JSON with the exports."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from config import NATIVES_DIR
from src.processed_data.skill_details.exporter import (
    LINKS_DIR,
    build_sheets,
    cartesian_blocks,
    effect_links,
    load_links,
    own_values,
    value_situations,
)
from src.processed_data.skill_details.labels import effect_name
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource


class SkillDetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.links = load_links()
        cls.sheets = build_sheets(
            SourceRepository(NATIVES_DIR),
            TextSource.from_natives(NATIVES_DIR),
            cls.links,
        )

    def value(self, skill, effect, level, applies="", situation=""):
        rows = [
            r
            for r in self.sheets["技能效果"]
            if r["技能ID"] == skill
            and r["效果"] == effect
            and r["技能等级"] == f"Lv.{level}"
            and r["适用"] == applies
            and r["条件"].startswith(situation)
        ]
        self.assertEqual(len(rows), 1, (skill, effect, level, applies, rows))
        return rows[0]["数值"]

    def test_attack_values_follow_skill_data_slots(self):
        # Checked against sdk config.GAME_VERSION: getSkillAttackRate = value[0] * 0.01, getSkillAttackAdd = value[1].
        self.assertEqual(self.value("HunterSkill_000", "攻击力倍率", 4), 1.02)
        self.assertEqual(
            [self.value("HunterSkill_000", "基础攻击力加算", lv) for lv in range(1, 6)],
            [3, 5, 7, 8, 9],
        )
        row = next(
            r for r in self.sheets["技能效果"] if r["技能ID"] == "HunterSkill_000"
        )
        self.assertEqual(row["日文名称"], "攻撃")
        self.assertNotIn(
            "0x", "".join(str(v) for r in self.sheets["技能效果"] for v in r.values())
        )

    def test_group_skill_reads_through_open_skill(self):
        # 狱焰蛸之反叛 opens HunterSkill_154; the code maps it back and reads _ViolentData.
        link = next(
            l
            for l in self.links["links"]
            if l["skill"] == "HunterSkill_178"
            and "getSkillViolentAddDamage"
            in (self.links["functions"][l["function"]]["method"] or "")
        )
        self.assertEqual(link["via"], "HunterSkill_154")
        # The two values come from different data, chosen by an unnamed flag.
        self.assertEqual(
            self.value("HunterSkill_178", "追加伤害", 4, situation="读取 SkillData"), 50
        )
        self.assertEqual(
            self.value("HunterSkill_178", "追加伤害", 4, situation="读取 _Violent"), 85
        )

    def test_weapon_comes_first_in_brackets(self):
        # Bow ballistics: the weapon comes from the _Wp11Data parameter path.
        self.assertEqual(
            [
                self.value("HunterSkill_019", "最佳距离起点倍率", lv, "【弓】通常射击")
                for lv in (2, 3)
            ],
            [0.8, 0.65],
        )
        self.assertEqual(
            self.value("HunterSkill_019", "最佳距离起点倍率", 1, "【重弩】散弹"), 0.6
        )
        # A weapon's own action is listed under that weapon, never after a "；".
        self.assertEqual(
            self.value("HunterSkill_075", "回避无敌时间", 1, "【单手剑】后跳"), 0.7
        )
        applies = {r["适用"] for r in self.sheets["技能效果"]}
        self.assertFalse([a for a in applies if "【" in a[1:] or "WP" in a])

    def test_meal_and_baseline_values_are_left_out(self):
        # getDodgeNoHitTime also returns the time without the skill and with a
        # meal skill adding levels; only the skill's own table values remain.
        self.assertEqual(
            [
                self.value("HunterSkill_075", "回避无敌时间", lv, "翻滚")
                for lv in range(1, 6)
            ],
            [0.25, 0.283333, 0.316667, 0.366667, 0.416667],
        )

    def test_values_that_depend_on_battle_state_are_kept(self):
        # 连击 raises its element bonus after five hits: one row per stage.
        stages = [
            self.value("HunterSkill_114", "属性值加算", 1, "【双刀、弓】", stage)
            for stage in ("连续命中不足 5 次", "连续命中 5 次及以上")
        ]
        self.assertEqual(stages, [3, 4])

    def test_descriptions_drop_listed_remarks_and_line_breaks(self):
        explain = next(
            r["技能说明"]
            for r in self.sheets["技能效果"]
            if r["技能ID"] == "HunterSkill_114"
        )
        self.assertEqual(explain, "攻击连续命中时，攻击力和属性值会阶段性上升。")

    def test_meanings_name_shown_effects_and_fill_their_columns(self):
        shown = {
            (skill, key)
            for skill, items in effect_links(self.links).items()
            for _, _, key in items
        }
        listed = {
            (skill, key)
            for skill, entries in self.links["meanings"].items()
            for key in entries
        }
        self.assertEqual(listed - shown, set())
        # 蓄力大师: the slot multiplies the element value of a charged hit.
        row = next(
            r
            for r in self.sheets["技能效果"]
            if r["技能ID"] == "HunterSkill_048"
            and r["技能等级"] == "Lv.3"
            and r["效果"] == "蓄力攻击属性值倍率"
        )
        self.assertEqual(
            (row["数值"], row["计算"][:2], row["单位"]), (1.25, "乘算", "倍")
        )
        self.assertIn("_AttrValue", row["作用于"])

    def test_effect_names_read_the_accessor_name(self):
        self.assertEqual(effect_name("getSkillFireAttackAdd493160"), "火属性值加算")
        self.assertEqual(
            effect_name("getSkillFirstShotLightAttackAdd493431"), "攻击力加算（轻弩）"
        )
        self.assertEqual(
            effect_name("getSkillMoraleAttackAdd_ToNpc493404"), "攻击力加算（对NPC）"
        )

    def test_points_are_split_into_cartesian_blocks(self):
        points = [("S", 1), ("L", 2), ("S", 3), ("M", 3), ("L", 3)]
        blocks = sorted(
            (sorted(kinds), sorted(levels))
            for kinds, levels in cartesian_blocks(points)
        )
        self.assertEqual(blocks, [(["L"], [2, 3]), (["M"], [3]), (["S"], [1, 3])])

    def test_every_skill_level_row_is_listed(self):
        ids = {row["技能ID"] for row in self.sheets["技能"]}
        self.assertEqual(
            ids, {k for k, v in self.links["skills"].items() if v["inSkillCommonData"]}
        )

    def test_shards_cover_every_link_once(self):
        index = json.loads((LINKS_DIR / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(
            sum(s["links"] for s in index["shards"]), len(self.links["links"])
        )

    def test_missing_shard_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            for path in LINKS_DIR.glob("*.json"):
                shutil.copyfile(path, Path(temp) / path.name)
            next(
                p for p in Path(temp).glob("*.json") if p.name != "index.json"
            ).unlink()
            with self.assertRaisesRegex(ValueError, "分片与索引不一致"):
                load_links(Path(temp))


def path(value, sources, conditions=()):
    return dict(
        status="ok", value=value, sources=list(sources), conditions=list(conditions)
    )


class SituationTests(unittest.TestCase):
    def test_random_check_becomes_its_chance(self):
        rng = "((全局量 0x1548e8e88 shl 15) ^ 全局量 0x1548e8e88)"
        items = [
            ((), path(True, ["SkillData[S Lv1]._value[0]"], [f"80 > {rng}"])),
            ((), path(False, ["SkillData[S Lv1]._value[0]"], [f"80 <= {rng}"])),
        ]
        self.assertEqual(value_situations(items, {}), {None: {"80%"}})

    def test_values_split_by_flag_then_by_data_or_condition(self):
        move, wall = "PlayerSkillParam._EggMoveRate", "PlayerSkillParam._EggWallRate"
        items = [
            ((("1:Boolean", "false"),), path(1.25, [move])),
            ((("1:Boolean", "true"),), path(1.2, [wall])),
        ]
        names = {"参数1=true": "爬墙时"}
        self.assertEqual(
            value_situations(items, names), {"参数1 为 false": {1.25}, "爬墙时": {1.2}}
        )
        table = "PlayerSkillParam._Table._DataPack[{}]._Value"
        items = [
            ((), path(5, [table.format(1)], ["_HitCount < 5", "x == 0"])),
            ((), path(10, [table.format(3)], ["_HitCount >= 5", "x == 0"])),
        ]
        names = {"_HitCount < 5": "不足 5 次", "_HitCount >= 5": ""}
        # Same field, different entries: told apart by the conditions; a
        # condition named "" is left out, leaving that value unnamed.
        self.assertEqual(value_situations(items, names), {"不足 5 次": {5}, None: {10}})

    def test_other_effects_and_other_skills_are_not_own_values(self):
        own = path(0.5, ["SkillData[S Lv1]._value[0]"], ["flag >= limit"])
        melody = path(
            0.1,
            ["SkillData[S Lv1]._value[1]"],
            ["cHunterSkill._Wp05MusicSkill._SkillTimer+0x90 > 0.0"],
        )
        other = path(8.0, ["SkillData[T Lv4]._value[0]"])
        self.assertEqual(own_values([own, melody, other], {"S"}), [own])
        # Only another skill's row: nothing is the skill's own.
        self.assertEqual(own_values([other], {"S"}), [])


if __name__ == "__main__":
    unittest.main()
