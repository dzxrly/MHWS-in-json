"""Regress interval boundaries, call contexts and first-selection-only input."""

from pathlib import Path
import shutil
import subprocess
import unittest

from sdk.enemy_logic_exporter.shared.models.player_view import (
    distance_intervals,
    PlayerCompiler,
)

ROOT = Path(__file__).resolve().parents[2]


class PlayerTreeTests(unittest.TestCase):
    def test_target_native_boundary_preserves_normal_return_contract(self):
        compiler = PlayerCompiler(dict(tables=[], rules=dict(rules=[])))
        boundary = compiler.node(
            "t",
            dict(
                id="call",
                kind="unknown",
                boundaryKind="native_call_effects",
                reason="持有调度尚未闭合",
                continuationKind="normal_return",
                next="tail",
            ),
        )
        self.assertEqual(boundary["continuationKind"], "normal_return")
        self.assertEqual(boundary["note"], "持有调度尚未闭合")
        self.assertEqual(boundary["next"], "t/tail")
        self.assertNotIn("resume", boundary)

    def test_partial_request_boundary_uses_normal_return_and_delays_tail_writes(self):
        compiler = PlayerCompiler(dict(tables=[], rules=dict(rules=[])))
        boundary = compiler.node(
            "t",
            dict(
                id="boundary",
                kind="unknown",
                boundaryKind="partial_request_effects",
                continuationKind="normal_return",
                reason="转换尚未闭合；正常返回后继续",
                next="tail",
                requestSource=dict(actionGuid="source"),
                convertedActionId=dict(status="unknown"),
                commandEffectsComplete=False,
            ),
        )
        self.assertEqual(boundary["continuationKind"], "normal_return")
        self.assertNotIn("resume", boundary)
        script = r"""
const assert=require('node:assert/strict'); const {pathToFileURL}=require('node:url');
import(pathToFileURL(process.argv[1]).href).then(({initial,step})=>{
const flag='context:_FlagArray[NO_REQUEST_ACTION]';
const view={scenario:{inputs:{}},nodes:{
 boundary:{kind:'unknown',sourceRef:'boundary',next:'tail',continuationKind:'normal_return',invalidateSnapshot:true},
 tail:{kind:'mutation',sourceRef:'tail',stateUpdates:{[flag]:false},next:'check',invalidateSnapshot:false},
 check:{kind:'condition',sourceRef:'check',condition:{op:'compare',key:flag,operator:'eq',value:false},true:'end',false:'end'},
 end:{kind:'return',sourceRef:'end'}
}};
const boundary=step(view,initial(view,{id:'boundary'},{[flag]:true,distance:5}));
assert.equal(boundary.kind,'unknown');assert.equal(boundary.children[0].label,'正常返回后继续');
const returned=step(view,boundary.children[0].state);
assert.equal(returned.sourceRef,'check');assert.equal(returned.truth,true);
assert.equal(returned.children[0].state.inputs[flag],false);
assert.equal(returned.children[0].state.inputs.distance,undefined);
}).catch(e=>{console.error(e);process.exit(1)});
"""
        result = subprocess.run(
            [
                shutil.which("node"),
                "-e",
                script,
                str(ROOT / "web/src/sites/enemy_battle_logic/player_engine.js"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_full_domain_history_formula_projection_and_native_integer_edges(self):
        high, low, draw = (
            "table_history:fixture:max",
            "table_history:fixture:min",
            "random_uint32_mod_100:site",
        )
        compiler = PlayerCompiler(dict(tables=[], rules=dict(rules=[])))
        compiler.input_definitions = {
            key: dict(label=key, number=True, min=-2147483648, max=2147483647)
            for key in (high, low)
        }
        raw = dict(
            kind="table_history_interval",
            drawKey=draw,
            maxKey=high,
            minKey=low,
            modulus=100,
            threshold=50,
        )
        projected = compiler.expression(raw)
        self.assertEqual(
            projected,
            {
                "op": "table_history_interval",
                **{k: v for k, v in raw.items() if k != "kind"},
            },
        )
        self.assertEqual(set(compiler.inputs), {high, low})
        script = r"""
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
import(pathToFileURL(process.argv[1]).href).then(({evaluate,initial,step})=>{
const high='table_history:fixture:max',low='table_history:fixture:min',draw='random_uint32_mod_100:site';
const expression={op:'table_history_interval',drawKey:draw,maxKey:high,minKey:low,modulus:100,threshold:50};
for(let r=0;r<100;r++) {
 assert.equal(evaluate(expression,{[draw]:r,[high]:-1,[low]:-1}),r<=50);
 assert.equal(evaluate(expression,{[draw]:r,[high]:51,[low]:0}),r===0);
 assert.equal(evaluate(expression,{[draw]:r,[high]:101,[low]:50}),true);
}
assert.equal(evaluate(expression,{[draw]:4294967295,[high]:-2147483648,[low]:2147483647}),false);
assert.equal(evaluate(expression,{[draw]:40,[high]:35,[low]:-200}),true); // candidate-external history
assert.equal(evaluate(expression,{[draw]:40,[high]:35}),null);
assert.equal(evaluate(expression,{[draw]:40,[high]:true,[low]:0}),null);
const view={scenario:{inputs:{}},persistentState:[high,low],nodes:{
 first:{kind:'condition',sourceRef:'first',condition:expression,true:'write',false:'end'},
 write:{kind:'mutation',sourceRef:'write',stateUpdates:{[high]:51,[low]:0},invalidateSnapshot:false,next:'second'},
 second:{kind:'condition',sourceRef:'second',condition:expression,true:'end',false:'end'},
 end:{kind:'return',sourceRef:'end'}
}};
const before=step(view,initial(view,{id:'first'},{[draw]:1,[high]:-1,[low]:-1}));
assert.equal(before.truth,true);
const after=step(view,before.children[0].state);
assert.equal(after.sourceRef,'second');assert.equal(after.truth,false);assert.equal(after.children.length,1);
// Interleaved pairs survive both another pair's write and action resumption.
const aMax='table_history:pairA:max',aMin='table_history:pairA:min',bMax='table_history:pairB:max',bMin='table_history:pairB:min';
const aDraw='drawA',bDraw='drawB';
const pair=(maxKey,minKey,drawKey)=>({op:'table_history_interval',maxKey,minKey,drawKey,modulus:100,threshold:50});
const interleaved={scenario:{inputs:{}},persistentState:[aMax,aMin,bMax,bMin],nodes:{
 A:{kind:'condition',sourceRef:'A',condition:pair(aMax,aMin,aDraw),true:'writeA',false:'done'},
 writeA:{kind:'mutation',sourceRef:'writeA',stateUpdates:{[aMax]:51,[aMin]:0},invalidateSnapshot:false,next:'actionA'},
 actionA:{kind:'action',sourceRef:'actionA',resume:'B'},
 B:{kind:'condition',sourceRef:'B',condition:pair(bMax,bMin,bDraw),true:'done',false:'writeB'},
 writeB:{kind:'mutation',sourceRef:'writeB',stateUpdates:{[bMax]:101,[bMin]:50},invalidateSnapshot:false,next:'actionB'},
 actionB:{kind:'action',sourceRef:'actionB',resume:'againA'},
 againA:{kind:'condition',sourceRef:'againA',condition:pair(aMax,aMin,aDraw),true:'done',false:'done'},
 done:{kind:'return',sourceRef:'done'}
}};
const firstA=step(interleaved,initial(interleaved,{id:'A'},{[aMax]:-1,[aMin]:-1,[bMax]:-1,[bMin]:-1,[aDraw]:1}));
assert.equal(firstA.truth,true);
const actionA=step(interleaved,firstA.children[0].state);
assert.equal(actionA.sourceRef,'actionA');
const stateB=actionA.children[0].state;stateB.inputs[bDraw]=99;
const firstB=step(interleaved,stateB);assert.equal(firstB.truth,false);
const actionB=step(interleaved,firstB.children[0].state);
assert.equal(actionB.sourceRef,'actionB');
const stateAgain=actionB.children[0].state;stateAgain.inputs[aDraw]=1;
const again=step(interleaved,stateAgain);
assert.equal(again.truth,false); // A still has (51,0); B's (101,50) cannot replace it.
assert.equal(again.children[0].state.inputs[aMax],51);
assert.equal(again.children[0].state.inputs[bMax],101);
}).catch(e=>{console.error(e);process.exit(1)});
"""
        result = subprocess.run(
            [
                shutil.which("node"),
                "-e",
                script,
                str(ROOT / "web/src/sites/enemy_battle_logic/player_engine.js"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_hidden_target_type_guards_keep_the_reviewed_summary(self):
        compiler = PlayerCompiler(dict(tables=[], rules=dict(rules=[])))
        result = compiler.node(
            "table",
            dict(
                id="guard",
                kind="condition",
                summary="检查目标更新的对象与类型",
                expression=dict(
                    kind="all",
                    items=[
                        dict(
                            kind="runtime",
                            key="enemy_command_work_valid",
                            source="work",
                        ),
                        dict(kind="runtime", key="self_extend_valid", source="Extend"),
                    ],
                ),
                true="write",
                false="return",
            ),
        )
        self.assertEqual(result["title"], "检查目标更新的对象与类型")
        self.assertTrue(result["presentation"]["compact"])
        self.assertEqual(result["true"], "table/write")
        self.assertEqual(result["false"], "table/return")

    def test_target_writes_invalidate_snapshot_and_preserve_native_description(self):
        compiler = PlayerCompiler(dict(tables=[], rules=dict(rules=[])))
        updates = [
            dict(
                order=0,
                category=18,
                position=dict(kind="native_vector_formula", formula="T+(P-T)"),
            )
        ]
        result = compiler.node(
            "table",
            dict(
                id="write",
                kind="mutation",
                effect="update_target_positions",
                summary="更新侧向目标并保存原目标位置",
                targetUpdates=updates,
                next="continue",
            ),
        )
        self.assertTrue(result["invalidateSnapshot"])
        self.assertEqual(result["targetUpdates"], updates)
        self.assertEqual(result["title"], "更新侧向目标并保存原目标位置")
        self.assertEqual(result["next"], "table/continue")
        result["targetUpdates"][0]["category"] = 10
        self.assertEqual(updates[0]["category"], 18)

    def test_boolean_command_effect_preserves_snapshot_and_declares_its_write(self):
        compiler = PlayerCompiler(dict(tables=[], rules=dict(rules=[])))
        result = compiler.node(
            "table",
            dict(
                id="write",
                kind="mutation",
                effect="apply_boolean_command_effects",
                summary="更新吸收状态",
                stateUpdates={"extend:fixture._State": 5},
                next="continue",
            ),
        )
        self.assertFalse(result["invalidateSnapshot"])
        self.assertEqual(result["title"], "更新吸收状态")
        self.assertEqual(result["stateUpdates"], {"extend:fixture._State": 5})
        self.assertEqual(result["next"], "table/continue")

    def test_declared_updates_change_later_checks_and_invalidate_old_assumptions(self):
        script = r"""
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
import(pathToFileURL(process.argv[1]).href).then(({applyUpdates, initial, step, evaluate}) => {
const update={variable:'g',kind:'float',operation:'add',value:1,min:0,max:10,definitionStatus:'bound',readOnly:false};
assert.equal(applyUpdates({variableUpdate:update},{'float:g':9.5})['float:g'],10);
assert.equal(applyUpdates({variableUpdate:update},{})['float:g'],undefined);
const guard={op:'compare',key:'valid',operator:'eq',value:true};
assert.equal(applyUpdates({variableUpdate:update,updateGuard:guard},{valid:false,'float:g':0})['float:g'],0);
assert.equal(applyUpdates({variableUpdate:update,updateGuard:guard},{'float:g':0})['float:g'],undefined);
assert.equal(applyUpdates({variableUpdate:{...update,readOnly:true}},{'float:g':0})['float:g'],0);
assert.equal(applyUpdates({variableUpdate:{variable:'b',kind:'bool',operation:'assign',value:false,definitionStatus:'bound',readOnly:false}},{'variable:b':true})['variable:b'],false);
assert.equal(applyUpdates({variableUpdate:{variable:'t',kind:'timer',operation:'activate',default:60,definitionStatus:'bound',readOnly:false}},{'timer:t':true})['timer:t'],false);
const nodes={
 before:{kind:'condition',sourceRef:'before',condition:{op:'compare',key:'float:g',operator:'lt',value:1},true:'write',false:'end'},
 write:{kind:'mutation',sourceRef:'write',next:'after',variableUpdate:update,invalidateSnapshot:false},
 after:{kind:'condition',sourceRef:'after',condition:{op:'compare',key:'float:g',operator:'eq',value:1},true:'action',false:'end'},
 action:{kind:'action',sourceRef:'action',title:'A',resume:'end'},end:{kind:'return',sourceRef:'end'}
};
const view={nodes,scenario:{inputs:{}}};
const before=step(view,initial(view,{id:'before'},{'float:g':0}));
const after=step(view,before.children[0].state);
assert.equal(after.truth,true);assert.equal(after.children.length,1);
assert.equal(after.children[0].state.inputs['float:g'],1);
const history='table_history:fixture:max';
view.persistentState=[history];
const action=step(view,initial(view,{id:'action'},{[history]:41,'float:g':1}));
assert.equal(action.children[0].state.inputs[history],41);
assert.equal(action.children[0].state.inputs['float:g'],undefined);
assert.equal(applyUpdates({stateUpdates:{[history]:null}},{[history]:41})[history],undefined);
// A true Boolean command writes before its successor and invalidates only
// assumptions about the changed field; its false branch leaves state alone.
const field='extend:fixture._State';
nodes.checkState={kind:'condition',sourceRef:'checkState',condition:{op:'compare',key:field,operator:'eq',value:4},true:'boolWrite',false:'end'};
nodes.boolWrite={kind:'mutation',sourceRef:'boolWrite',effect:'apply_boolean_command_effects',stateUpdates:{[field]:5},next:'checkStateAgain',invalidateSnapshot:false};
nodes.checkStateAgain={kind:'condition',sourceRef:'checkStateAgain',condition:{op:'compare',key:field,operator:'eq',value:4},true:'action',false:'end'};
const checked=step(view,initial(view,{id:'checkState'},{[field]:4,'float:g':2}));
const afterBool=step(view,checked.children[0].state);
assert.equal(afterBool.truth,false);
assert.equal(afterBool.children[0].state.inputs[field],5);
assert.equal(afterBool.children[0].state.inputs['float:g'],2);
const rejected=step(view,initial(view,{id:'checkState'},{[field]:3}));
assert.equal(rejected.truth,false);
assert.equal(rejected.children[0].state.inputs[field],3);
nodes.dynamic={kind:'mutation',sourceRef:'dynamic',title:'请求选定的越障动作',dynamicAction:true,invalidateSnapshot:true,next:'end'};
assert.equal(step(view,initial(view,{id:'dynamic'},{})).title,'请求选定的越障动作');
}).catch(error=>{console.error(error);process.exit(1);});
"""
        result = subprocess.run(
            [
                shutil.which("node"),
                "-e",
                script,
                str(ROOT / "web/src/sites/enemy_battle_logic/player_engine.js"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unexplained_actions_are_named_by_class_and_parameter_set(self):
        from sdk.enemy_logic_exporter.shared.models.player_view import (
            technical_action_names,
        )

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
            action(
                "a", "cDash", variant="v", pointer="/_BranchedParamsList/3/_Params/1"
            ),
            action("b", "cGlide", source=base),
            action("c1234567x", "cTwin"),
            action("d7654321x", "cTwin"),
        ]
        names = technical_action_names(
            dict(enemyId="EM0002_50_0", tables=[dict(nodes=nodes)])
        )
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

    def test_browser_filter_and_continuation_semantics(self):
        script = r"""
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
import(pathToFileURL(process.argv[1]).href).then(({compare, evaluate, initial, step}) => {
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
// Standing scenario facts survive an action, so a settled internal check
// after it passes through; snapshot inputs are still cleared.
const guard={op:'compare',key:'solo',operator:'eq',value:true};
const settledView={nodes:{
  act:{kind:'action',sourceRef:'act',title:'A',resume:'check'},
  check:{kind:'condition',sourceRef:'check',checks:'单人',condition:guard,presentation:{compact:true},true:'dist',false:'done'},
  dist:{kind:'condition',sourceRef:'dist',condition:{op:'compare',key:'d',operator:'lt',value:10},true:'done',false:'done'},
  done:{kind:'return',sourceRef:'done'},
},scenario:{inputs:{solo:true},persistent:['solo']}};
const acted=step(settledView,initial(settledView,{id:'act'},{d:5}));
const resumed=step(settledView,acted.children[0].state);
assert.equal(resumed.sourceRef,'dist');
assert.equal(resumed.truth,null);
assert.deepEqual(resumed.via.map(v=>[v.kind,v.truth]),[['check',true]]);
// An unsettled internal check stays a visible branch point.
settledView.scenario.persistent=[];
const actedAgain=step(settledView,initial(settledView,{id:'act'},{d:5}));
assert.equal(step(settledView,actedAgain.children[0].state).sourceRef,'check');
console.log('player engine boundaries and continuations passed');
}).catch(error => { console.error(error); process.exit(1); });
"""
        result = subprocess.run(
            [
                shutil.which("node"),
                "-e",
                script,
                str(ROOT / "web/src/sites/enemy_battle_logic/player_engine.js"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
