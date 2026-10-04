"""Render an offline review workbench without treating evidence as recovered AI."""

import json


def render_workbench(result, inventory, requests):
    data = json.dumps(
        dict(result=result, inventory=inventory, requests=requests),
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    template = r"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>大型怪物离线分析结果</title>
<style>body{font:15px/1.6 system-ui,sans-serif;background:#f5f7fa;color:#20334a;max-width:1450px;margin:auto;padding:30px}h1{margin:0 0 8px}header,panel,section{display:block;background:white;border:1px solid #dce3ed;border-radius:12px;padding:20px;margin:15px 0}.status{color:#a05223;background:#fff4e5;padding:12px;border-radius:8px}select,input{font:inherit;padding:8px;border:1px solid #b6c5d6;border-radius:6px;max-width:100%}table{width:100%;border-collapse:collapse;margin-top:12px}th,td{text-align:left;padding:9px;border-bottom:1px solid #e4eaf1;overflow-wrap:anywhere}th{background:#edf2f8}td.guid{font:12px/1.5 monospace}summary{cursor:pointer}small{color:#5d6e83}a{color:#2164a2}.scroll{max-height:600px;overflow:auto}.stats{display:flex;gap:20px;flex-wrap:wrap}.stats b{font-size:25px;display:block}</style>
<header><h1>大型怪物离线分析结果</h1><p>资源、原生证据与动作身份的全量运行结果。每个怪物的实际分支、调用、返回和状态切换，需要独立完成语义恢复。</p><div class="status" id="status"></div><div class="stats" id="stats"></div></header>
<section><p><a href="native-flow/index.html">查看全部 34 个怪物的原生基本块流程图（语义待审核）</a></p><label>选择怪物 <select id="enemy"></select></label> <span id="model"></span><p id="coverage"></p><details><summary>行为表与真实资源主人</summary><div class="scroll"><table><thead><tr><th>行为表</th><th>子表方法数</th><th>资源</th></tr></thead><tbody id="tables"></tbody></table></div></details></section>
<section><h2>已核对的显式动作请求</h2><p>中文说明名来自动作类含义。动作 GUID 和参数变体由原生请求位置与资源核对；此目录没有推断招式概率或先后顺序。</p><label>筛选名称、动作类或 GUID <input id="filter" type="search"></label><div class="scroll"><table><thead><tr><th>名称／动作类</th><th>动作 GUID</th><th>参数变体 GUID</th><th>请求位置数</th></tr></thead><tbody id="actions"></tbody></table></div></section>
<section><h2>项目已有原始名称</h2><p>以下 Shell 名称与注释保留原始 UID。尚未核实的动作到具体 Shell 触发关系没有建立映射。</p><div class="scroll"><table><thead><tr><th>UID</th><th>原名</th><th>原注释</th><th>资源</th></tr></thead><tbody id="shells"></tbody></table></div></section>
<details><summary>运行来源与未完成范围</summary><pre id="receipt"></pre></details><script type="application/json" id="data">__DATA__</script><script>
const d=JSON.parse(document.getElementById('data').textContent),q=id=>document.getElementById(id),resources=new Map(d.inventory.resources.map(x=>[x.resource,x]));
function cell(row,text,cls){let td=document.createElement('td');td.textContent=text;if(cls)td.className=cls;row.append(td)}
function rows(id,items,columns){q(id).replaceChildren();for(const item of items){let tr=document.createElement('tr');for(const c of columns)cell(tr,c.value(item),c.cls);q(id).append(tr)}}
q('status').textContent=d.result.releaseReady?'已通过完整语义模型验收':'全量原生证据已提取；完整语义行动树尚未完成，当前结果不能通过正式发布验收。';
for(const [n,v] of [['大型怪物',d.inventory.monsterCount],['行为表资源',d.inventory.uniqueBTableResources],['原生代码段',d.result.nativeExtraction.completedBodies],['已核对动作变体',d.result.actionRequests.distinctActionVariants]]){let e=document.createElement('p'),b=document.createElement('b');b.textContent=v;e.append(b,document.createTextNode(n));q('stats').append(e)}
for(const m of d.inventory.monsters){let o=document.createElement('option');o.value=m.enemyId;o.textContent=m.enemyId;q('enemy').append(o)}
let actionRows=[];
function filter(){let s=q('filter').value.toLowerCase();rows('actions',actionRows.filter(x=>JSON.stringify(x).toLowerCase().includes(s)),[{value:x=>x.displayName+' / '+x.actionClass},{value:x=>x.actionGuid,cls:'guid'},{value:x=>x.parameterVariantGuid,cls:'guid'},{value:x=>x.count}])}
function update(){let m=d.inventory.monsters.find(x=>x.enemyId===q('enemy').value),set=new Set(m.tableImportClosure),events=d.requests.actionRequestBindings.filter(x=>set.has(x.resource)),counts=new Map();for(const e of events)counts.set(e.actionRef,(counts.get(e.actionRef)||0)+1);actionRows=[...counts].map(([k,count])=>({...d.requests.actionCatalog[k],count}));filter();q('coverage').textContent=m.tableImportClosure.length+' 份实际行为表资源；'+events.length+' 个已核对显式请求位置。语义覆盖状态见运行记录。';rows('tables',m.tableImportClosure.map(p=>resources.get(p)),[{value:x=>x.exportType},{value:x=>x.nativeTableMethods},{value:x=>x.resource}]);rows('shells',d.inventory.shellNameCatalog.filter(s=>m.shellNameResources.includes(s.resource)).flatMap(s=>s.entries),[{value:x=>x.uniqueId},{value:x=>x.name},{value:x=>x.comment},{value:x=>x.source}]);q('model').replaceChildren();let found=d.result.semanticModels.find(x=>x.enemyId===m.enemyId);if(found){let a=document.createElement('a');a.href='semantic-preview/enemy_battle_logic/'+m.enemyId+'.html';a.textContent='查看已恢复的语义行动图（'+found.coverage.nodes+' 个节点，部分恢复）';q('model').append(a)}else q('model').textContent='此怪物的语义行动树尚未固化';}
q('enemy').addEventListener('change',update);q('filter').addEventListener('input',filter);q('receipt').textContent=JSON.stringify(d.result,null,2);update();
</script></html>"""
    return template.replace("__DATA__", data)
