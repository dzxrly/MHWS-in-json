/* Offline research viewer. Successor lines do not assert reviewed condition semantics. */
window.NATIVE_TABLES = {};
const nativeData = JSON.parse(document.getElementById('data').textContent);
const nativeElement = id => document.getElementById(id);
const nativeResources = new Map(nativeData.resources.map(r => [r.resource, r]));
const nativeIds = new Map(nativeData.resources.map(r => [r.id, r]));
const nativeElk = new ELK();
let nativeCurrent, nativeLayout, nativeZoom = 1, nativeRevision = 0;
function nativeOption(select, value, label) {
  const option = document.createElement('option'); option.value = value; option.textContent = label; select.append(option);
}
function nativeSvg(name, attrs = {}, text) {
  const e = document.createElementNS('http://www.w3.org/2000/svg', name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
}
function nativeParagraph(text) {
  const p = document.createElement('p'); p.textContent = text; nativeElement('detail').append(p); return p;
}
function nativeInspect(block) {
  nativeElement('detail').replaceChildren();
  nativeParagraph('基本块 ' + block.id + ' · ' + block.start + ' — ' + block.end);
  nativeParagraph('后继：' + (block.successors.join('、') || '无；检查 RETURN 或其他终止操作'));
  for (const a of block.actions) {
    nativeParagraph(a.displayName + ' / ' + a.actionClass);
    nativeParagraph('请求 GUID：' + a.actionGuid + '\n实例 GUID：' + a.instanceActionGuid + '\n参数变体：' + a.parameterVariantGuid + '\n写入位置：' + a.site + '；工厂 ' + a.commandIndex + '，参数 ' + a.argumentIndex);
    nativeParagraph('来源：' + a.source + '\n参数：' + a.parameterAsset + a.parameterBodyPointer + '\n' + (a.parameterOverridesResolved ? '无参数继承覆盖' : '参数继承覆盖尚未完整合并'));
  }
  for (const c of block.calls) {
    const p = nativeParagraph((c.direct ? '直接调用 ' + c.address : '间接调用，目标未解析') + ' · ' + c.site);
    for (const target of c.targets) {
      const button = document.createElement('button'); button.textContent = target.type + ' / ' + target.method;
      button.addEventListener('click', () => nativeFollow(target)); p.append(document.createElement('br'), button);
    }
  }
  if (!block.actions.length) nativeParagraph('此块没有已绑定的显式选动作请求；其他语义需继续核实。');
}
function nativeScale(fit = false) {
  if (!nativeLayout) return;
  if (fit) nativeZoom = Math.min(1, (nativeElement('viewport').clientWidth - 24) / nativeLayout.width);
  const svg = nativeElement('graph'); svg.setAttribute('width', nativeLayout.width * nativeZoom); svg.setAttribute('height', nativeLayout.height * nativeZoom);
  svg.setAttribute('viewBox', '0 0 ' + nativeLayout.width + ' ' + nativeLayout.height);
}
async function nativeDraw() {
  const revision = ++nativeRevision;
  const resource = nativeIds.get(nativeElement('resource').value), table = window.NATIVE_TABLES[resource.id];
  nativeCurrent = table.methods.find(m => m.method === nativeElement('method').value);
  nativeElement('graph').replaceChildren(); nativeLayout = null;
  if (!nativeCurrent) { nativeElement('loading').textContent = '资源没有原生子表或调度器；保留空资源记录。'; return; }
  const current = nativeCurrent, labels = new Map();
  for (const b of current.blocks) labels.set(b.id, ['块 ' + b.id + ' · ' + b.start, ...(b.actions.length ? b.actions.map(a => a.displayName + ' / ' + a.actionClass) : [b.successors.length > 1 ? '原生分支；条件语义待核实' : b.terminalOperations.includes('RETURN') ? '原生返回；返回含义待核实' : '原生操作']), '直接／间接调用：' + b.calls.length]);
  const graph = {id:'flow', layoutOptions:{'elk.algorithm':'layered','elk.direction':'DOWN','elk.edgeRouting':'ORTHOGONAL','elk.layered.spacing.nodeNodeBetweenLayers':'45'}, children:current.blocks.map(b => ({id:b.id,width:340,height:Math.max(82,labels.get(b.id).length*20+20)})), edges:current.blocks.flatMap(b => b.successors.map((target,i) => ({id:b.id+'_'+i,sources:[b.id],targets:[target]})))};
  nativeElement('loading').textContent = '正在布局 ' + graph.children.length + ' 个真实基本块…';
  try {
    const layout = await nativeElk.layout(graph);
    if (revision !== nativeRevision) return;
    nativeLayout = layout;
    const svg = nativeElement('graph'), defs = nativeSvg('defs'), marker = nativeSvg('marker',{id:'arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto-start-reverse'});
    marker.append(nativeSvg('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#7690aa'})); defs.append(marker); svg.append(defs);
    for (const e of layout.edges || []) for (const s of e.sections || []) {
      const points = [s.startPoint,...(s.bendPoints || []),s.endPoint];
      svg.append(nativeSvg('path',{class:'edge',d:points.map((p,i)=>(i?'L':'M')+p.x+' '+p.y).join(' '),'marker-end':'url(#arrow)'}));
    }
    for (const n of layout.children) {
      const b = current.blocks.find(x=>x.id===n.id), group = nativeSvg('g',{class:'node',transform:'translate('+n.x+','+n.y+')'});
      group.append(nativeSvg('rect',{width:n.width,height:n.height,rx:7,fill:b.actions.length?'#e0f3e8':b.successors.length>1?'#fff0d3':'#edf3fb',stroke:'#8ea4bc'}));
      labels.get(b.id).forEach((t,i)=>group.append(nativeSvg('text',{x:12,y:23+i*20},t.length>45?t.slice(0,44)+'…':t)));
      group.addEventListener('click',()=>nativeInspect(b)); svg.append(group);
    }
    nativeZoom = .85; nativeScale();
    const entry = layout.children.find(n=>n.id===current.entryBlock) || layout.children[0];
    if (entry) {nativeElement('viewport').scrollLeft=Math.max(0,entry.x*nativeZoom-24);nativeElement('viewport').scrollTop=Math.max(0,entry.y*nativeZoom-24);}
    nativeElement('loading').textContent = '';
    nativeElement('status').textContent = current.type+' · '+current.method+'；'+current.blocks.length+' 个块，'+graph.edges.length+' 条真实后继线。入口块：'+(current.entryBlock??'未唯一定位')+'。';
    nativeElement('code').textContent = (current.rangeBoundaryWarnings.length ? '警告：反编译基本块起点超出方法范围，块 '+current.rangeBoundaryWarnings.join(', ')+'，需单独核查边界。\n\n' : '') + (current.unplacedActionSites.length ? '未唯一定位到基本块的请求：'+current.unplacedActionSites.join(', ')+'\n\n':'')+current.code;
    nativeElement('detail').replaceChildren(); nativeParagraph('选择基本块查看动作和调用。原生字节 SHA-256：'+current.nativeSha256); nativeParagraph('同地址别名：'+JSON.stringify(current.addressAliases));
  } catch (error) { if (revision === nativeRevision) nativeElement('loading').textContent='布局失败：'+error.message; }
}
async function nativeLoadResource(method) {
  const identity = nativeElement('resource').value;
  if (!window.NATIVE_TABLES[identity]) {
    nativeElement('loading').textContent = '读取当前行为表的离线数据…';
    try { await new Promise((resolve,reject)=>{const s=document.createElement('script');s.src='tables/'+identity+'.js';s.onload=resolve;s.onerror=()=>reject(new Error('缺少离线数据 '+identity));document.head.append(s)}); }
    catch(error) { nativeElement('loading').textContent=error.message; return; }
  }
  if (nativeElement('resource').value !== identity) return;
  const methods = window.NATIVE_TABLES[identity].methods, select = nativeElement('method'); select.replaceChildren();
  for (const m of methods) nativeOption(select,m.method,(m.method.startsWith('updateTableInpl')?'调度器 · ':'子表 · ')+m.method);
  select.value = method || methods.find(m=>m.method.startsWith('updateTableInpl'))?.method || methods[0]?.method || '';
  await nativeDraw();
}
async function nativeUpdateEnemy() {
  const monster = nativeData.monsters.find(m=>m.enemyId===nativeElement('enemy').value), select = nativeElement('resource'); select.replaceChildren();
  for (const source of monster.tableImportClosure) {const r=nativeResources.get(source), roles=Object.entries(monster.slots).filter(([,p])=>p===source).map(([k])=>k);nativeOption(select,r.id,(roles.length?roles.join('/')+' · ':'导入 · ')+r.type)}
  select.value = nativeResources.get(monster.slots.COMBAT).id;
  await nativeLoadResource();
}
async function nativeFollow(target) {
  const resource = nativeIds.get(target.resourceId);
  if (![...nativeElement('resource').options].some(o=>o.value===resource.id)) {
    const monster=nativeData.monsters.find(m=>m.tableImportClosure.includes(resource.resource));
    nativeElement('enemy').value=monster.enemyId; await nativeUpdateEnemy();
  }
  nativeElement('resource').value=resource.id; await nativeLoadResource(target.method);
}
for (const monster of nativeData.monsters) nativeOption(nativeElement('enemy'),monster.enemyId,monster.enemyId);
nativeElement('enemy').addEventListener('change',nativeUpdateEnemy);
nativeElement('resource').addEventListener('change',()=>nativeLoadResource());
nativeElement('method').addEventListener('change',nativeDraw);
nativeElement('fit').addEventListener('click',()=>nativeScale(true));
nativeElement('smaller').addEventListener('click',()=>{nativeZoom=Math.max(.1,nativeZoom/1.25);nativeScale()});
nativeElement('larger').addEventListener('click',()=>{nativeZoom=Math.min(4,nativeZoom*1.25);nativeScale()});
nativeElement('export').addEventListener('click',()=>{if(!nativeLayout)return;const copy=nativeElement('graph').cloneNode(true);copy.setAttribute('width',nativeLayout.width);copy.setAttribute('height',nativeLayout.height);const style=nativeSvg('style',{},'.node text{font:12px sans-serif;fill:#20334d}.edge{fill:none;stroke:#7690aa;stroke-width:1.3}');copy.prepend(style);const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)],{type:'image/svg+xml'})),a=document.createElement('a');a.href=url;a.download=nativeCurrent.method+'.svg';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
nativeElement('receipt').textContent=JSON.stringify({profile:nativeData.profile,coverage:nativeData.counts,semanticReviewCompleted:false},null,2);
nativeUpdateEnemy();
