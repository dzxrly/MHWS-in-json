"""JSON adapters and independent CLI boundaries for the migrated producer."""

import ast
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sdk.action_map_exporter.__main__ import parser
from sdk.action_map_exporter.builder import (
    ActionMapOptions,
    build_action_map,
    _shell_prefab_count,
)
from sdk.action_map_exporter.models import PfbResourceDocument
from types import SimpleNamespace
from sdk.action_map_exporter.motion_catalogs import MotbankCatalog
from sdk.action_map_exporter.pfb import PfbResourceCatalog
from sdk.action_map_exporter.shared.json_io import write_json_atomic


def write(root, relative, document):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


class JsonResourcesTests(unittest.TestCase):
    def test_shell_statistic_excludes_extra_weapon_and_player_dependencies(self):
        documents = [
            PfbResourceDocument(
                "GameDesign/Player/ActionData/Wp00/Shell/Root.pfb", "", ()
            ),
            PfbResourceDocument("Outside/DirectShell.pfb", "", ()),
            PfbResourceDocument("GameDesign/Equip/_Prefab/Weapon/Wp00.pfb", "", ()),
            PfbResourceDocument("GameDesign/Player/_Prefab/Runtime/Player.pfb", "", ()),
        ]
        prefabs = PfbResourceCatalog(documents)
        shells = SimpleNamespace(
            entries=[SimpleNamespace(prefab_path="Outside/DirectShell.pfb")]
        )
        self.assertEqual(len(prefabs.documents), 4)
        self.assertEqual(_shell_prefab_count(prefabs, shells), 2)

    def test_weapon_banks_use_exported_identity_and_all_fourteen_scopes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number in range(14):
                source = (
                    f"STM/Motion/Player/Weapon/Wp{number:02d}/wp{number:02d}.motbank.4"
                )
                write(
                    root,
                    source + ".json",
                    {
                        "_format": "re_engine_motbank_v1",
                        "sourcePath": source,
                        "motlists": [
                            {
                                "bankId": 20,
                                "bankType": 0,
                                "path": f"Motion/Player/Weapon/Wp{number:02d}/Main.motlist",
                            },
                            {
                                "bankId": 21,
                                "bankType": 1,
                                "path": f"Motion/Player/Weapon/Wp{number:02d}/Tree.motlist.992",
                            },
                        ],
                    },
                )
            catalog = MotbankCatalog.load_from_directory(root)
            self.assertEqual(len(catalog.entries), 28)
            self.assertEqual(
                {x.scope for x in catalog.entries}, {f"Wp{i:02d}" for i in range(14)}
            )
            self.assertEqual(
                catalog.entries[0].source_path,
                "STM/Motion/Player/Weapon/Wp00/wp00.motbank.4",
            )
            self.assertEqual(catalog.entries[1].bank_type, 1)
            self.assertTrue(catalog.entries[1].motlist_path.endswith("/Tree.motlist"))
            path = root / "STM/Motion/Player/Weapon/Wp13/wp13.motbank.4.json"
            path.unlink()
            with self.assertRaisesRegex(ValueError, "Wp13"):
                MotbankCatalog.load_from_directory(root)

    def test_prefab_resource_table_keeps_archive_paths_and_follows_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = "STM/GameDesign/Player/ActionData/Wp00/Shell/"
            write(
                root,
                prefix + "Root.pfb.18.json",
                {
                    "_format": "mhws_pfb_v1",
                    "resources": [
                        "Other/Child.pfb",
                        "GameDesign/Player/ActionData/Wp00/Collision/A.rcol",
                        "GameDesign/Player/ActionData/Wp00/Collision/A.rcol",
                    ],
                },
            )
            write(
                root,
                "STM/Other/Child.pfb.18.json",
                {
                    "_format": "mhws_pfb_v1",
                    "resources": [
                        "GameDesign/Player/ActionData/Wp00/Shell/Root.pfb",
                        "Other/B.rcol",
                    ],
                },
            )
            catalog = PfbResourceCatalog.load_from_directory(
                root,
                [
                    "GameDesign/Player/ActionData/Wp00/Shell/Root.pfb",
                ],
            )
            self.assertEqual(len(catalog.documents), 2)
            self.assertEqual(catalog.missing_prefabs, ())
            document = catalog.find(
                "natives/STM/GameDesign/Player/ActionData/Wp00/Shell/Root.pfb.18"
            )
            self.assertEqual(
                document.archive_path,
                "natives/STM/" + prefix.removeprefix("STM/") + "Root.pfb.18",
            )
            self.assertEqual(len(document.resources), 2)
            resolved = catalog.find_rcol_resources(document.prefab_path)
            self.assertEqual(
                [resource for _, resource in resolved],
                [
                    "GameDesign/Player/ActionData/Wp00/Collision/A.rcol",
                    "Other/B.rcol",
                ],
            )
            self.assertEqual([len(chain) for chain, _ in resolved], [1, 2])
            write(
                root,
                "STM/Other/Child.pfb.19.json",
                {"_format": "mhws_pfb_v1", "resources": []},
            )
            with self.assertRaisesRegex(ValueError, "同一 PFB"):
                PfbResourceCatalog.load_from_directory(root, ["Other/Child.pfb"])

    def test_required_prefab_roots_and_nested_dependencies_must_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(FileNotFoundError, "missing.pfb"):
                PfbResourceCatalog.load_from_directory(root, ["Missing.pfb"])
            write(
                root,
                "STM/Root.pfb.18.json",
                {"_format": "mhws_pfb_v1", "resources": ["Other/Child.pfb"]},
            )
            write(
                root,
                "STM/Other/Child.pfb.18.json",
                {"_format": "mhws_pfb_v1", "resources": ["Missing.pfb"]},
            )
            with self.assertRaisesRegex(
                FileNotFoundError, r"missing.pfb.*Other/Child.pfb.18"
            ):
                PfbResourceCatalog.load_from_directory(root, ["Root.pfb"])

    def test_unrelated_duplicate_and_malformed_prefabs_are_outside_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(
                root,
                "STM/Needed.pfb.18.json",
                {"_format": "mhws_pfb_v1", "resources": []},
            )
            for version in (18, 19):
                write(root, f"STM/Unrelated.pfb.{version}.json", {})
            (root / "STM/Unrelated.pfb.18.json").write_text(
                "not JSON", encoding="utf-8"
            )
            catalog = PfbResourceCatalog.load_from_directory(root, ["Needed.pfb"])
            self.assertEqual([d.prefab_path for d in catalog.documents], ["Needed.pfb"])

    def test_required_nested_prefab_ambiguity_is_rejected_at_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(
                root,
                "STM/Needed.pfb.18.json",
                {"_format": "mhws_pfb_v1", "resources": ["Other/Child.pfb"]},
            )
            for version in (18, 19):
                write(
                    root,
                    f"STM/Other/Child.pfb.{version}.json",
                    {"_format": "mhws_pfb_v1", "resources": []},
                )
            with self.assertRaisesRegex(
                ValueError, r"同一 PFB other/child.pfb.*Needed.pfb.18"
            ):
                PfbResourceCatalog.load_from_directory(root, ["Needed.pfb"])

    def test_malformed_prefab_does_not_become_an_empty_resource_table(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for payload in (
                {},
                {"_format": "mhws_pfb_v1"},
                {"_format": "mhws_pfb_v1", "resources": [7]},
            ):
                write(root, "STM/Root.pfb.18.json", payload)
                with self.assertRaises(ValueError):
                    PfbResourceCatalog.load_from_directory(root, ["Root.pfb"])


class ExportBoundaryTests(unittest.TestCase):
    def test_cli_uses_explicit_dump_or_environment_without_guessing_game_paths(self):
        with patch.dict(os.environ, {}, clear=True):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(
                SystemExit
            ):
                parser().parse_args(["extract"])
            args = parser().parse_args(
                ["extract", "-e", "dump.exe", "-i", "metadata.json"]
            )
            self.assertEqual(args.exe, Path("dump.exe"))
            self.assertEqual(args.natives.name, "natives")
            self.assertEqual(args.output.name, "ActionMap.json")
        with patch.dict(
            os.environ,
            {"MHWS_EXE": "from-env.exe", "MHWS_IL2CPP": "from-env.json"},
            clear=True,
        ):
            args = parser().parse_args(["extract"])
            self.assertEqual(args.exe, Path("from-env.exe"))
            self.assertEqual(args.il2cpp, Path("from-env.json"))
            override = parser().parse_args(["extract", "-e", "override.exe"])
            self.assertEqual(override.exe, Path("override.exe"))

    def test_atomic_write_failure_preserves_previous_document(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "ActionMap.json"
            target.write_bytes(b"previous")
            with self.assertRaises(TypeError):
                write_json_atomic(target, {"invalid": object()})
            self.assertEqual(target.read_bytes(), b"previous")
            self.assertEqual(list(target.parent.glob("*.tmp")), [])
            write_json_atomic(target, {"x": float("inf")})
            self.assertEqual(
                json.loads(target.read_text(encoding="utf-8")), {"x": "Infinity"}
            )

    def test_native_review_precedes_resources_and_keeps_old_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / "dump.exe"
            metadata = root / "metadata.json"
            output = root / "ActionMap.json"
            exe.write_bytes(b"fixture")
            metadata.write_text("{}", encoding="utf-8")
            output.write_bytes(b"previous")
            options = ActionMapOptions(exe, metadata, root, output)
            with patch(
                "sdk.action_map_exporter.shared.native_validation.verify_native_rules",
                side_effect=ValueError("changed native"),
            ), patch(
                "sdk.action_map_exporter.builder.ActionDataCatalog.load"
            ) as resource:
                with self.assertRaisesRegex(ValueError, "changed native"):
                    build_action_map(options)
                resource.assert_not_called()
            self.assertEqual(output.read_bytes(), b"previous")

    def test_required_prefab_failure_preserves_previous_action_map(self):
        for ambiguous in (False, True):
            with self.subTest(
                ambiguous=ambiguous
            ), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                exe, metadata, output = (
                    root / name
                    for name in ("dump.exe", "metadata.json", "ActionMap.json")
                )
                exe.write_bytes(b"fixture")
                metadata.write_text("{}", encoding="utf-8")
                output.write_bytes(b"previous")
                write(
                    root,
                    "STM/Needed.pfb.18.json",
                    {"_format": "mhws_pfb_v1", "resources": ["Child.pfb"]},
                )
                if ambiguous:
                    for version in (18, 19):
                        write(
                            root,
                            f"STM/Child.pfb.{version}.json",
                            {"_format": "mhws_pfb_v1", "resources": []},
                        )
                stubs = {
                    "shared.native_validation.load_native_metadata": object(),
                    "shared.native_validation.verify_native_rules": None,
                    "builder.ActionDataCatalog.load": SimpleNamespace(
                        actions=[], natives_directory=root
                    ),
                    "builder.MotbankCatalog.load_from_directory": SimpleNamespace(
                        entries=[]
                    ),
                    "builder.MotlistJsonCatalog.load": SimpleNamespace(documents=[]),
                    "builder.MotionTargetCatalog.build": SimpleNamespace(targets=[]),
                    "builder.MotionGroupCatalog.load": SimpleNamespace(
                        groups=[], verified_extends=0
                    ),
                    "builder.RequestSetCatalog.load": SimpleNamespace(records=[]),
                    "builder.TrackColliderCatalog.load": SimpleNamespace(routes=[]),
                    "builder.ShellCatalog.load": SimpleNamespace(
                        entries=[SimpleNamespace(prefab_path="Needed.pfb")]
                    ),
                }
                with contextlib.ExitStack() as stack:
                    for target, result in stubs.items():
                        stack.enter_context(
                            patch(
                                "sdk.action_map_exporter." + target, return_value=result
                            )
                        )
                    with self.assertRaises(
                        ValueError if ambiguous else FileNotFoundError
                    ):
                        build_action_map(ActionMapOptions(exe, metadata, root, output))
                self.assertEqual(output.read_bytes(), b"previous")
                self.assertEqual(list(root.glob("*.tmp")), [])

    def test_production_package_imports_no_consumer_or_retired_runtime(self):
        package = Path(__file__).resolve().parents[3] / "sdk/action_map_exporter"
        forbidden = {
            "src",
            "core",
            "action_map",
            "rcol",
            "motlist",
            "pythonnet",
            "clr",
            "System",
        }
        for path in package.rglob("*.py"):
            module = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    self.assertFalse(
                        {n.name.split(".")[0] for n in node.names} & forbidden,
                        str(path),
                    )
                elif isinstance(node, ast.ImportFrom) and not node.level:
                    self.assertNotIn(
                        (node.module or "").split(".")[0], forbidden, str(path)
                    )


if __name__ == "__main__":
    unittest.main()
