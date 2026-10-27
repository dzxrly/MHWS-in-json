"""The ActionMap constant guard checks code, callees, tables and declarations."""

from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from sdk.action_map_exporter.shared import native_validation as native


class Image:
    def __init__(self, base=0x1000):
        self.base = base
        self.image_base = base
        self.length = 12
        self.memory = {
            base: bytes.fromhex("8b051a000000e8f5010000c3"),
            base + 0x20: struct.pack("<ii", 600, 601),
            base + 0x200: b"\xc3",
        }

    def read_function_bytes(self, address, size):
        for start, data in self.memory.items():
            if start <= address < start + len(data):
                return data[address - start : address - start + size]
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def identity(owner, method):
    return dict(
        type=owner,
        method=method,
        parameters=[],
        parameterModifiers=[],
        returns="System.Int32",
        implFlags="HasThis",
    )


class ActionMapNativeRuleTests(unittest.TestCase):
    def setUp(self):
        work = Path(".tmp/action-map-migration")
        work.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "rules.json"
        self.image = Image()
        self.records = {
            "app.Rule": dict(
                methods={
                    "run100": dict(
                        function="1000",
                        returns=dict(type="System.Int32"),
                        params=[],
                        impl_flags="HasThis",
                    )
                },
                fields={"_State": dict(type="System.Int32", offset_from_base="0x10")},
            ),
            "app.Helper": dict(
                methods={
                    "pick200": dict(
                        function="1200",
                        returns=dict(type="System.Int32"),
                        params=[],
                        impl_flags="HasThis",
                    )
                }
            ),
            "app.Enum": dict(fields={"LEVEL": dict(default=1)}),
        }
        shape, _, _ = native._shape(self.image, self.image.base, self.image.length)
        self.proof = dict(
            schemaVersion=1,
            methods=[
                dict(
                    identity=identity("app.Rule", "run"),
                    body=dict(
                        boundary="unwind",
                        length=12,
                        maskedBytes=shape,
                        branches=[
                            dict(offset=6, method=identity("app.Helper", "pick"))
                        ],
                        ripChecks=[
                            dict(
                                offset=0,
                                kind="bytes",
                                bytes=struct.pack("<ii", 600, 601).hex(),
                            )
                        ],
                    ),
                )
            ],
            fieldChecks=[
                dict(
                    type="app.Rule",
                    field="_State",
                    fieldType="System.Int32",
                    offset="0x10",
                )
            ],
            enumChecks=[dict(type="app.Enum", field="LEVEL", value=1)],
            ruleConstants=dict(WEAPON_BODY_GROUP_OFFSET=5, PENETRATE_BOTTLE_OFFSET=400),
        )

    def verify(self):
        self.path.write_text(json.dumps(self.proof), encoding="utf8")
        with patch.object(native, "RULES_PATH", self.path), patch.object(
            native, "PeImage", return_value=self.image
        ), patch.object(
            native, "iter_il2cpp_types", return_value=list(self.records.items())
        ), patch.object(
            native,
            "_function_ranges",
            side_effect=lambda image: [(image.base, image.base + image.length)],
        ):
            return native.verify_native_rules("unused.exe", "unused.json")

    def test_current_shape_and_declared_rules_pass(self):
        self.assertEqual(
            self.verify(), dict(verifiedMethods=1, verifiedFields=1, verifiedEnums=1)
        )

    def test_method_suffix_and_relocation_are_not_fixed_addresses(self):
        self.image = Image(0x4000)
        detail = self.records["app.Rule"]["methods"].pop("run100")
        detail["function"] = "4000"
        self.records["app.Rule"]["methods"]["run999"] = detail
        self.records["app.Helper"]["methods"]["pick200"]["function"] = "4200"
        self.assertEqual(self.verify()["verifiedMethods"], 1)

    def test_changed_instruction_or_appended_tail_fails(self):
        self.image.memory[self.image.base] = bytes.fromhex("8b051a000000e8f501000090")
        with self.assertRaisesRegex(ValueError, "完整代码"):
            self.verify()
        self.image = Image()
        self.image.length = 13
        with self.assertRaisesRegex(ValueError, "长度"):
            self.verify()

    def test_changed_callee_identity_is_not_hidden_by_rel32_mask(self):
        self.image.memory[self.image.base] = bytes.fromhex("8b051a000000e8f6010000c3")
        with self.assertRaisesRegex(ValueError, "被调方"):
            self.verify()

    def test_changed_rip_data_fails_even_when_code_is_unchanged(self):
        self.image.memory[self.image.base + 0x20] = struct.pack("<ii", 999, 601)
        with self.assertRaisesRegex(ValueError, "查表值"):
            self.verify()

    def test_jump_table_targets_are_relative_to_the_resolved_method(self):
        self.proof["methods"][0]["body"]["ripChecks"] = [
            dict(offset=0, kind="jump_table", targets=[0, 6])
        ]
        self.image.memory[self.image.base + 0x20] = struct.pack("<ii", -32, -26)
        self.verify()
        self.image.memory[self.image.base + 0x20] = struct.pack("<ii", -32, -25)
        with self.assertRaisesRegex(ValueError, "分派表"):
            self.verify()

    def test_rip_type_guard_uses_current_metadata_instead_of_saved_address(self):
        self.records["app.Guard"] = dict(address="1234")
        self.proof["methods"][0]["body"]["ripChecks"] = [
            dict(offset=0, kind="class", type="app.Guard")
        ]
        self.image.memory[self.image.base + 0x20] = struct.pack("<Q", 0x1234)
        self.verify()
        self.records["app.Guard"]["address"] = "5678"
        with self.assertRaisesRegex(ValueError, "类型守卫"):
            self.verify()

    def test_changed_layout_enum_signature_and_rule_declaration_fail(self):
        cases = [
            (
                "layout",
                lambda: self.records["app.Rule"]["fields"]["_State"].update(
                    offset_from_base="0x14"
                ),
            ),
            (
                "enum",
                lambda: self.records["app.Enum"]["fields"]["LEVEL"].update(default=2),
            ),
            (
                "signature",
                lambda: self.records["app.Rule"]["methods"]["run100"].update(
                    returns=dict(type="System.Boolean")
                ),
            ),
            (
                "declaration",
                lambda: self.proof["ruleConstants"].update(PENETRATE_BOTTLE_OFFSET=401),
            ),
        ]
        original_records, original_proof = deepcopy(self.records), deepcopy(self.proof)
        for name, change in cases:
            with self.subTest(name=name):
                self.records, self.proof = deepcopy(original_records), deepcopy(
                    original_proof
                )
                change()
                with self.assertRaises(ValueError):
                    self.verify()

    def test_missing_or_ambiguous_method_fails(self):
        self.records["app.Rule"]["methods"]["run101"] = dict(
            self.records["app.Rule"]["methods"]["run100"]
        )
        with self.assertRaisesRegex(ValueError, "唯一定位"):
            self.verify()

    def test_unrelated_methods_still_bound_reviewed_functions(self):
        self.records["app.Unrelated"] = dict(
            methods={"other900": dict(function="100b")}
        )
        with self.assertRaisesRegex(ValueError, "长度"):
            self.verify()

    def test_unrelated_invalid_function_address_is_not_silently_skipped(self):
        self.records["app.Unrelated"] = dict(
            methods={"other900": dict(function="invalid-address")}
        )
        with self.assertRaises(ValueError):
            self.verify()


