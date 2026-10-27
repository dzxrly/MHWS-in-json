from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ijson

from sdk.action_map_exporter.il2cpp_methods import Il2CppMethodCatalog
from sdk.action_map_exporter.shared.il2cpp import iter_il2cpp_types


class Il2CppMetadataTests(unittest.TestCase):
    def test_single_scan_retains_only_review_records_and_selects_ancestors(self):
        document = {
            "app.Base": {
                "fields": {
                    "_MotionId": {
                        "type": "System.UInt32",
                        "offset_from_base": "0x10",
                    }
                },
                "methods": {".ctor1": {"function": "1000"}},
            },
            "app.Child": {
                "parent": "app.Base",
                "methods": {"run2": {"function": "1100"}},
            },
            "app.Unrelated": {"methods": {"next3": {"function": "1104"}}},
            "app.Rule": {
                "address": "3000",
                "fields": {"VALUE": {"default": 7}},
                "methods": {"check4": {"function": "2000"}},
                "unused_large_record": {"not_retained": True},
            },
        }
        with patch(
            "sdk.action_map_exporter.il2cpp_methods.iter_il2cpp_types",
            return_value=iter(document.items()),
        ) as reader:
            index = Il2CppMethodCatalog.load(
                Path("metadata.json"),
                record_types={"app.Rule"},
                strict_addresses=True,
            )
            methods = index.select({"app.Child"})
            index.select({"app.Base"})
            reader.assert_called_once()
        self.assertEqual(set(index.records), {"app.Rule"})
        self.assertNotIn("unused_large_record", index.records["app.Rule"])
        self.assertEqual(methods.function_addresses, [0x1000, 0x1100, 0x1104, 0x2000])
        self.assertEqual(set(methods.target_methods), {"app.Child", "app.Base"})
        self.assertEqual(methods.lineage("app.Child"), ("app.Child", "app.Base"))
        self.assertEqual(methods.motion_fields("app.Child")[0x10].name, "_MotionId")
        self.assertEqual(
            methods.constructor_at("app.Child", 0x1000).type_name,
            "app.Base",
        )

    def test_strict_index_rejects_invalid_method_mappings(self):
        for methods in (None, [], "invalid"):
            with self.subTest(methods=methods), patch(
                "sdk.action_map_exporter.il2cpp_methods.iter_il2cpp_types",
                return_value=iter([("app.Bad", {"methods": methods})]),
            ):
                with self.assertRaisesRegex(ValueError, "methods must be an object"):
                    Il2CppMethodCatalog.load(
                        Path("metadata.json"), strict_addresses=True
                    )

    def test_structural_reader_handles_formatting_escaping_and_nested_names(
        self,
    ) -> None:
        document = {
            "unrelated": {
                "app.Sample_Fixed": {
                    "parent": "System.Enum",
                    "fields": {"WRONG": {"default": 7}},
                }
            },
            'type.with.escaped"name': {"methods": {'m"ethod': {"function": "0x1234"}}},
            "app.Sample_Fixed": {
                "fields": {"SAMPLE": {"default": 7}},
                "parent": "System.Enum",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            for index, indent in enumerate((None, 2, 4, "\t")):
                with self.subTest(indent=indent):
                    path = Path(directory) / f"dump-{index}.json"
                    path.write_text(
                        json.dumps(document, indent=indent), encoding="utf-8"
                    )
                    methods = Il2CppMethodCatalog.load(path, {'type.with.escaped"name'})
                    self.assertEqual(methods.function_addresses, [0x1234])
                    self.assertEqual(
                        methods.target_methods['type.with.escaped"name'][0].method_name,
                        'm"ethod',
                    )
            bom_path = Path(directory) / "bom.json"
            bom_path.write_text(json.dumps(document), encoding="utf-8-sig")
            self.assertEqual(dict(iter_il2cpp_types(bom_path)), document)

    def test_invalid_or_truncated_dump_is_not_silently_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dump.json"
            for text in ("[]", "", '{"app.A": {"fields": {}}'):
                with self.subTest(text=text):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises((ValueError, ijson.JSONError)):
                        list(iter_il2cpp_types(path))


if __name__ == "__main__":
    unittest.main()
