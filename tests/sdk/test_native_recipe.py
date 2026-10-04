"""Check root dispatch aliases and unknown random data with synthetic x64."""

import hashlib
from importlib.util import find_spec
import unittest
from unittest.mock import Mock, patch


@unittest.skipUnless(find_spec("capstone"), "原生配方回归需要 Capstone")
class NativeRecipeTests(unittest.TestCase):
    def context(self, native):
        from sdk.enemy_logic_exporter.shared.models.native_recipe import (
            NativeRecipeContext,
        )

        context = NativeRecipeContext.__new__(NativeRecipeContext)
        context.pe = None
        context.native = lambda row: native
        return context

    def test_dispatch_root_executes_position_zero_and_preserves_alias_context(self):
        # cmp [r8+4],0; jne return; jmp 0x2000; ret
        native = bytes.fromhex("41837804007505e9f40f0000c3")
        row = dict(
            type="fixture",
            method="updateTableInpl",
            address="0x1000",
            end=hex(0x1000 + len(native)),
            nativeSha256=hashlib.sha256(native).hexdigest(),
        )
        targets = [
            dict(
                row=dict(type="fixture", address="0x2000"),
                tableGuid="root",
                tableIndex=0,
            ),
            dict(
                row=dict(type="fixture", address="0x2000"),
                tableGuid="alias",
                tableIndex=1,
            ),
        ]
        self.assertEqual(
            self.context(native).dispatch_root(row, targets)["tableGuid"], "root"
        )
        targets[1]["tableIndex"] = 0
        with self.assertRaisesRegex(ValueError, "别名"):
            self.context(native).dispatch_root(row, targets)

    def test_unreviewed_random_value_cannot_select_zero_branch(self):
        from sdk.enemy_logic_exporter.shared.logic.machine import Machine

        native = bytes.fromhex("e80000000085c07406b801000000c331c0c3")
        row = dict(
            type="fixture",
            address="0x1000",
            nativeSha256=hashlib.sha256(native).hexdigest(),
        )
        machine = Machine(row, native, None, {}, [], {}, {})
        event = dict(
            kind="call",
            site="0x1000",
            target=("random_generator",),
            arguments=[None],
            positionArguments={},
        )
        with patch.object(machine, "event", return_value=event):
            result = machine.build()
        kinds = [n["kind"] for n in result["nodes"]]
        self.assertIn("unknown", kinds)
        self.assertNotIn("return", kinds)

    def test_empty_dispatcher_requires_actual_immediate_void_return(self):
        row = dict(
            type="ActualOwner",
            method="updateTableInpl123",
            address="0x1000",
            end="0x1004",
            nativeSha256=hashlib.sha256(b"\xc3\xcc\xcc\xcc").hexdigest(),
        )
        context = self.context(b"\xc3\xcc\xcc\xcc")
        method = dict(function="0x1000", returns=dict(type="System.Void"))
        context.metadata = Mock()
        context.metadata.get.return_value = dict(methods={row["method"]: method})
        context.metadata.type_hash.return_value = "a" * 64
        result = context.non_dispatch_entry(row)
        self.assertEqual(result["status"], "native_no_dispatch_verified")
        self.assertEqual(result["entryInstruction"]["bytes"], "c3")
        self.assertNotIn("tableGuid", result)
        method["function"] = "0x2000"
        self.assertIsNone(context.non_dispatch_entry(row))
        method["function"] = "0x1000"
        method["returns"]["type"] = "System.Boolean"
        self.assertIsNone(context.non_dispatch_entry(row))
        method["returns"]["type"] = "System.Void"
        context.native = lambda row: b"\x31\xc0\xc3"
        self.assertIsNone(context.non_dispatch_entry(row))