class SharedMetadataNativeRuleTests(ActionMapNativeRuleTests):
    """Run every native guard against the shared, single-pass index as well."""

    def verify(self):
        self.path.write_text(json.dumps(self.proof), encoding="utf8")
        with patch.object(native, "RULES_PATH", self.path), patch.object(
            native, "PeImage", return_value=self.image
        ), patch(
            "sdk.action_map_exporter.il2cpp_methods.iter_il2cpp_types",
            return_value=iter(self.records.items()),
        ) as reader, patch.object(
            native, "iter_il2cpp_types", side_effect=AssertionError("metadata reread")
        ), patch.object(
            native,
            "_function_ranges",
            side_effect=lambda image: [(image.base, image.base + image.length)],
        ):
            metadata = native.load_native_metadata("unused.json")
            try:
                result = native.verify_native_rules(
                    "unused.exe", "unused.json", metadata=metadata
                )
                metadata.select({"app.Rule"})
                return result
            finally:
                reader.assert_called_once()

    def test_shared_index_requires_current_source_and_strict_address_parsing(self):
        self.path.write_text(json.dumps(self.proof), encoding="utf8")
        with patch.object(native, "RULES_PATH", self.path):
            for source, strict in (("different.json", True), ("unused.json", False)):
                with self.subTest(source=source, strict=strict):
                    metadata = native.Il2CppMethodCatalog(
                        {},
                        [],
                        source_path=Path(source).resolve(),
                        strict_addresses=strict,
                    )
                    with self.assertRaisesRegex(ValueError, "索引来源"):
                        native.verify_native_rules(
                            "unused.exe", "unused.json", metadata=metadata
                        )


if __name__ == "__main__":
    unittest.main()
