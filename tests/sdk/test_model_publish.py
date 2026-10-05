"""Published web models drop research provenance and share repeated values."""

import json
from pathlib import Path
import tempfile
import unittest

from sdk.enemy_logic_exporter.shared.models.publish import (
    publish_models,
    share_values,
    strip_research_fields,
)
from sdk.enemy_logic_exporter.shared.models.io import expand_shared_values
from src.processed_data.enemy_battle_logic.model_io import (
    expand_shared_values as web_expand,
)

EVIDENCE = {"type": "app.Fixture", "method": "onExecute1", "address": "0x1", "end": "0x2", "nativeSha256": "0" * 64}


def model():
    nodes = [
        dict(
            id=str(i),
            kind="condition",
            argument={"_EditArg": "[1] LONG_ENOUGH_VALUE_FOR_SHARING"},
            commandType="app.Fixture",
            predicate=dict(
                status="verified",
                argument={"_EditArg": "[1] LONG_ENOUGH_VALUE_FOR_SHARING"},
                commandType="app.Fixture",
                evidence=EVIDENCE,
            ),
            nativeSite="0x10",
            nativeNodeIdentity="0x10",
            true="0",
            false="0",
        )
        for i in range(3)
    ]
    return dict(
        schemaVersion=1,
        enemyId="EM0002_00_0",
        tables=[dict(tableGuid="t", entry="0", nodes=nodes)],
        selectionRecovery=[{"large": "research"}],
    )


class ModelPublishTests(unittest.TestCase):
    def test_research_fields_and_predicate_duplicates_are_removed(self):
        stripped = strip_research_fields(model())
        node = stripped["tables"][0]["nodes"][0]
        self.assertNotIn("nativeSite", node)
        self.assertNotIn("nativeNodeIdentity", node)
        self.assertNotIn("argument", node["predicate"])
        self.assertEqual(node["predicate"]["evidence"], EVIDENCE)
        self.assertNotIn("selectionRecovery", stripped)

    def test_shared_values_round_trip_in_both_loaders(self):
        stripped = strip_research_fields(model())
        packed = share_values(stripped)
        self.assertTrue(packed["sharedValues"])
        text = json.dumps(packed)
        self.assertEqual(text.count("LONG_ENOUGH_VALUE_FOR_SHARING"), 1)
        self.assertEqual(expand_shared_values(json.loads(text)), stripped)
        self.assertEqual(web_expand(json.loads(text)), stripped)

    def test_invalid_references_and_reference_shaped_values_are_rejected(self):
        packed = share_values(strip_research_fields(model()))
        packed["tables"] = [{"$": 999}]
        with self.assertRaisesRegex(ValueError, "引用无效"):
            web_expand(packed)
        with self.assertRaisesRegex(ValueError, "格式冲突"):
            share_values(dict(model(), extra={"$": 1}))

    def test_publish_refuses_an_already_published_model(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder, "source"), Path(folder, "out")
            source.mkdir()
            (source / "em0002_00_0.v1.json").write_text(json.dumps(model()))
            rows = publish_models(source, output)
            self.assertLess(rows[0]["publishedBytes"], rows[0]["sourceBytes"])
            with self.assertRaisesRegex(ValueError, "完整研究模型"):
                publish_models(output, Path(folder, "again"))
