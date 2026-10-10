"""Regress interval boundaries, call contexts and first-selection-only input."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest

from sdk.enemy_logic_exporter.shared.models.player_view import (
    build_player_view,
    distance_intervals,
    PlayerCompiler,
)
from src.processed_data.enemy_battle_logic.player_contract import validate_player_view

ROOT = Path(__file__).resolve().parents[2]


class PlayerTreeTests(unittest.TestCase):
    def test_sdk_projection_preserves_native_references_and_candidate_slots(self):
        graph = json.loads(
            (
                ROOT
                / "tests/fixtures/enemy_battle_logic/em0001.upstream.reference.v1.json"
            ).read_text(encoding="utf8")
        )
        graph["playerView"] = build_player_view(graph)
        validate_player_view(graph)
        key, node = next(
            (k, n)
            for k, n in graph["playerView"]["nodes"].items()
            if n["kind"] == "action"
        )
        node["resume"] = key
        with self.assertRaisesRegex(ValueError, "继续位置"):
            validate_player_view(graph)

    def test_unexplained_actions_are_named_by_class_and_parameter_set(self):
        from sdk.enemy_logic_exporter.shared.models.player_view import technical_action_names

        own = "STM/GameDesign/Enemy/Em0002/50/Action/Em0002_50_ActionID.user.3.json"
        base = own.replace("50", "00")

        def action(guid, cls, source=own, variant="0", pointer="/_ActionClassList/3"):
            selection = "branched" if "Branched" in pointer else "default"
            return dict(
                kind="action",
                action=dict(
                    source=source,
                    actionGuid=guid,
                    parameterVariantGuid=variant,
                    actionClass=cls,
                    parameterClass=cls,
                    parameterSelection=selection,
                    parameterBodyPointer=pointer,
                ),
            )

        nodes = [
            action("a", "cDash"),
            action("a", "cDash", variant="v", pointer="/_BranchedParamsList/3/_Params/1"),
            action("b", "cGlide", source=base),
            action("c1234567x", "cTwin"),
            action("d7654321x", "cTwin"),
        ]
        names = technical_action_names(dict(enemyId="EM0002_50_0", tables=[dict(nodes=nodes)]))
        self.assertEqual(
            sorted(names.values()),
            [
                "cDash",
                "cDash · 分支参数 2",
                "cGlide · Em0002_00 动作表",
                "cTwin · c1234567",
                "cTwin · d7654321",
            ],
        )

    def test_distance_bands_keep_equality_separate(self):
        values = [choice["value"] for choice in distance_intervals([8, 11])["options"]]
        self.assertIn(dict(min=8.0, max=8.0, minClosed=True, maxClosed=True), values)
        self.assertIn(dict(min=8.0, max=11.0, minClosed=False, maxClosed=False), values)

    def test_tree_branch_labels_preserve_strict_boundaries_and_phase_names(self):
        compiler = PlayerCompiler(dict(tables=[], rules=dict(rules=[])))
        distance = compiler.presentation(
            dict(
                op="all",
                items=[
                    dict(
                        op="compare",
                        key="ordinary_combat_snapshot",
                        operator="eq",
                        value=True,
                    ),
                    dict(
                        op="compare", key="distance_horizontal", operator="lt", value=8
                    ),
                ],
            )
        )
        self.assertIn("< 8", distance["trueLabel"])
        self.assertIn("≥ 8", distance["falseLabel"])
        self.assertTrue(distance["snapshotGuard"])
        phase = compiler.presentation(
            dict(op="compare", key="battle_phase", operator="eq", value=0)
        )
        self.assertEqual(phase["trueLabel"], "当前为阶段 1")
        self.assertEqual(phase["falseLabel"], "其他阶段")

    def test_posture_interrupts_own_enemy_and_float_variables(self):
        from sdk.enemy_logic_exporter.shared.logic.predicates import RuleRegistry
        from sdk.enemy_logic_exporter.shared.models.uncertainty import evaluate

        rules = RuleRegistry.load().data
        compiler = PlayerCompiler(
            dict(
                enemyId="EM0160_00_0",
                tables=[
                    dict(
                        tableGuid="t",
                        nodes=[
                            dict(
                                id="0",
                                kind="condition",
                                argument=dict(
                                    Enemy={
                                        "Arg": {"_EditArg": "[-283654400] EM0160_50_0"}
                                    }
                                ),
                            )
                        ],
                    )
                ],
                rules=rules,
                standStates=dict(common={}, extra={}, unique={"HILL": 25477}),
            )
        )

        def status(category, **values):
            return compiler.predicate(
                dict(
                    status="verified",
                    kind="self_status",
                    commandType="app.btable.EmCommonCommand.cCheckSelfStatus",
                    values=dict(category=category, **values),
                )
            )

        def holder(layer, value):
            return {"STRUCT__Value_Type": f"[{layer}] X", "STRUCT__Value_Value": value}

        unique = status("[1] STAND_STATE", stand=holder(2, 25477))
        common = status("[1] STAND_STATE", stand=holder(0, 1))
        # One effective posture: the unique layer excludes the common check.
        posture = dict(posture="unique:25477")
        self.assertIs(evaluate(unique, posture, compiler.inputs), True)
        self.assertIs(evaluate(common, posture, compiler.inputs), False)
        self.assertIn("HILL", compiler.inputs["posture"]["options"][0]["label"])
        lead = status("[5] AI_STATE", ai="[5] LEAD")
        scenario = dict(ai_interrupt_next=-1, **{"ai_interrupt_exists:5": False})
        self.assertIs(evaluate(lead, scenario, compiler.inputs), False)
        self.assertIs(evaluate(lead, dict(scenario, ai_interrupt_next=5), {}), True)
        index = dict(kind="runtime", key="enemy_enum_index:-283654400")
        own = compiler.expression(
            dict(
                kind="any",
                items=[
                    dict(
                        kind="compare",
                        operator="eq",
                        left=index,
                        right=dict(kind="constant", value=-1),
                    ),
                    dict(
                        kind="compare",
                        operator="eq",
                        left=dict(kind="runtime", key="self_basic_enemy_id"),
                        right=index,
                    ),
                ],
            )
        )
        self.assertIs(evaluate(own, dict(self_enemy_id="EM0160_00_0"), {}), False)
        self.assertIs(evaluate(own, dict(self_enemy_id="EM0160_50_0"), {}), True)
        equal = compiler.predicate(
            dict(
                status="verified",
                kind="variable_float",
                commandType="ace.btable.cCompareFloatValue",
                values=dict(variable="g", compare="[0] EQUAL", value=1.0),
            )
        )
        self.assertIs(evaluate(equal, {"float:g": 1.0005}, {}), True)
        self.assertIs(evaluate(equal, {"float:g": 1.002}, {}), False)

    @unittest.skipUnless(shutil.which("node"), "浏览器逻辑回归需要 Node")
    def test_browser_filter_and_continuation_semantics(self):
        script = r"""
