import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.database.missions.text import MissionTextResolver
from src.shared.source.repository import SourceRepository
from src.shared.text.catalog import REJECTED, TextPolicy, TextSource, content_at
from src.shared.text.values import TextParts, TextRef, localize


class TextTests(unittest.TestCase):
    def test_guid_projection_is_explicit_and_does_not_mutate_template(self):
        guid = "11111111-1111-1111-1111-111111111111"
        rows = [{"Name": TextRef(guid), "Id": guid, "Materials": [TextParts((TextRef(guid), " x", 3))]}]
        self.assertEqual(localize(rows, lambda key: "Iron")[0],
                         {"Name": "Iron", "Id": guid, "Materials": ["Iron x3"]})
        self.assertEqual(localize(rows, lambda key: "铁")[0]["Name"], "铁")
        self.assertIsInstance(rows[0]["Name"], TextRef)
        self.assertEqual(localize(TextRef(guid), lambda key: None), "")

    def test_source_is_loaded_once_and_nested_mutation_is_isolated(self):
        guid = "11111111-1111-1111-1111-111111111111"
        with patch("src.shared.source.repository.load_user3_table", return_value=[
            {"Name": guid, "Id": guid, "Values": [{"x": 1}]},
        ]) as load:
            repository = SourceRepository(Path("unused"))
            first = repository.referenced_table("data.json")
            first[0]["Values"][0]["x"] = 7
            second = repository.table("data.json")
        load.assert_called_once()
        self.assertIsInstance(first[0]["Name"], TextRef)
        self.assertEqual(first[0]["Id"], guid)
        self.assertEqual(second[0]["Values"], [{"x": 1}])
        self.assertEqual(second[0]["Name"], guid)

    def test_policy_keeps_mission_newlines_and_discards_rejected(self):
        self.assertEqual(content_at(["a\r\nb\x01"], 0, TextPolicy.DATABASE), "ab")
        self.assertEqual(content_at(["a\r\nb\x01"], 0, TextPolicy.MISSION), "a\nb")
        self.assertEqual(content_at([REJECTED + "bad"], 0, TextPolicy.DATABASE), "bad")
        self.assertEqual(content_at([REJECTED + "bad"], 0, TextPolicy.MISSION), "")

    def test_duplicate_and_missing_references_keep_existing_semantics(self):
        source = TextSource([
            ("one", "ONE", [REJECTED + "old"]), ("one", "ONE", ["new"]),
            ("blank", "BLANK", [""]), ("ref", "REF", ["<REF BLANK>/<REF UNKNOWN>/<EMID EM001>"]),
            ("cycle", "CYCLE", ["<REF CYCLE>"]),
        ])
        database = source.build(0)
        self.assertFalse(database.is_rejected("one"))
        self.assertEqual(database.get("one"), "new")
        self.assertEqual(database.get("ref"), "/<REF UNKNOWN>/<EMID EM001>")
        self.assertEqual(database.get("cycle"), "<REF CYCLE>")
        self.assertEqual(MissionTextResolver(source, 0).get_guid("ref"), "<REF BLANK>/<REF UNKNOWN>/EM001")

    def test_language_views_are_bounded_and_english_fallback_is_preserved(self):
        source = TextSource([("title", "TITLE", ["", "English", "Français"])])
        for language in range(15):
            source.build(language)
        self.assertLessEqual(len(source._views), 2)
        self.assertEqual(MissionTextResolver(source, 0).get_guid("title"), "English")

    def test_language_discovery_reuses_message_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.msg.23.json").write_text(json.dumps({"languages": [0, 1, -1], "entries": []}), encoding="utf-8")
            (root / "b.msg.23.json").write_text(json.dumps({"languages": [0, -1, 2], "entries": []}), encoding="utf-8")
            source = TextSource.from_natives(root)
        self.assertEqual(source.language_ids, (0,))
        self.assertEqual(source.file_count, 2)
