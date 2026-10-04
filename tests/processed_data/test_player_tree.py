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
