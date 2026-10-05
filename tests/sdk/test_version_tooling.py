"""Version-update tooling: relocation-insensitive digests, symbols, roster."""

from importlib.util import find_spec
import unittest

from sdk.enemy_logic_exporter.shared.models.uncertainty import evaluate
from sdk.enemy_logic_exporter.shared.native.symbols import (
    Method,
    evidence_rows,
    find_method,
    method_stem,
)


class FakePE:
    """A function laid out at ``base``; ``end`` is the end of that body."""

    def __init__(self, base, code):
        self.base, self.code = base, bytes.fromhex(code)

    def read(self, address, size):
        offset = address - self.base
        return self.code[offset : offset + size]

    def end(self, address):
        return self.base + len(self.code)


class FakeMetadata:
    def __init__(self, methods):
        self.methods = methods

    def get(self, name):
        return dict(methods=self.methods) if name == "app.T" else None


@unittest.skipUnless(find_spec("capstone"), "离线原生测试需要 SDK 的 Capstone 依赖")
class NormalizedDigestTests(unittest.TestCase):
    def test_relocated_calls_and_rip_data_keep_the_digest(self):
        from sdk.enemy_logic_exporter.shared.native.symbols import normalized_digest

        # mov eax,[rip+X]; call T; ret  at two builds with different X and T.
        first = FakePE(0x1000, "8b0500100000e8f00f0000c3")
        second = FakePE(0x5000, "8b0534120000e8aa220000c3")
        self.assertEqual(
            normalized_digest(first, 0x1000), normalized_digest(second, 0x5000)
        )
        # A changed structure offset is a real code change.
        third = FakePE(0x1000, "8b4008e8f10f0000c3")
        self.assertNotEqual(
            normalized_digest(first, 0x1000), normalized_digest(third, 0x1000)
        )

    def test_named_callees_are_part_of_the_digest(self):
        from sdk.enemy_logic_exporter.shared.native.symbols import normalized_digest

        # Same bytes shape, call targets 0x1ffb and 0x72b5 in the two builds.
        first = FakePE(0x1000, "8b0500100000e8f00f0000c3")
        second = FakePE(0x5000, "8b0534120000e8aa220000c3")
        same = {0x1ffb: "M:app.A.f()", 0x72b5: "M:app.A.f()"}.get
        moved = {0x1ffb: "M:app.A.f()", 0x72b5: "M:app.B.g()"}.get
        self.assertEqual(
            normalized_digest(first, 0x1000, names=same),
            normalized_digest(second, 0x5000, names=same),
        )
        self.assertNotEqual(
            normalized_digest(first, 0x1000, names=moved),
            normalized_digest(second, 0x5000, names=moved),
        )

    def test_migration_compares_the_whole_function_not_the_row_prefix(self):
        from sdk.enemy_logic_exporter.shared.native.symbols import normalized_digest
        from sdk.enemy_logic_exporter.shared.workflow.version_update import _same_function

        names = lambda address: "M:app.A.f()"
        original = FakePE(0x1000, "8b0500100000e8f00f0000c3")
        # The evidence row covers only the first instruction.
        old = dict(
            functionLength=12,
            rowLength=6,
            normalizedSha256=normalized_digest(original, 0x1000, 0x100C, names),
        )
        self.assertTrue(_same_function(original, 0x1000, old, names))
        # The tail after the row changed: mov eax,1 instead of the call.
        changed = FakePE(0x1000, "8b0500100000b801000000c3")
        self.assertFalse(_same_function(changed, 0x1000, old, names))
        # The function grew: an extra nop after ret.
        grown = FakePE(0x1000, "8b0500100000e8f00f0000c390")
        self.assertFalse(_same_function(grown, 0x1000, old, names))


class SymbolTests(unittest.TestCase):
    def test_methods_resolve_by_name_without_suffix_and_by_parameters(self):
        metadata = FakeMetadata(
            {
                "setCurrentPosition233766": dict(
                    function="1000", params=[dict(type="System.Int32")]
                ),
                "setCurrentPosition233780": dict(
                    function="2000", params=[dict(type="ace.btable.BTableDef.POSITION")]
                ),
            }
        )
        self.assertEqual(method_stem("get_Item494226"), "get_Item")
        spec = Method("app.T", "setCurrentPosition", ("ace.btable.BTableDef.POSITION",))
        self.assertEqual(find_method(metadata, spec), ("setCurrentPosition233780", 0x2000))
        with self.assertRaisesRegex(ValueError, "无法唯一定位"):
            find_method(metadata, Method("app.T", "setCurrentPosition"))

    def test_evidence_rows_are_found_anywhere_in_a_document(self):
        row = dict(type="a", method="m1", address="0x1", end="0x2", nativeSha256="0")
        document = dict(methods={"m1": row}, rules=[dict(evidence=dict(row))])
        self.assertEqual(len(evidence_rows(document)), 2)


