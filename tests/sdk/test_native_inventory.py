"""Check real owner references and metadata coverage rather than monster name guesses."""

from pathlib import Path
import unittest

from sdk.enemy_logic_exporter.inventory import discover_inventory
from sdk.enemy_logic_exporter.__main__ import SUPPORTED_PROFILE

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(
    (ROOT / "src/data/il2cpp_dump.json").exists(), "需要匹配的 IL2CPP 元数据"
)
class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = discover_inventory(
            ROOT / "MHWS-in-json/natives",
            ROOT / "src/data/il2cpp_dump.json",
            SUPPORTED_PROFILE,
        )

    def test_all_real_monsters_and_spelling_variants_have_method_coverage(self):
        self.assertEqual(self.inventory["monsterCount"], 34)
        self.assertEqual(self.inventory["uniqueBTableResources"], 677)
        self.assertEqual(self.inventory["nativeTableMethodBindings"], 7210)
        monsters = {x["enemyId"] for x in self.inventory["monsters"]}
        self.assertNotIn("EM0165_00_0", monsters)
        combat = next(
            r
            for r in self.inventory["resources"]
            if r["exportType"] == "app.Em0152_00_Btable_Combat_Export"
        )
        self.assertEqual(combat["nativeTableMethods"], 72)

    def test_shared_variant_keeps_actual_resource_owner_and_unique_tables(self):
        variant = next(
            m for m in self.inventory["monsters"] if m["enemyId"] == "EM0160_50_0"
        )
        self.assertIn("/Em0160/00/", variant["slots"]["COMBAT"])
        self.assertIn("/Em0160/50/", variant["slots"]["REPEL"])
        self.assertEqual(len(self.inventory["shellNameCatalog"]), 31)
        self.assertEqual(
            sum(len(s["entries"]) for s in self.inventory["shellNameCatalog"]), 1142
        )
