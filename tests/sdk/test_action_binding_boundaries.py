"""Existing missing parameter requests remain unknown across model rebinding."""

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from sdk.enemy_logic_exporter.shared.models.builder import build_chain
from sdk.enemy_logic_exporter.shared.resources.reader import structure_signature


class ActionBindingBoundaryTests(unittest.TestCase):
    def fixture(self, reason="missing_action_parameter_guid"):
        command = "app.btable.EmCommonCommand.cRequestAction"
        argument_type = command + "Arg"
        resource = "fixture.user.3.json"
        factories = [dict(_OrderType=command, _ArgumentType=argument_type)]
        body = dict(
            _ExportBTableType="app.Em0001_00_BTable_Fixture_Export",
            _ThisGuid="fixture-table",
            _UseExportArgData=False,
            _CommandArgArray=[{argument_type: {"_EditActionGuid": "missing-guid"}}],
            _ImportBTableList=[],
        )
        resources = SimpleNamespace(
            accessed=set(),
            factories=lambda _: factories,
            action=Mock(side_effect=AssertionError("must not retry unknown request")),
        )

        def read(path):
            if path != resource:
                raise FileNotFoundError(path)
            resources.accessed.add(path)
            return body

        resources.read = read
        graph = dict(
            schemaVersion=1,
            enemyId="EM0001_00_0",
            entry="fixture-table",
            resources={
                resource: dict(structureSignature=structure_signature(body, factories))
            },
            tables=[
                dict(
                    tableGuid="fixture-table",
                    entry="request",
                    resource=resource,
                    nodes=[
                        dict(
                            id="request",
                            kind="unknown",
                            commandIndex=0,
                            argumentIndex=0,
                            expectedCommandType=command,
                            expectedArgumentType=argument_type,
                            requestSite="0x1000",
                            reason="parameter remains unknown",
                            parameterBindingBoundary=dict(
                                reason=reason, actionGuid="missing-guid"
                            ),
                        )
                    ],
                )
            ],
        )
        return graph, resources

    def rebind(self, graph, resources):
        with patch(
            "sdk.enemy_logic_exporter.shared.models.builder.RuleRegistry.load",
            return_value=SimpleNamespace(data={}),
        ), patch(
            "sdk.enemy_logic_exporter.shared.models.builder.ActionNames",
            return_value=SimpleNamespace(catalog=lambda: {}),
        ), patch(
            "sdk.enemy_logic_exporter.shared.models.builder.referenced_variables",
            return_value={},
        ), patch(
            "sdk.enemy_logic_exporter.shared.models.builder.build_player_view",
            return_value={},
        ):
            return build_chain("unused", model=graph, resources=resources)

    def test_missing_parameter_boundary_is_preserved_and_rebinding_is_idempotent(self):
        graph, resources = self.fixture()
        boundary = deepcopy(graph["tables"][0]["nodes"][0]["parameterBindingBoundary"])
        first = self.rebind(graph, resources)
        second = self.rebind(first, resources)
        self.assertEqual(
            first["actionBindingCoverage"], second["actionBindingCoverage"]
        )
        self.assertEqual(second["actionBindingCoverage"]["bound"], 0)
        self.assertEqual(second["actionBindingCoverage"]["unresolved"], 1)
        self.assertEqual(len(second["actionBindingCoverage"]["boundaries"]), 1)
        node = second["tables"][0]["nodes"][0]
        self.assertEqual(node["kind"], "unknown")
        self.assertEqual(node["parameterBindingBoundary"], boundary)
        self.assertNotIn("action", node)
        resources.action.assert_not_called()

    def test_other_unknown_reasons_are_not_reclassified_as_missing_parameters(self):
        graph, resources = self.fixture(reason="unreviewed_native_helper")
        result = self.rebind(graph, resources)
        self.assertEqual(result["actionBindingCoverage"]["unresolved"], 0)
        self.assertEqual(result["tables"][0]["nodes"][0]["kind"], "unknown")
        resources.action.assert_not_called()
