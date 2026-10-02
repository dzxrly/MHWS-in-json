const catalog = JSON.parse(document.getElementById('enemy-catalog').textContent);
const enemies = catalog.enemies;
const panels = [...document.querySelectorAll('.diagram')];
const enemy = document.getElementById('enemy');
const phase = document.getElementById('phase');
const viewport = document.getElementById('viewport');
let scale = 1;
let hit = 0;

function currentEnemy() { return enemies.find(e => e.enemyId === enemy.value); }
function currentGraph() { return currentEnemy().graphs[Number(phase.value)]; }
function current() { return panels.find(p => p.dataset.enemy === enemy.value && p.dataset.phase === phase.value); }

function zoom(value, keep = true) {
  const cx = (viewport.scrollLeft + viewport.clientWidth / 2) / scale;
  const cy = (viewport.scrollTop + viewport.clientHeight / 2) / scale;
  scale = Math.max(.002, Math.min(4, value));
  const s = current().querySelector('svg');
  s.style.width = s.viewBox.baseVal.width * scale + 'px';
  s.style.height = s.viewBox.baseVal.height * scale + 'px';
  if (keep) {
    viewport.scrollLeft = cx * scale - viewport.clientWidth / 2;
    viewport.scrollTop = cy * scale - viewport.clientHeight / 2;
  }
  document.getElementById('status').textContent = (scale < .1 ? (scale * 100).toFixed(1) : Math.round(scale * 100)) + '%';
}

function focusEntry() {
  zoom(1, false);
  const el = [...current().querySelectorAll('.node')].find(n => n.dataset.node === currentGraph().entry);
  const b = el.getBBox();
  viewport.scrollLeft = Math.max(0, b.x + b.width / 2 - viewport.clientWidth / 2);
  viewport.scrollTop = Math.max(0, b.y - 35);
}

function showPhase() {
  panels.forEach(p => p.hidden = p !== current());
  current().classList.remove('has-selection');
  current().querySelectorAll('.selected,.upstream,.downstream,.interrupted,.path-node').forEach(n => n.classList.remove('selected', 'upstream', 'downstream', 'interrupted', 'path-node'));
  document.getElementById('notes').textContent = currentGraph().basis === 'native_flow' ? 'x 是玩家给定距离；d 是源码里的命令距离，尚未完成单位与目标对应的校准。实线保留已知关系，虚线处条件或去向待恢复。选中动作后显示其外层中断连线。' : '当前只有资源证据。距离、状态与派生条件尚未恢复，以下动作版本的阶段适用范围也待确认。';
  document.getElementById('limitations').textContent = currentGraph().limitations.join('\n\n');
  document.getElementById('action-detail').textContent = '本阶段关联 ' + currentGraph().coverage.displayedActionTypes + ' 种动作类型、' + currentGraph().coverage.actionVersions + ' 个参数版本。动作请求位置分别保留。点击节点追踪条件和后续，或按名称搜索。';
  document.getElementById('source-detail').textContent = '';
  hit = 0;
  focusEntry();
}

function showEnemy() {
  phase.replaceChildren(...currentEnemy().graphs.map((g, i) => {
    const option = document.createElement('option');
    option.value = String(i);
    option.textContent = g.title;
    return option;
  }));
  const e = currentEnemy();
  document.getElementById('identity').textContent = e.enemyId + ' · ' + e.name;
  showPhase();
}

function select(element) {
  current().classList.add('has-selection');
  current().querySelectorAll('.selected').forEach(n => n.classList.remove('selected'));
  element.classList.add('selected');
  tracePaths(element.dataset.node);
  const node = currentGraph().nodes.find(n => n.id === element.dataset.node);
  const detail = node.detail || {};
  const target = document.getElementById('action-detail');
  target.replaceChildren();
  const title = document.createElement('p');
  title.textContent = node.label.split('\n')[0];
  target.append(title);
  if (detail.stateCases) {
    const conditions = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = '查看候选所覆盖的状态组合';
    const text = document.createElement('pre');
    const names = { hostility: '敌视', rampage: '愤怒状态', hl: 'HL', spatk_end: '大招结束标记', spatk_request: '大招请求标记' };
    const states = detail.stateCases.map(c => Object.entries(c.state || c).map(([k, v]) => (names[k] || k) + '：' + (v ? '是' : '否')).join('；'));
    text.textContent = '这些是静态选招分析采用的状态组合；其他筛选条件仍待还原。\n\n' + [...new Set(states)].join('\n');
    conditions.append(summary, text);
    target.append(conditions);
  }
  for (const action of detail.action ? [detail.action] : detail.actions || []) {
    const item = document.createElement('div');
    item.className = 'action-item';
    const name = document.createElement('strong');
    name.textContent = catalog.actionNames[action.type] || action.type;
    const type = document.createElement('code');
    type.textContent = action.type;
    item.append(name, type);
    const parameters = document.createElement('p');
    parameters.textContent = [action.versionLabel, ...(action.parameterNotes || [])].filter(Boolean).join('；');
    item.append(parameters);
    if (action.requestSite) {
      const route = document.createElement('p');
      route.textContent = '本节点保留这一请求位置的调用上下文，正常完成后只继续所属路径。';
      item.append(route);
    }
    target.append(item);
  }
  const incoming = currentGraph().edges.filter(e => e.to === node.id && !e.back);
  if (incoming.length) {
    const conditions = document.createElement('p');
    conditions.textContent = '直接进入条件：' + incoming.map(e => (e.label || '沿本路径进入') + '；上一步：' + currentGraph().nodes.find(n => n.id === e.from).label.split('\n')[0]).join('。');
    target.append(conditions);
  }
  if (detail.continuation) {
    const continuation = document.createElement('p');
    continuation.textContent = detail.continuation.label;
    target.append(continuation);
  }
  if (detail.executionUnresolved) {
    const unknown = document.createElement('p');
    unknown.textContent = '已恢复本动作的请求与参数身份；动作内部状态和完成条件尚未恢复。';
    target.append(unknown);
  }
  const note = document.createElement('p');
  note.textContent = '橙色线：上游条件；蓝色线：本动作与正常后续；红色线：外层中断。等待循环和下一轮决策不向外继续展开。';
  target.append(note);
  document.getElementById('source-detail').textContent = JSON.stringify(detail, null, 2);
}