const assert = require('node:assert/strict');
require(process.argv[1]);
const {compare, evaluate, initial, step} = BattlePlayer;
const interval = (min,max,minClosed=false,maxClosed=false) => ({min,max,minClosed,maxClosed});
assert.equal(compare(interval(8,11), 'lt',11),true);
assert.equal(compare(interval(8,11), 'gt',8),true);
assert.equal(compare(interval(8,11), 'lt',9),null);
assert.equal(compare(interval(8,8,true,true), 'lt',8),false);
assert.equal(compare(interval(8,8,true,true), 'gt',8),false);
assert.equal(compare(interval(90,90,true,true), 'le',90),true);
assert.equal(compare(interval(90,180), 'le',90),false);
assert.equal(compare(undefined,'eq',false),null);
assert.equal(evaluate({op:'all',items:[{op:'unknown',reason:'missing'},{op:'compare',key:'x',operator:'eq',value:1}]},{x:0}),false);
const nodes = {
  root:{kind:'call',sourceRef:'root',target:'action',resume:'distance'},
  action:{kind:'action',sourceRef:'action',title:'A',resume:'end'},
  end:{kind:'return',sourceRef:'end',value:true},
  distance:{kind:'condition',sourceRef:'distance',title:'distance',condition:{op:'compare',key:'d',operator:'lt',value:10},true:'yes',false:'no'},
  yes:{kind:'action',sourceRef:'yes',title:'B',resume:'done'},
  no:{kind:'return',sourceRef:'no'},
  done:{kind:'return',sourceRef:'done'},
  second:{kind:'call',sourceRef:'second',target:'action',resume:'no'},
};
const view = {nodes,scenario:{inputs:{ordinary_combat_snapshot:true}}};
const first = step(view,initial(view,{id:'root'},{d:5}));
assert.equal(first.title,'A');
const next = step(view,first.children[0].state);
assert.equal(next.sourceRef,'distance');
assert.equal(next.truth,null);
assert.equal(next.children.length,2);
assert.equal(next.afterAction,true);
const other = step(view,initial(view,{id:'second'},{d:5}));
assert.equal(step(view,other.children[0].state).sourceRef,'no');
// Unrelated unknown conditions must never acquire a shared Boolean identity.
view.nodes.u1={kind:'condition',sourceRef:'u1',condition:{op:'unknown',reason:'missing'},true:'u2',false:'done'};
view.nodes.u2={kind:'condition',sourceRef:'u2',condition:{op:'unknown',reason:'missing'},true:'yes',false:'no'};
const u1=step(view,initial(view,{id:'u1'},{}));
assert.equal(step(view,u1.children[0].state).children.length,2);
// Candidate slots remain separate even when they target the same call node.
view.nodes.pool={kind:'weighted_random',sourceRef:'pool',candidates:[{id:'slot:0',target:'root',weight:1,filteringUnknown:true},{id:'slot:1',target:'root',weight:1,filteringUnknown:true}],fallback:'no'};
const pool=step(view,initial(view,{id:'pool'},{}));
assert.equal(pool.children.length,3);
assert.notEqual(pool.children[0].slot,pool.children[1].slot);
// Conditions on the same selection snapshot cannot produce impossible paths.
view.inputs={d:{numericRange:{min:0,max:null}}};
view.nodes.low={kind:'condition',sourceRef:'low',condition:{op:'compare',key:'d',operator:'lt',value:8},true:'high',false:'done'};
view.nodes.high={kind:'condition',sourceRef:'high',condition:{op:'compare',key:'d',operator:'gt',value:11},true:'yes',false:'no'};
const low=step(view,initial(view,{id:'low'},{}));
const high=step(view,low.children[0].state);
assert.equal(high.truth,false);
assert.equal(high.children.length,1);
// Folded state changes retain provenance and invalidate the prior snapshot.
view.nodes.write={kind:'mutation',sourceRef:'write',title:'change',next:'distance',invalidateSnapshot:true};
const changed=step(view,initial(view,{id:'write'},{d:5}));
assert.equal(changed.sourceRef,'distance');
assert.equal(changed.truth,null);
assert.equal(changed.via[0].sourceRef,'write');
// An unresolved action identity must retain its verified request continuation.
view.nodes.unbound={kind:'unknown',sourceRef:'unbound',resume:'distance',invalidateSnapshot:true};
const unbound=step(view,initial(view,{id:'unbound'},{d:5}));
assert.equal(unbound.children.length,1);
assert.equal(unbound.children[0].role,'resume');
assert.equal(step(view,unbound.children[0].state).truth,null);
// Timer/variable writes must invalidate internal predicates even when distance
// and other observed fields remain valid in the same selection snapshot.
view.nodes.beforeWrite={kind:'condition',sourceRef:'same-internal-check',condition:{op:'unknown',reason:'timer'},true:'timerWrite',false:'done'};
view.nodes.timerWrite={kind:'mutation',sourceRef:'timerWrite',title:'timer',next:'afterWrite',invalidateSnapshot:false};
view.nodes.afterWrite={kind:'condition',sourceRef:'same-internal-check',condition:{op:'unknown',reason:'timer'},true:'yes',false:'no'};
const checked=step(view,initial(view,{id:'beforeWrite'},{d:5}));
const afterWrite=step(view,checked.children[0].state);
assert.equal(afterWrite.children.length,2);
assert.equal(afterWrite.afterAction,false);
console.log('player engine boundaries and continuations passed');
"""
        result = subprocess.run(
            [
                shutil.which("node"),
                "-e",
                script,
                str(ROOT / "src/processed_data/enemy_battle_logic/player_engine.js"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
