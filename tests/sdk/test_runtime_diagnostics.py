"""Persistent diagnostics observe existing SDK outcomes without changing them."""

import argparse
from contextlib import redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sdk.enemy_logic_exporter.shared.workflow import cli, runtime_log

ROW = dict(
    type="app.Fixture.Export",
    method="table_fixture123",
    address="0x140001000",
    end="0x140001020",
)


def events(path):
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]


def one_event(rows, kind):
    return next(row for row in rows if row["event"] == kind)


class RuntimeDiagnosticsTests(unittest.TestCase):
    def test_success_flushes_one_log_and_resets_active_context(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(io.StringIO()):
            root = Path(directory)
            with runtime_log.diagnostic_run(
                "extract", root, {"input": root / "input"}
            ) as logger:
                self.assertIs(runtime_log.active_run(), logger)
                self.assertEqual(
                    one_event(events(logger.path), "start")["options"]["input"],
                    str((root / "input").resolve()),
                )
                logger.inputs({"input": root / "final", "limit": 123})
                logger.set_method(ROW)
                logger.set_method(ROW)
                logger.event("fixture_result", value=0.125)
            self.assertIsNone(runtime_log.active_run())
            self.assertIsNone(logger.file)
            self.assertEqual(list((root / "logs").iterdir()), [logger.path])
            rows = events(logger.path)
            self.assertEqual(sum(row["event"] == "native_method" for row in rows), 1)
            self.assertEqual(
                one_event(rows, "inputs")["options"],
                {"input": str((root / "final").resolve()), "limit": 123},
            )
            self.assertEqual(one_event(rows, "finish")["status"], "success")
            self.assertEqual(one_event(rows, "fixture_result")["value"], 0.125)

    def test_failure_persists_traceback_and_last_methods_and_reraises_same_error(self):
        failure = ValueError("fixture extraction failed")
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(io.StringIO()):
            with self.assertRaises(ValueError) as caught:
                with runtime_log.diagnostic_run("extract-all", directory, {}) as logger:
                    logger.set_stage("native_evaluation")
                    logger.set_method(
                        ROW,
                        enemy_id="em-variant",
                        table_guid="table-guid",
                        resource="fixture.user",
                    )
                    logger.set_method(
                        dict(ROW, method="helper456", address="0x140002000")
                    )
                    raise failure
            self.assertIs(caught.exception, failure)
            self.assertIsNone(runtime_log.active_run())
            self.assertIsNone(logger.file)
            rows = events(logger.path)
            error = one_event(rows, "error")
            finish = one_event(rows, "finish")
            self.assertEqual(error["exceptionType"], "ValueError")
            self.assertIn("fixture extraction failed", error["traceback"])
            self.assertIn("test_failure_persists_traceback", error["traceback"])
            self.assertEqual(error["stage"], "native_evaluation")
            self.assertEqual(error["lastTableMethod"]["tableGuid"], "table-guid")
            self.assertEqual(error["lastNativeMethod"]["method"], "helper456")
            self.assertEqual(finish["status"], "error")
            self.assertEqual(finish["lastNativeMethod"], error["lastNativeMethod"])
            self.assertEqual(len(list((Path(directory) / "logs").glob("*.jsonl"))), 1)

    def test_manual_catalog_preserves_explicit_owner_and_selected_import_scope(self):
        stem = "table_11111111_2222_3333_4444_555555555555"
        tuple_stem = "table_aaaaaaaa_bbbb_cccc_dddd_eeeeeeeeeeee"
        shared, tuple_owner, missing, outside = (
            "app.Shared.Export",
            "app.Tuple.Export",
            "app.Missing.Export",
            "app.Outside.Export",
        )
        modules = [
            SimpleNamespace(
                ENEMY_ID="em-base",
                LOCAL_HISTORY_TABLES={shared: {stem}},
                FORMULA_HISTORY_TABLES={shared: {stem}},
            ),
            SimpleNamespace(
                ENEMY_ID="em-tuple",
                LOCAL_HISTORY_EXPORT=tuple_owner,
                LOCAL_HISTORY_TABLES=(tuple_stem,),
            ),
            SimpleNamespace(
                ENEMY_ID="em-missing", LOCAL_HISTORY_TABLES={missing: {stem}}
            ),
            SimpleNamespace(
                ENEMY_ID="em-outside", LOCAL_HISTORY_TABLES={outside: {stem}}
            ),
        ]
        descriptions = {
            shared: {"methods": {stem + "123": {}}},
            tuple_owner: {"methods": {tuple_stem + "456": {}}},
            outside: {"methods": {stem + "789": {}}},
        }
        rows = {
            owner: [dict(ROW, type=owner, method=next(iter(record["methods"])))]
            for owner, record in descriptions.items()
        }
        monsters = {
            "em-variant": {
                "tableImportClosure": ["shared.user", "tuple.user", "missing.user"]
            },
            "em-base": {"tableImportClosure": ["outside.user"]},
        }
        resources = {
            "shared.user": {"exportType": shared},
            "tuple.user": {"exportType": tuple_owner},
            "missing.user": {"exportType": missing},
            "outside.user": {"exportType": outside},
        }
        history = SimpleNamespace(
            complete_discovery=True,
            candidates={((16, 51), (20, 0)): {"0x1000"}},
            local_pairs=[],
            formula_enabled=True,
            read_sites={1: {16}, 2: {20}},
            escaped_sites=[],
        )
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(
            io.StringIO()
        ), patch(
            "sdk.enemy_logic_exporter.monster.iter_monsters", return_value=modules
        ):
            with runtime_log.diagnostic_run(
                "extract-all", directory, {"enemy": ["em-variant"]}
            ) as logger:
                logger.manual_catalog(
                    SimpleNamespace(get=descriptions.get), rows, monsters, resources
                )
                shared_row, tuple_row = rows[shared][0], rows[tuple_owner][0]
                scope = dict(
                    enemy_id="em-variant",
                    table_guid="11111111-2222-3333-4444-555555555555",
                    resource="shared.user",
                )
                policy = dict(local=True, formula=True)
                logger.history_requested(shared_row, policy, **scope)
                logger.history_enabled(shared_row, policy, history, **scope)
                logger.history_requested(
                    tuple_row,
                    {"local": True},
                    enemy_id="em-variant",
                    table_guid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    resource="tuple.user",
                )
                failed_scope = dict(
                    enemy_id="em-variant",
                    table_guid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    resource="tuple-unavailable.user",
                )
                logger.history_requested(tuple_row, policy, **failed_scope)
                logger.history_enabled(tuple_row, policy, None, **failed_scope)
            finish = one_event(events(logger.path), "finish")
        catalog = {row["type"]: row for row in finish["manualPolicyDeclarations"]}
        self.assertEqual(catalog[shared]["declaredBy"], ["em-base"])
        self.assertEqual(catalog[shared]["requested"], {"local": True, "formula": True})
        self.assertEqual(catalog[shared]["selectedEnemies"], ["em-variant"])
        self.assertEqual(catalog[shared]["observedEnemies"], ["em-variant"])
        self.assertEqual(catalog[shared]["identityStatus"], "matched")
        self.assertEqual(catalog[shared]["executionStatus"], "observed")
        self.assertEqual(catalog[tuple_owner]["cachedMethods"], [tuple_stem + "456"])
        self.assertEqual(
            catalog[tuple_owner]["executionStatus"], "started_not_completed"
        )
        self.assertEqual(catalog[missing]["identityStatus"], "type_missing")
        self.assertEqual(catalog[missing]["executionStatus"], "declaration_unmatched")
        self.assertEqual(catalog[outside]["identityStatus"], "matched")
        self.assertEqual(
            catalog[outside]["scopeStatus"], "not_in_selected_import_closure"
        )
        self.assertEqual(
            catalog[outside]["executionStatus"], "not_in_selected_import_closure"
        )
        actual = next(row for row in finish["manualPolicies"] if row["type"] == shared)
        self.assertEqual(actual["actual"], {"local": True, "formula": True})
        self.assertEqual(actual["privateReadSites"], 2)
        self.assertIsNone(
            next(row for row in finish["manualPolicies"] if row["type"] == tuple_owner)[
                "actual"
            ]
        )
        unavailable = next(
            row
            for row in finish["manualPolicies"]
            if row["resource"] == "tuple-unavailable.user"
        )
        self.assertEqual(unavailable["requested"], {"local": True, "formula": True})
        self.assertEqual(unavailable["actual"], {"local": False, "formula": False})

    def test_unknowns_keep_success_and_locations_without_changing_graph_values(self):
        graph = dict(
            enemyId="em-variant",
            coverage={"unresolved": 2, "weight": 0.125},
            tables=[
                dict(
                    tableGuid="guid",
                    resource="fixture.user",
                    nativeType=ROW["type"],
                    nativeMethod=ROW["method"],
                    evidence=[dict(ROW), dict(ROW, method="wrapper789")],
                    nodes=[
                        dict(
                            id="condition-a",
                            kind="condition",
                            nativeSite="0x140001001",
                            expression=dict(
                                kind="all",
                                items=[
                                    dict(kind="unknown", reason="first"),
                                    dict(kind="unknown", reason="second"),
                                ],
                            ),
                        ),
                        dict(
                            id="condition-b",
                            kind="condition",
                            expression=dict(
                                kind="not", item=dict(kind="unknown", reason="first")
                            ),
                        ),
                        dict(
                            id="verified",
                            kind="condition",
                            expression=dict(
                                kind="predicate", predicate=dict(status="verified")
                            ),
                        ),
                        dict(
                            id="flow",
                            kind="unknown",
                            reason="unproved call",
                            nativeSite="0x140001005",
                            programCounter=17,
                            nativeBoundary={"target": "0x140009000"},
                            staticArray={"slot": 8},
                        ),
                        dict(id="return", kind="return", value=False),
                    ],
                )
            ],
            selectionBoundaries=[
                dict(
                    id="selection",
                    tableGuid="guid",
                    reason="selection unknown",
                    site="0x140001006",
                    source="selection",
                    dispatcherCount=3,
                )
            ],
            resourceEntryBoundaries=[
                dict(
                    id="resource-entry",
                    tableGuid="missing-guid",
                    status="entry unknown",
                    evidence=[],
                    reference="missing.user",
                    tableMethodCount=0,
                )
            ],
        )
        before = deepcopy(graph)
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(io.StringIO()):
            runtime_log.record_graph(graph)  # No active run is an unchanged no-op.
            with runtime_log.diagnostic_run("extract", directory, {}) as logger:
                runtime_log.record_graph(graph)
            rows = events(logger.path)
        self.assertEqual(graph, before)
        self.assertEqual(one_event(rows, "finish")["status"], "success")
        summary = one_event(rows, "unknown_summary")
        self.assertEqual(
            summary["counts"],
            {
                "condition": 2,
                "flow": 1,
                "selectionBoundaries": 1,
                "resourceEntryBoundaries": 1,
            },
        )
        self.assertEqual(summary["reasonOccurrences"]["condition"], 3)
        flow = next(row for row in summary["entries"] if row["category"] == "flow")
        self.assertEqual(flow["nativeSite"], "0x140001005")
        self.assertEqual(flow["evidence"], graph["tables"][0]["evidence"])
        self.assertEqual(
            flow["boundaryContext"],
            {
                "programCounter": 17,
                "nativeBoundary": {"target": "0x140009000"},
                "staticArray": {"slot": 8},
            },
        )
        selection = next(
            row
            for row in summary["entries"]
            if row["category"] == "selectionBoundaries"
        )
        self.assertEqual(selection["method"], ROW["method"])
        self.assertEqual(selection["methodAddress"], ROW["address"])
        self.assertEqual(
            selection["boundaryContext"],
            {"site": "0x140001006", "source": "selection", "dispatcherCount": 3},
        )
        entry = next(
            row
            for row in summary["entries"]
            if row["category"] == "resourceEntryBoundaries"
        )
        self.assertEqual(entry["evidence"], [])
        self.assertEqual(entry["boundaryContext"]["reference"], "missing.user")

    def test_cli_all_commands_are_logged_without_changing_return_value(self):
        commands = next(
            action.choices
            for action in cli.parser()._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(io.StringIO()):
            for command in commands:
                with self.subTest(command=command):
                    args = SimpleNamespace(command=command, work_dir=Path(directory))
                    parser = SimpleNamespace(parse_args=lambda: args)

                    def run(arguments):
                        self.assertIs(arguments, args)
                        self.assertIsNotNone(runtime_log.active_run())
                        return 731

                    with patch.object(cli, "parser", return_value=parser), patch.object(
                        cli, "_run", side_effect=run
                    ):
                        self.assertEqual(cli.main(), 731)
            logs = list((Path(directory) / "logs").glob("*.jsonl"))
            self.assertEqual(len(logs), len(commands))
            self.assertEqual(
                {one_event(events(path), "start")["command"] for path in logs},
                set(commands),
            )
            self.assertTrue(
                all(
                    one_event(events(path), "finish")["status"] == "success"
                    for path in logs
                )
            )


if __name__ == "__main__":
    unittest.main()
