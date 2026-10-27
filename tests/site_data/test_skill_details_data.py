"""The skill page data shows the same values as SkillDetails.xlsx."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from config import BASE_DIR, NATIVES_DIR, SUPPORT_FILES
from src.processed_data.skill_details.exporter import build_sheets, load_links
from src.site_data.skill_details import (
    OUTPUT_NAME,
    build_site_data,
    display,
    export_skill_data,
)
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import TextSource


class SkillWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repository = SourceRepository(NATIVES_DIR)
        text_source = TextSource.from_natives(NATIVES_DIR)
        links = load_links()
        cls.data = build_site_data(repository, text_source, links)
        cls.sheets = build_sheets(repository, text_source, links)
        cls.skills = {s["id"]: s for s in cls.data["skills"]}
        cls.repository, cls.text_source = repository, text_source

    def test_values_match_the_workbook(self):
        site = {
            (skill["id"], effect["name"], level, value["text"])
            for skill in self.data["skills"]
            for effect in skill["effects"]
            for row in effect["rows"]
            for level, value in row["values"].items()
        }
        workbook = {
            (
                r["技能ID"],
                r["效果"],
                int(r["技能等级"].removeprefix("Lv.")),
                display(r["数值"]),
            )
            for r in self.sheets["技能效果"]
        }
        self.assertEqual(site, workbook)

    def test_every_skill_is_listed_with_its_category(self):
        with_effects = {r["技能ID"] for r in self.sheets["技能效果"]}
        self.assertEqual(
            {s["id"] for s in self.data["skills"] if s["effects"]}, with_effects
        )
        self.assertEqual(self.skills["HunterSkill_000"]["name"], "攻击")
        self.assertEqual(self.skills["HunterSkill_000"]["category"], "武器技能")
        self.assertEqual(
            self.skills["HunterSkill_000"]["levelColumns"], [1, 2, 3, 4, 5]
        )

    def test_empty_internal_skills_link_to_the_code_mapping(self):
        skill = self.skills["HunterSkill_061"]
        self.assertEqual(skill["name"], skill["id"])
        self.assertEqual((skill["ja"], skill["explain"]), ("", ""))
        self.assertEqual(
            skill["mappedSkill"],
            {"id": "HunterSkill_171", "name": self.skills["HunterSkill_171"]["name"]},
        )
        self.assertIn("HunterSkill_061", self.skills["HunterSkill_171"]["openSkills"])
        self.assertNotIn("SkillCommon_", self.skills["HunterSkill_171"]["openSkills"])
        self.assertNotIn("SkillCommon_", self.skills["HunterSkill_171"]["explain"])
        for internal in self.skills.values():
            self.assertFalse(internal["name"].startswith("SkillCommon_"))
            if "mappedSkill" in internal:
                self.assertIn(internal["mappedSkill"]["id"], self.skills)
                self.assertEqual(internal["levels"], [])
                self.assertEqual(internal["effects"], [])

    def test_named_internal_skills_keep_their_own_content(self):
        # A future named internal skill must not be hidden by the remap alone.
        skill_id = "HunterSkill_061"
        common = next(
            r
            for r in self.repository.table(SUPPORT_FILES["skill_common"])
            if r["skillId"] == skill_id
        )
        overview = [dict(r) for r in self.sheets["技能"]]
        for row in overview:
            if row["技能ID"] == skill_id:
                row["简体中文名称"] = "已命名的启用技能"
                row["技能说明"] = "有实际说明"
        original_text = self.text_source.text

        def text(key, *args, **kwargs):
            if key in {common["skillName"], common["skillExplain"]}:
                return "有实际文本"
            return original_text(key, *args, **kwargs)

        with patch(
            "src.site_data.skill_details.build_sheets", return_value={"技能": overview}
        ), patch.object(self.text_source, "text", side_effect=text):
            data = build_site_data(self.repository, self.text_source, load_links())
        skill = next(s for s in data["skills"] if s["id"] == skill_id)
        self.assertEqual(skill["name"], "已命名的启用技能")
        self.assertNotIn("mappedSkill", skill)

    def test_resource_open_skill_is_not_a_confirmed_code_mapping(self):
        skill = self.skills["HunterSkill_093"]
        self.assertEqual(skill["name"], "HunterSkill_093")
        self.assertNotIn("mappedSkill", skill)
        self.assertEqual(
            skill["resourceOpenSkills"],
            [
                {
                    "id": "HunterSkill_219",
                    "name": self.skills["HunterSkill_219"]["name"],
                    "level": 3,
                }
            ],
        )

    def test_rows_read_across_levels(self):
        # 连击: one row per weapon group and hit count, Lv.1 to Lv.5 side by side.
        (effect,) = [
            e
            for e in self.skills["HunterSkill_114"]["effects"]
            if e["name"] == "基础攻击力加算"
        ]
        rows = {(r["applies"], r["situation"]): r["values"] for r in effect["rows"]}
        below = rows["", "连续命中不足 5 次"]
        self.assertEqual([below[lv]["text"] for lv in range(1, 6)], ["5"] * 5)
        self.assertEqual(effect["meaning"]["单位"], "点")

    def test_export_writes_the_page_data(self):
        scratch = BASE_DIR / ".tmp" / "test-runs"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = export_skill_data(Path(directory), self.repository, self.text_source)
            self.assertEqual(path, Path(directory) / OUTPUT_NAME)
            written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written, json.loads(json.dumps(self.data)))
