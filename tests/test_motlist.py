import json
import tempfile
import unittest
from pathlib import Path

from src.data.motlist import (
    MOTLIST_JSON_FORMAT,
    infer_weapon_scope,
    load_motlist_request_set_relations,
)


class MotlistRelationTests(unittest.TestCase):
    def test_loader_uses_format_and_source_path_instead_of_root_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = (
                root
                / "future"
                / "MHWS-in-json"
                / "natives"
                / "arbitrary"
                / "wp00_00.motlist.992.json"
            )
            path.parent.mkdir(parents=True)
            _write_document(
                path,
                "STM/Motion/Player/Weapon/Wp00/wp00_00/wp00_00.motlist.992",
                [
                    {"motionId": 358, "motionName": "wp00_00_352", "requestSetId": 1060},
                    {"motionId": 359, "motionName": "wp00_00_352", "requestSetId": 1060},
                    {"motionId": 360, "motionName": "", "requestSetId": 1061},
                ],
            )

            catalog = load_motlist_request_set_relations(root)

        self.assertEqual(catalog.documents, 1)
        self.assertEqual(catalog.documents_with_mappings, 1)
        self.assertEqual(catalog.source_mappings, 3)
        self.assertEqual(catalog.unnamed_mappings, 1)
        self.assertEqual(catalog.unscoped_mappings, 0)
        self.assertEqual(len(catalog.relations), 1)
        relation = catalog.relations[0]
        self.assertEqual(relation.scope, "Wp00")
        self.assertEqual(relation.request_set_id, 1060)
        self.assertEqual(relation.motion_name, "wp00_00_352")
        self.assertEqual(relation.motion_id, 358)

    def test_loader_rejects_unknown_contract_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.motlist.999.json"
            path.write_text(
                json.dumps(
                    {
                        "_format": "future_motlist_contract_v2",
                        "sourcePath": "STM/Motion/Player/Weapon/Wp00/sample.motlist.999",
                        "requestSetMappings": [],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Unsupported motlist JSON format"):
                load_motlist_request_set_relations(Path(temp_dir))

    def test_scope_fallback_is_limited_to_player_motion_paths(self) -> None:
        self.assertEqual(
            infer_weapon_scope(
                "STM/Motion/Player/Common/common.motlist.992",
                "wp03_00_100",
            ),
            "Wp03",
        )
        self.assertEqual(
            infer_weapon_scope(
                "STM/Motion/Enemy/em0001/em0001.motlist.992",
                "wp03_00_100",
            ),
            "",
        )


def _write_document(path: Path, source_path: str, mappings: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "_format": MOTLIST_JSON_FORMAT,
                "sourcePath": source_path,
                "requestSetMappings": mappings,
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
