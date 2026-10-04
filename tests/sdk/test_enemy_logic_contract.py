"""Regress context-preserving evidence storage and semantic coverage gates."""

from copy import deepcopy
import json
import unittest

from sdk.enemy_logic_exporter.shared.evidence import pack_methods, method_rows
from sdk.enemy_logic_exporter.shared.manifest import selected
from sdk.enemy_logic_exporter.shared.expressions import evaluate_expression
from sdk.enemy_logic_exporter.shared.predicates import RuleRegistry
from sdk.enemy_logic_exporter.shared.model_io import MODEL_LIMIT_BYTES, read_json
from src.processed_data.enemy_battle_logic.audit import (
    validate_release_graph,
    discovery_digest,
)
from pathlib import Path
from unittest.mock import patch


class EvidenceTests(unittest.TestCase):
    def test_btable_spelling_variants_and_interrupt_manager_are_discovered(self):
        self.assertTrue(
            selected(
                "app.Em0152_00_Btable_Combat_Export", "table_guid", "Em0152_00", "all"
            )
        )
        self.assertTrue(
            selected(
                "app.Em0001_00_Btable_Ride_Export",
                "updateTableInpl",
                "Em0001_00",
                "base",
            )
        )
        self.assertTrue(
            selected(
                "app.cEmAIStateManager", "onBeforePushInterrupt", "Em0001_00", "all"
            )
        )
        self.assertFalse(
            selected(
                "app.Em0152_00_Btable_Combat_Export", "table_guid", "Em0001_00", "all"
            )
        )

    def test_shared_code_does_not_merge_different_type_contexts(self):
        base = dict(
            address="0x1000",
            end="0x1010",
            nativeSha256="a" * 64,
            addressAliases=[["first", "execute"], ["second", "execute"]],
        )
        rows = [
            dict(
                base,
                type="first",
                method="execute",
                parameters=["bool"],
                fields={"a": 1},
            ),
            dict(
                base,
                type="second",
                method="execute",
                parameters=["int"],
                fields={"b": 2},
            ),
        ]
        packed = pack_methods(rows, {"gameVersion": "fixture"})
        self.assertEqual(method_rows(packed), rows)
        self.assertEqual(len(packed["nativeCode"]), 1)
        self.assertEqual(len(packed["methods"]), 2)
        self.assertEqual(len(packed["fieldsByType"]), 2)
        self.assertNotIn("addressAliases", packed["methods"][0])

    def test_repeated_aliases_are_serialized_once(self):
        aliases = [["type" + str(i), "method"] for i in range(1000)]
        rows = [
            dict(
                type="type",
                method="method" + str(i),
                fields={},
                parameters=[],
                address="0x1000",
                end="0x1010",
                nativeSha256="a" * 64,
                addressAliases=aliases,
            )
            for i in range(50)
        ]
        packed = pack_methods(rows, {})
        self.assertLess(len(json.dumps(packed)), len(json.dumps(rows)) // 10)
        self.assertEqual(method_rows(packed), rows)

    def test_all_selection_includes_scheduler_parent_and_special_command(self):
        for name, method in [
            ("app.cEmAIStateCombat", "onEnter577109"),
            ("app.cEmAIUpdateBTable", "resumeJumpBTable578134"),
            ("ace.btable.cExportBTableBase", "jumpTable233123"),
            ("app.Em0022_00_BTableOrderBank_Export", ".ctor10"),
            ("app.btable.Em0022_00BTableCommand.cCheckCanDive", "onExecute10"),
        ]:
            self.assertTrue(selected(name, method, "Em0022_00", "all"))
        self.assertFalse(
            selected(
                "app.btable.Em0002_00BTableCommand.cCheckCurrentStage",
                "onExecute10",
                "Em0022_00",
                "all",
            )
        )

    def test_size_limit_checks_before_allocating_large_json(self):
        with patch.object(Path, "stat") as stat, patch.object(
            Path, "read_text"
        ) as read:
            stat.return_value.st_size = MODEL_LIMIT_BYTES + 1
            with self.assertRaisesRegex(ValueError, "25 MiB"):
                read_json(Path("large.json"))
            read.assert_not_called()


class ExpressionTests(unittest.TestCase):
    def setUp(self):
        self.registry = RuleRegistry.load()
        self.unknown = dict(kind="unknown", reason="unreviewed branch")
        self.runtime = dict(kind="runtime", key="angry", source="getter evidence")

    def test_missing_input_preserves_both_possible_branches(self):
        result = evaluate_expression(
            dict(kind="not", item=self.runtime), self.registry, {}
        )
        self.assertIsNone(result.truth)
        self.assertIs(
            evaluate_expression(
                dict(kind="not", item=self.runtime), self.registry, {"angry": True}
            ).truth,
            False,
        )

    def test_three_valued_boolean_algebra_does_not_default_unknown_to_true(self):
        for kind, value, expected in [
            ("all", False, False),
            ("any", True, True),
            ("all", True, None),
            ("any", False, None),
        ]:
            result = evaluate_expression(
                dict(kind=kind, items=[self.unknown, self.runtime]),
                self.registry,
                {"angry": value},
            )
            self.assertIs(result.truth, expected)

    def test_comparison_boundary_and_missing_value(self):
        expression = dict(
            kind="compare",
            operator="le",
            left=dict(kind="runtime", key="distance", source="distance helper"),
            right=dict(kind="constant", value=10),
        )
        self.assertIsNone(evaluate_expression(expression, self.registry, {}).truth)
        self.assertIsNone(
            evaluate_expression(expression, self.registry, {"distance": None}).truth
        )
        self.assertTrue(
            evaluate_expression(expression, self.registry, {"distance": 10}).truth
        )
        self.assertFalse(
            evaluate_expression(expression, self.registry, {"distance": 10.1}).truth
        )


class CoverageGateTests(unittest.TestCase):
    def graph(self):
        evidence = dict(
            type="fixture",
            method="entry",
            address="0x1000",
            end="0x1010",
            nativeSha256="a" * 64,
        )
        discovery = dict(
            profile={},
            discoveredMethods=["fixture:entry"],
            actionRequestSites=["fixture:1"],
        )
        return dict(
            enemyId="EM0001_00_0",
            profile={},
            entryPoints=[
                dict(kind="combat_enter", status="verified", evidence=evidence)
            ],
            tables=[
                dict(
                    evidence=evidence,
                    nodes=[dict(kind="action", requestSite="fixture:1")],
                )
            ],
            recoveryAudit=dict(
                reviewed=True,
                discovery=discovery,
                discoverySha256=discovery_digest(discovery),
                discoveredMethods=discovery["discoveredMethods"],
                actionRequestSites=discovery["actionRequestSites"],
                resourceInventoryChecked=True,
            ),
        )

    def test_discovered_method_or_action_omission_is_not_a_valid_graph(self):
        graph = self.graph()
        validate_release_graph(graph)
        graph["recoveryAudit"]["discoveredMethods"].append("fixture:omitted")
        graph["recoveryAudit"]["discoverySha256"] = discovery_digest(
            graph["recoveryAudit"]["discovery"]
        )
        with self.assertRaisesRegex(ValueError, "发现的方法"):
            validate_release_graph(graph)
        graph = self.graph()
        graph["recoveryAudit"]["actionRequestSites"].append("fixture:2")
        graph["recoveryAudit"]["discoverySha256"] = discovery_digest(
            graph["recoveryAudit"]["discovery"]
        )
        with self.assertRaisesRegex(ValueError, "动作请求"):
            validate_release_graph(graph)

    def test_whole_unknown_table_is_not_accepted_as_recovered_flow(self):
        graph = self.graph()
        graph["tables"][0]["nodes"] = [
            dict(kind="unknown", reason="entire method missing")
        ]
        with self.assertRaisesRegex(ValueError, "整个未知"):
            validate_release_graph(graph)
