"""Declared variant resources can intentionally use a base-form Combat owner."""

import unittest
from unittest.mock import Mock

from sdk.enemy_logic_exporter.monster import em0160_50_0
from sdk.enemy_logic_exporter.shared.extraction import ExtractionContext
from sdk.enemy_logic_exporter.shared.resources import Resources


class VariantResourceScopeTests(unittest.TestCase):
    def context(self, combat_owner="app.Em0160_00_BTable_Combat_Export"):
        base = "STM/GameDesign/Enemy/Em0160/00/BTable/"
        variant = "STM/GameDesign/Enemy/Em0160/50/BTable/"
        combat = base + "Em0160_00_BTable_Combat.user.3.json"
        common = base + "Em0160_00_BTable_CommonAttack.user.3.json"
        repel = variant + "Em0160_50_BTable_Repel.user.3.json"
        listed = variant + "Em0160_50_BTableList.user.3.json"
        unrelated = base + "Em0160_00_BTable_Predator.user.3.json"

        def reference(source):
            return {"ace.btable.user_data.BTable": {"path": source}}

        data = {
            listed: {
                "_Table_COMBAT": reference(combat),
                "_Table_REPEL": reference(repel),
            },
            combat: {
                "_ExportBTableType": combat_owner,
                "_ImportBTableList": [reference(common)],
            },
            common: {
                "_ExportBTableType": "app.Em0160_00_BTable_CommonAttack_Export",
                "_ImportBTableList": [],
            },
            repel: {
                "_ExportBTableType": "app.Em0160_50_BTable_Repel_Export",
                "_ImportBTableList": [],
            },
            unrelated: {
                "_ExportBTableType": "app.Em0160_00_BTable_Predator_Export",
                "_ImportBTableList": [],
            },
        }
        resources = Resources.__new__(Resources)
        resources.resolve = Mock(
            side_effect=lambda source: (
                source if source in data else self.fail("undeclared fixture source")
            )
        )
        resources.read = Mock(side_effect=data.__getitem__)
        # Resolve the actual typed declarations and imports. No enemy-ID prefix
        # or array position is used to decide which table is Combat.
        slots = {
            key[7:]: resources.reference(value)
            for key, value in resources.read(listed).items()
            if key.startswith("_Table_")
        }
        closure, pending = set(), list(slots.values())
        while pending:
            source = pending.pop()
            if source in closure:
                continue
            closure.add(source)
            pending.extend(
                resources.table_references(resources.read(source)["_ImportBTableList"])
            )
        inventory = {
            "profile": {"version": "fixture"},
            "monsters": [
                {
                    "enemyId": "EM0160_50_0",
                    "btableList": listed,
                    "slots": slots,
                    "tableImportClosure": sorted(closure),
                }
            ],
            "resources": [
                {"resource": source, "exportType": body["_ExportBTableType"]}
                for source, body in data.items()
                if "_ExportBTableType" in body
            ],
        }
        rows = [
            {"type": body["_ExportBTableType"], "method": source}
            for source, body in data.items()
            if "_ExportBTableType" in body
        ]
        return (
            ExtractionContext(inventory, rows),
            resources,
            combat,
            common,
            repel,
            unrelated,
        )

    def test_variant_identity_keeps_declared_base_combat_and_variant_repel(self):
        context, resources, combat, common, repel, unrelated = self.context()
        result = em0160_50_0.extract(context)
        self.assertEqual(result["enemyId"], "EM0160_50_0")
        self.assertEqual(result["nativeOwner"], "Em0160_00")
        self.assertEqual(result["combatResource"], combat)
        self.assertEqual(result["slots"]["REPEL"], repel)
        self.assertEqual(set(result["resources"]), {combat, common, repel})
        self.assertEqual(
            {row["method"] for row in result["nativeMethods"]}, {combat, common, repel}
        )
        self.assertNotIn(unrelated, result["resources"])
        self.assertIn(
            "app.Em0160_50_BTable_Repel_Export",
            {row["type"] for row in result["nativeMethods"]},
        )
        resources.read.assert_any_call(combat)
        resources.read.assert_any_call(repel)
        self.assertFalse(result["semanticReviewComplete"])

    def test_declared_combat_owner_must_match_even_when_identity_is_variant(self):
        context, *_ = self.context("app.Em0159_00_BTable_Combat_Export")
        with self.assertRaisesRegex(ValueError, "Combat"):
            em0160_50_0.extract(context)


if __name__ == "__main__":
    unittest.main()