class SchedulerPresentationTests(unittest.TestCase):
    def test_independent_slots_share_one_real_call_without_merging_filters(self):
        from sdk.enemy_logic_exporter.shared.models.builder import trace_until_request
        from sdk.enemy_logic_exporter.shared.models.native_recipe import (
            local_identities,
        )
        from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry
        from src.processed_data.enemy_battle_logic.diagram import combined_diagram

        candidates = [
            dict(
                id=f"slot:{index}",
                nodeId="call",
                nativeCandidateIndex=index,
                nativeKey=key,
                targetTable="child",
                weight=weight,
                skipTableReferences=skips,
            )
            for index, key, weight, skips in (
                (0, 4, 20, ["skip-first"]),
                (1, 9, 80, []),
            )
        ]
        root = dict(
            tableGuid="root",
            entry="choose",
            name="root",
            evidence={},
            nodes=[
                dict(
                    id="choose",
                    kind="weighted_random",
                    filteringMode="per_candidate",
                    candidates=candidates,
                    fallback="end",
                ),
                dict(id="call", kind="call", targetTable="child", resume="end"),
                dict(id="end", kind="return", value=False),
            ],
        )
        graph = dict(
            profile={},
            entry="root",
            rules=RuleRegistry.load().data,
            tables=[
                root,
                dict(
                    tableGuid="child",
                    entry="end",
                    name="child",
                    evidence={},
                    nodes=[dict(id="end", kind="return", value=True)],
                ),
            ],
        )
        result = trace_until_request(
            graph,
            dict(
                candidate_skip_matches_current_action={"root:choose": {"slot:0": True}},
                random_draws={"root:choose": 0},
            ),
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["path"][0]["selection"], "slot:1")
        self.assertEqual(result["path"][1]["node"], "call")
        edges = [
            edge
            for edge in combined_diagram(graph)["layout"]["edges"]
            if edge["role"] == "random"
        ]
        self.assertEqual([edge["targets"] for edge in edges], [["root/call"]] * 2)
        self.assertEqual([edge["candidateId"] for edge in edges], ["slot:0", "slot:1"])
        self.assertEqual([edge["text"] for edge in edges], ["权重 20", "权重 80"])
        converted = local_identities(root)
        self.assertEqual([c["id"] for c in candidates], ["slot:0", "slot:1"])
        self.assertEqual([c["nodeId"] for c in candidates], ["1", "1"])
        self.assertEqual(len(converted["nodes"]), 3)

    def test_request_site_coverage_cannot_hide_a_missing_alias_context(self):
        from sdk.enemy_logic_exporter.shared.models.native_recipe import (
            request_coverage,
        )

        binding = dict(
            resource="first",
            type="FirstType",
            method="table",
            address="0x1000",
            commandIndex=4,
            argumentIndex=1,
        )
        alias = dict(binding, resource="second", type="SecondType", argumentIndex=7)
        table = dict(
            resource="first",
            nativeType="FirstType",
            nativeMethod="table",
            nodes=[
                dict(
                    kind="action", requestSite="0x1000", commandIndex=4, argumentIndex=1
                )
            ],
        )
        result = request_coverage([table], [binding, alias], {"first", "second"})
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["expectedContexts"], 2)
        self.assertEqual(result["recoveredContexts"], 1)
        self.assertEqual(result["missingContexts"], [alias])

    def test_missing_serialized_action_parameter_keeps_request_and_resume_boundary(
        self,
    ):
        from sdk.enemy_logic_exporter.shared.models.builder import bind_action_node
        from sdk.enemy_logic_exporter.shared.resources.reader import ActionBindingError

        resources, names = Mock(), Mock()
        resources.action.side_effect = ActionBindingError(
            "missing parameter GUID",
            reason="missing_action_parameter_guid",
            context=dict(
                actionGuid="actual-guid",
                tableGuid="resource-guid",
                actionIdRecord=dict(_Class="actual-requested-class"),
            ),
        )
        node = dict(kind="action", id="request", requestSite="0x1234", resume="next")
        boundary = bind_action_node(node, {}, {}, resources, names)
        self.assertEqual(node["kind"], "unknown")
        self.assertEqual(node["resume"], "next")
        self.assertEqual(node["requestSite"], "0x1234")
        self.assertEqual(boundary["actionIdRecord"]["_Class"], "actual-requested-class")
        names.bind.assert_not_called()
        resources.action.side_effect = ValueError("duplicate parameter records")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            bind_action_node({}, {}, {}, resources, names)

    def test_equal_table_guids_keep_resource_context_and_leave_cached_records_intact(
        self,
    ):
        from sdk.enemy_logic_exporter.shared.models.native_recipe import (
            resource_table_identities,
        )

        cached = [
            dict(tableGuid="equal-guid", resource="Damage", row=dict(type="Damage")),
            dict(tableGuid="equal-guid", resource="Life", row=dict(type="Life")),
            dict(tableGuid="unique-guid", resource="Life", row=dict(type="Life")),
        ]
        result = resource_table_identities(cached)
        self.assertNotEqual(result[0]["tableGuid"], result[1]["tableGuid"])
        self.assertEqual(result[0]["nativeTableGuid"], "equal-guid")
        self.assertEqual(result[1]["nativeTableGuid"], "equal-guid")
        self.assertEqual(result[2]["tableGuid"], "unique-guid")
        self.assertEqual(cached[0]["tableGuid"], "equal-guid")
        self.assertEqual(resource_table_identities(cached), result)

    def test_candidate_filters_require_their_own_source_binding_on_both_sides(self):
        from sdk.enemy_logic_exporter.shared.models.validation import (
            validate_candidate_filters as sdk_validate,
        )
        from src.processed_data.enemy_battle_logic.validation import (
            validate_candidate_filters as viewer_validate,
        )

        argument_type = "app.btable.EmCommonCommand.cSetSkipActionTblArg"
        candidate = dict(
            skipArgumentIndex=3,
            expectedSkipArgumentType=argument_type,
            skipArgumentType=argument_type,
            skipArgument={"_SkipActionTblList": ["skip-a"]},
            skipTableReferences=["skip-a"],
            skipSourceResource="own-resource",
            skipSourceBodyPointer=f"/_CommandArgArray/3/{argument_type}",
        )
        node = dict(filteringMode="per_candidate", candidates=[candidate])
        for validate in (sdk_validate, viewer_validate):
            validate(node, {"own-resource": "a" * 64})
            with self.assertRaisesRegex(ValueError, "来源"):
                validate(node, {"foreign-resource": "a" * 64})
            with self.assertRaisesRegex(ValueError, "共同"):
                validate(dict(node, argumentIndex=3), {"own-resource": "a" * 64})
            altered = dict(candidate, skipTableReferences=["unbound-skip"])
            with self.assertRaisesRegex(ValueError, "不一致"):
                validate(dict(node, candidates=[altered]), {"own-resource": "a" * 64})

    def test_each_candidate_filters_only_its_own_action_skip_list(self):
        from sdk.enemy_logic_exporter.shared.models.builder import (
            trace_until_request,
            bind_skip_argument,
        )
        from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry

        node = dict(
            id="choose",
            kind="weighted_random",
            filteringMode="per_candidate",
            fallback="end",
            candidates=[
                dict(
                    id="a",
                    targetTable="child",
                    weight=50,
                    skipTableReferences=["skip-a"],
                ),
                dict(id="b", targetTable="child", weight=50, skipTableReferences=[]),
            ],
        )
        graph = dict(
            entry="root",
            rules=RuleRegistry.load().data,
            tables=[
                dict(
                    tableGuid="root",
                    entry="choose",
                    nodes=[
                        node,
                        dict(id="a", kind="call", targetTable="child", resume="end"),
                        dict(id="b", kind="call", targetTable="child", resume="end"),
                        dict(id="end", kind="return", value=False),
                    ],
                ),
                dict(
                    tableGuid="child",
                    entry="end",
                    nodes=[dict(id="end", kind="return", value=True)],
                ),
            ],
        )
        self.assertEqual(trace_until_request(graph, {})["status"], "unknown")
        result = trace_until_request(
            graph,
            dict(
                candidate_skip_matches_current_action={"root:choose": {"a": True}},
                random_draws={"root:choose": 0},
            ),
        )
        self.assertEqual(result["path"][0]["selection"], "b")
        self.assertEqual(result["status"], "completed")
        argument_type = "app.btable.EmCommonCommand.cSetSkipActionTblArg"
        body = dict(
            _CommandArgArray=[{argument_type: dict(_SkipActionTblList=["skip-a"])}]
        )
        self.assertEqual(
            bind_skip_argument(body, 0, argument_type, "own-resource")[
                "skipTableReferences"
            ],
            ["skip-a"],
        )
        with self.assertRaisesRegex(ValueError, "类型"):
            bind_skip_argument(body, 0, "foreign-argument", "own-resource")

    def test_async_request_does_not_acquire_call_resume_semantics(self):
        from src.processed_data.enemy_battle_logic.diagram import combined_diagram
        from src.processed_data.enemy_battle_logic.viewer_labels import label

        end = dict(id="end", kind="return", value=None, returnType="void")
        request = dict(
            id="queue",
            kind="mutation",
            effect="request_btable",
            dispatchTarget="target",
            next="end",
        )
        graph = dict(
            profile={},
            entry="event",
            tables=[
                dict(
                    tableGuid="event",
                    name="callback",
                    entry="queue",
                    evidence={},
                    nodes=[request, end],
                ),
                dict(
                    tableGuid="target",
                    name="Combat",
                    entry="end",
                    evidence={},
                    nodes=[end],
                ),
            ],
        )
        edges = combined_diagram(graph)["layout"]["edges"]
        self.assertEqual([e["role"] for e in edges], ["next", "dispatch"])
        self.assertTrue(edges[1]["asynchronous"])
        self.assertFalse(any(e.get("continuation") for e in edges))
        self.assertEqual(label(end)[0], "回调结束")
