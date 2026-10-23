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
    format_cases,
    load_links,
)
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

    def effect(self, skill, function, levels, args=""):
        rows = [
            r
            for r in self.sheets["技能效果"]
            if r["技能ID"] == skill
            and r["函数"] == function
            and r["等级"] == levels
            and r["参数"] == args
            and not r["运行时条件"]
        ]
        self.assertEqual(len(rows), 1, (skill, function, levels, args, rows))
        return rows[0]

    def test_attack_values_follow_skill_data_slots(self):
        # 1.42.0.2: getSkillAttackRate = value[0] * 0.01, getSkillAttackAdd = value[1].
        self.assertEqual(
            self.effect("HunterSkill_000", "cHunterSkill.getSkillAttackRate", "4")[
                "结果"
            ],
            "1.02",
        )
        add = self.effect("HunterSkill_000", "cHunterSkill.getSkillAttackAdd", "5")
        self.assertEqual(add["结果"], "9")
        self.assertIn("SkillData[HunterSkill_000 Lv5]._value[1]", add["数据来源"])

    def test_group_skill_reads_through_open_skill(self):
        # 狱焰蛸之反叛 opens HunterSkill_154; the code maps it back and reads _ViolentData.
        row = self.effect(
            "HunterSkill_178",
            "cHunterSkill.getSkillViolentAddDamage",
            "4",
            "1:Boolean=true",
        )
        self.assertEqual(row["结果"], "85")
        self.assertEqual(row["代码引用的技能"].split("（")[0], "HunterSkill_154")
        self.assertIn(
            "PlayerSkillParam._ViolentData._DataPack[2]._Value", row["数据来源"]
        )

    def test_cases_are_split_into_cartesian_blocks(self):
        domains = {"1:Kind": ["S", "M", "L"]}
        cases = [
            {"level": 1, "args": {"1:Kind": "S"}},
            {"level": 2, "args": {"1:Kind": "L"}},
            {"level": 3, "args": {"1:Kind": "S"}},
            {"level": 3, "args": {"1:Kind": "M"}},
            {"level": 3, "args": {"1:Kind": "L"}},
        ]
        self.assertEqual(
            format_cases(cases, domains),
            [("1,3", "1:Kind=S"), ("2,3", "1:Kind=L"), ("3", "1:Kind=M")],
        )

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
        self.assertEqual(self.links["gameVersion"], index["gameVersion"])

    def test_missing_shard_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            for path in LINKS_DIR.glob("*.json"):
                shutil.copyfile(path, Path(temp) / path.name)
            next(
                p for p in Path(temp).glob("*.json") if p.name != "index.json"
            ).unlink()
            with self.assertRaisesRegex(ValueError, "分片与索引不一致"):
                load_links(Path(temp))


if __name__ == "__main__":
    unittest.main()