function tracePaths(id) {
  const graph = currentGraph();
  const nodes = new Map(graph.nodes.map(n => [n.id, n]));
  const context = nodes.get(id).detail?.context;
  const visible = new Set([id]), up = new Set(), down = new Set(), interruptions = new Set();
  const excluded = e => e.back || ['wait','new_decision','interruption','related'].includes(e.role);
  function visit(reverse, chosen) {
    const seen = new Set([id]), queue = [id];
    while (queue.length) {
      const at = queue.shift();
      if (at !== id && ((!reverse && nodes.get(at).kind === 'end') ||
          (nodes.get(at).kind === 'action' && nodes.get(at).detail?.context !== context))) continue;
      graph.edges.forEach((e, index) => {
        if (excluded(e) || (reverse ? e.to : e.from) !== at) return;
        const other = reverse ? e.from : e.to;
        chosen.add(index); visible.add(other);
        if (!seen.has(other)) { seen.add(other); queue.push(other); }
      });
    }
  }
  visit(true, up); visit(false, down);
  graph.edges.forEach((e,index) => {
    if (e.role === 'interruption' && e.from === id) { interruptions.add(index); visible.add(e.to); }
  });
  const indexed = new Map();
  graph.edges.forEach((e,index) => {
    const key = e.from+'\0'+e.to;
    if (!indexed.has(key)) indexed.set(key, []);
    indexed.get(key).push(index);
  });
  current().querySelectorAll('.edge,.edge-label').forEach(el => {
    const ids = indexed.get(el.dataset.from+'\0'+el.dataset.to) || [];
    el.classList.toggle('upstream', ids.some(i => up.has(i)));
    el.classList.toggle('downstream', ids.some(i => down.has(i)));
    el.classList.toggle('interrupted', ids.some(i => interruptions.has(i)));
  });
  current().querySelectorAll('.node').forEach(n => n.classList.toggle('path-node', visible.has(n.dataset.node)));
}

function find() {
  const query = document.getElementById('search').value.trim().toLowerCase();
  if (!query) return;
  const matched = currentGraph().nodes.filter(n => n.label.toLowerCase().includes(query));
  if (!matched.length) {
    document.getElementById('action-detail').textContent = '没有找到匹配动作或节点';
    return;
  }
  const id = matched[hit++ % matched.length].id;
  const el = [...current().querySelectorAll('.node')].find(n => n.dataset.node === id);
  zoom(Math.max(scale, 1));
  select(el);
  el.scrollIntoView({ block: 'center', inline: 'center' });
}

enemy.addEventListener('change', showEnemy);
phase.addEventListener('change', showPhase);
document.getElementById('plus').onclick = () => zoom(scale * 1.25);
document.getElementById('minus').onclick = () => zoom(scale / 1.25);
document.getElementById('actual').onclick = () => zoom(1);
document.getElementById('entry').onclick = focusEntry;
document.getElementById('fit').onclick = () => {
  const box = current().querySelector('svg').viewBox.baseVal;
  zoom(Math.min((viewport.clientWidth - 40) / box.width, (viewport.clientHeight - 40) / box.height), false);
  viewport.scrollTo(0, 0);
};
document.getElementById('find').onclick = find;
document.getElementById('search').addEventListener('keydown', e => { if (e.key === 'Enter') find(); });
panels.forEach(p => {
  p.addEventListener('click', e => { const node = e.target.closest('.node'); if (node) select(node); });
  p.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.classList.contains('node')) select(e.target); });
});
if (enemies.some(e => e.enemyId === 'EM0166_00_0')) enemy.value = 'EM0166_00_0';
showEnemy();
