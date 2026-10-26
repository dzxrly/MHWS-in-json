"""The offline skill page shows the same values as SkillDetails.xlsx."""

import json
import re
import unittest

from config import NATIVES_DIR
from src.processed_data.skill_details.exporter import build_sheets, load_links
from src.processed_data.skill_details.web import (
    build_site_data,
    display,
    render_html,
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

    def test_page_embeds_the_data(self):
        html = render_html(self.data)
        self.assertNotRegex(html, r"__(CSS|JS|DATA|SCOPE)__")
        payload = re.search(
            r'<script id="data" type="application/json">(.*?)</script>', html, re.S
        )
        self.assertEqual(
            json.loads(payload.group(1))["skills"][0]["id"], "HunterSkill_000"
        )
        self.assertNotIn("http://", html.replace("http://www.w3.org", ""))