class RosterTests(unittest.TestCase):
    def test_combat_owner_and_exclusions_come_from_the_resources(self):
        from sdk.enemy_logic_exporter.shared.models.roster import build_roster

        def enemy(enemy_id):
            return {"app.EnemyDataItem": {"_enemyId": f"[1] {enemy_id}"}}

        def btable(owner):
            path = f"GameDesign/Enemy/x/{owner}_Btable_Combat.user"
            return {"_Table_COMBAT": {"ace.btable.user_data.BTable": {"path": path}}}

        files = {
            "STM/GameDesign/Common/Enemy/EnemyData.user.3.json": {
                "_Values": [
                    enemy("EM0160_00_0"),
                    enemy("EM0160_50_0"),
                    enemy("EM0165_00_0"),
                    enemy("EM1001_00_0"),
                ]
            },
            "STM/GameDesign/Enemy/Em0160/00/BTable/Em0160_00_BTableList.user.3.json": btable("Em0160_00"),
            "STM/GameDesign/Enemy/Em0160/50/BTable/Em0160_50_BTableList.user.3.json": btable("Em0160_00"),
        }

        class Resources:
            def read(self, path):
                return files[path]

        roster = build_roster(Resources())
        self.assertEqual(
            [(e["enemyId"], e["nativeOwner"]) for e in roster["enemies"]],
            [("EM0160_00_0", "Em0160_00"), ("EM0160_50_0", "Em0160_00")],
        )


class UncertaintyTests(unittest.TestCase):
    def test_player_inputs_are_not_uncertainty_but_unknown_leaves_are(self):
        scenario, inputs = dict(mask=False), dict(distance={})
        guard = dict(op="not", item=dict(op="compare", key="mask", operator="eq", value=True))
        distance = dict(op="compare", key="distance", operator="lt", value=8)
        unknown = dict(op="unknown", reason="x")
        self.assertTrue(evaluate(guard, scenario, inputs))
        self.assertEqual(evaluate(dict(op="all", items=[guard, distance]), scenario, inputs), "input")
        self.assertIsNone(evaluate(dict(op="all", items=[distance, unknown]), scenario, inputs))
        self.assertFalse(evaluate(dict(op="all", items=[dict(guard, op="not", item=guard), unknown]), scenario, inputs))


class LeafRuleTests(unittest.TestCase):
    def leaf(self, **extra):
        base = dict(
            contextType="app.cEm0162_00Extend",
            contextField="_QuestPhase",
            contextFieldType="System.Int32",
            contextOffset="0x12c",
            operator=">=",
            argumentField="_ChoicePhase",
            constant=None,
        )
        return {**base, **extra}

    def test_argument_leaf_compares_the_extend_field_with_the_resource_value(self):
        from sdk.enemy_logic_exporter.shared.logic.commands import leaf_expression
        from sdk.enemy_logic_exporter.shared.logic.expressions import evaluate_expression
        from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry

        expression = leaf_expression(self.leaf(), {"_ChoicePhase": "[2] PHASE_2"})
        context = dict(enemy_command_work_valid=True, self_extend_valid=True)
        key = "extend:app.cEm0162_00Extend._QuestPhase"
        registry = RuleRegistry.load()
        self.assertTrue(evaluate_expression(expression, registry, dict(context, **{key: 3})).truth)
        self.assertFalse(evaluate_expression(expression, registry, dict(context, **{key: 1})).truth)
        self.assertIsNone(leaf_expression(self.leaf(), {}))

    def test_boolean_leaf_without_argument_reads_the_field_itself(self):
        from sdk.enemy_logic_exporter.shared.logic.commands import leaf_expression

        leaf = self.leaf(
            contextFieldType="System.Boolean", operator="==", argumentField=None
        )
        leaf["constant"] = 0
        test = leaf_expression(leaf)["items"][1]
        self.assertEqual(test["kind"], "not")
        self.assertEqual(test["item"]["key"], "extend:app.cEm0162_00Extend._QuestPhase")
