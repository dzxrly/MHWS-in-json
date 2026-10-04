"""Prove that runtime packages interact through JSON, including isolated imports."""

import ast
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sdk.enemy_logic_exporter.monster import get_monster, iter_monsters
from sdk.enemy_logic_exporter.shared.extraction import ExtractionContext
from src.processed_data.enemy_battle_logic.definitions import EXPECTED_ENEMY_IDS

ROOT = Path(__file__).resolve().parents[2]


class PackageBoundaryTests(unittest.TestCase):
    def test_all_large_monsters_have_distinct_entries_and_training_is_rejected(self):
        modules = iter_monsters()
        self.assertEqual(
            tuple(module.ENEMY_ID for module in modules), EXPECTED_ENEMY_IDS
        )
        self.assertEqual(len({module.__file__ for module in modules}), 34)
        self.assertIsNot(get_monster("EM0002_00_0"), get_monster("EM0002_50_0"))
        with self.assertRaises(ValueError):
            get_monster("EM0165_00_0")

    def test_no_import_can_cross_the_sdk_src_boundary(self):
        for folder, forbidden in (
            (ROOT / "sdk/enemy_logic_exporter", "src"),
            (ROOT / "src", "sdk"),
        ):
            for path in folder.rglob("*.py"):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf8"))):
                    if isinstance(node, ast.ImportFrom):
                        names = [node.module or ""]
                    elif isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    else:
                        continue
                    self.assertFalse(
                        any(
                            name == forbidden or name.startswith(forbidden + ".")
                            for name in names
                        ),
                        str(path),
                    )

    def test_packages_work_with_the_other_package_blocked(self):
        scratch = ROOT / ".agents/test-runs"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            cases = (
                (
                    "src",
                    "from sdk.enemy_logic_exporter.monster import iter_monsters; assert len(iter_monsters()) == 34; from sdk.enemy_logic_exporter.shared.cli import parser; parser()",
                ),
                (
                    "sdk",
                    f"from src.processed_data.enemy_battle_logic.exporter import export_battle_logic; from src.processed_data.enemy_battle_logic.definitions import DEFAULT_TEMPLATE; export_battle_logic({directory!r}, template_path=DEFAULT_TEMPLATE)",
                ),
            )
            for forbidden, body in cases:
                code = f"""import sys
class Blocker:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == {forbidden!r} or fullname.startswith({forbidden + '.'!r}):
            raise AssertionError("cross-package import: " + fullname)
sys.meta_path.insert(0, Blocker())
{body}
"""
                result = subprocess.run(
                    [sys.executable, "-B", "-c", code],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf8",
                    errors="replace",
                    timeout=180,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_variant_scope_uses_its_declared_combat_and_keeps_method_aliases(self):
        source = "variant-combat.json"
        own_type = "app.Em0002_50_BTable_Combat_Export"
        monster = dict(
            enemyId="EM0002_50_0", slots={"COMBAT": source}, tableImportClosure=[source]
        )
        inventory = dict(
            profile={},
            monsters=[monster],
            resources=[dict(resource=source, exportType=own_type)],
        )
        rows = [
            dict(type=own_type, method="table_a", address="0x1000"),
            dict(type=own_type, method="table_b", address="0x1000"),
            dict(
                type="app.Em0002_00_BTable_Combat_Export",
                method="table_other",
                address="0x1000",
            ),
        ]
        result = get_monster("EM0002_50_0").extract(ExtractionContext(inventory, rows))
        self.assertEqual(
            [row["method"] for row in result["nativeMethods"]], ["table_a", "table_b"]
        )
        inventory["resources"][0]["exportType"] = "app.Em0002_00_BTable_Combat_Export"
        with self.assertRaisesRegex(ValueError, "归属"):
            get_monster("EM0002_50_0").extract(ExtractionContext(inventory, rows))
