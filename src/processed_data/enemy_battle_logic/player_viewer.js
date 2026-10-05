/* One interactive decision tree per monster: groups, BTable slots, branches. */
(function () {
  "use strict";
  const { graph } = JSON.parse(document.getElementById("data").textContent);
  const view = graph.playerView, panel = document.getElementById("player-panel");
  if (!view) { panel.hidden = true; window.startTechnicalGraph(); return; }
  const engine = window.BattlePlayer, ns = "http://www.w3.org/2000/svg";
  const $ = id => document.getElementById(id);
  const viewport = $("player-viewport"), canvas = $("player-canvas"), scene = $("player-scene");
  const status = $("player-status"), selection = $("player-selection"), body = panel.querySelector(".player-body");
  const sources = new Map();
  for (const table of graph.tables) for (const node of table.nodes) sources.set(`${table.tableGuid}/${node.id}`, { table, node });

  const NODE_W = 236, GAP_X = 178, GAP_Y = 14, LINE = 18, INITIAL_BUDGET = 150, INITIAL_DEPTH = 5;
  const fills = { root: "#14273c", group: "#dfe8f1", entry: "#d9ecf7", condition: "#edf7f0", action: "#e8f2fc", weighted_random: "#fff6de", mutation: "#f3eefb", unknown: "#fff0e7", return: "#f0f3f7", loop: "#f0f3f7", ref: "#f1f3f6" };
  const badges = { condition: "条件判断", weighted_random: "候选选择", action: "动作请求", mutation: "战斗流程变化", unknown: "逻辑待核查", return: "返回 / 本轮结束", loop: "回到此前判断", ref: "同前 · 已在别处展开" };

  function html(tag, text, className) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (className) e.className = className;
    return e;
  }
  function svg(tag, attrs, text) {
    const e = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attrs || {})) e.setAttribute(key, value);
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function wrap(text, width) {
    const result = [];
    for (const part of String(text).split("\n")) {
      let line = "", used = 0;
      for (const char of part) {
        const size = char.codePointAt(0) > 255 ? 1 : .55;
        if (used + size > width && line) { result.push(line); line = ""; used = 0; }
        line += char; used += size;
      }
      if (line) result.push(line);
    }
    return result.length ? result : [""];
  }

  // ------------------------------------------------------------ tree model
  let uid = 0, inputs = {}, root, shown = new Map(), selected = null;
  const records = new Map();
  function stateKey(state) { return JSON.stringify([state.key, state.stack, state.afterAction, state.inputs, Object.entries(state.assumptions).sort()]); }
  function record(state) {
    const key = stateKey(state);
    if (!records.has(key)) records.set(key, engine.step(view, { ...state, seen: [] }));
    return { key, record: records.get(key) };
  }
  function make(kind, title, extra = {}) {
    const node = { uid: "n" + uid++, kind, title, children: null, expanded: false, ...extra };
    node.compact = !!node.record?.presentation?.compact;
    if (node.compact) node.title = "内部检查";
    const lines = wrap(node.title, 15);
    node.lines = lines;
    node.h = node.compact ? 30 : 30 + lines.length * LINE + (node.subtitle ? LINE : 0);
    return node;
  }
  function recordNode(state, label, parent, extra = {}) {
    const { key, record: rec } = record(state);
    const kind = rec.kind;
    if (shown.has(key)) {
      return make("ref", rec.presentation?.title || rec.title, { label, parent, refKey: key, record: rec, state, ...extra });
    }
    const node = make(kind, rec.presentation?.title || rec.title, { label, parent, record: rec, state, stateKey: key, ...extra });
    if (rec.kind === "action" && rec.nameStatus === "unresolved") node.subtitle = "动作名称待核查";
    shown.set(key, node);
    return node;
  }
  // Internal checks stay as small nodes: folding them would multiply edges
  // for every unresolved check, while a node per check keeps growth linear.
  function project(rec, parent) {
    return rec.children.map(child => {
      const { record: target } = record(child.state);
      let label = child.label;
      if (target.via?.some(n => n.kind === "mutation")) label += "\n状态更新后继续";
      return recordNode(child.state, label, parent, { role: child.role || (child.slot ? "random" : "next") });
    });
  }
  function children(node) {
    if (node.children) return node.children;
    if (node.kind === "root") node.children = groups.map(g => make("group", g.name, { parent: node, group: g, subtitle: g.entries.length + " 张行为表" }));
    else if (node.kind === "group") node.children = node.group.entries.map(entry => make("entry", entry.label, { parent: node, entry, subtitle: entry.requestedBy?.length ? "由 " + entry.requestedBy.slice(0, 3).join("、") + (entry.requestedBy.length > 3 ? " 等" : "") + " 请求" : entry.relation === "unknown" ? "接入位置待核查" : "" }));
    else if (node.kind === "entry") node.children = [recordNode(engine.initial(view, node.entry, inputs), "开始", node)];
    else if (node.record && node.kind !== "ref") node.children = project(node.record, node);
    else node.children = [];
    return node.children;
  }
  function expandable(node) {
    if (node.kind === "ref") return false;
    if (node.children) return node.children.length > 0;
    if (["root", "group", "entry"].includes(node.kind)) return true;
    return !!node.record?.children.length;
  }

  const groupOrder = [];
  for (const entry of view.entries) {
    const name = entry.group || (entry.relation === "unknown" ? "接入位置待核查的局部分支" : "其他行为表");
    let group = groupOrder.find(g => g.name === name);
    if (!group) { group = { name, entries: [] }; groupOrder.push(group); }
    group.entries.push(entry);
  }
  const groups = groupOrder.sort((a, b) => rank(a) - rank(b));
  function rank(group) {
    if (group.name === "与玩家战斗") return 0;
    if (group.name === "与其他怪物") return 1;
    if (group.name === "接入位置待核查的局部分支") return 3;
    return 2;
  }

  function build() {
    uid = 0; shown = new Map(); records.clear(); selected = null;
    root = make("root", graph.enemyName || graph.enemyId, { subtitle: view.entries.length + " 个入口" });
    root.expanded = true;
    let budget = INITIAL_BUDGET;
    for (const group of children(root)) {
      if (group.group.name !== "与玩家战斗") continue;
      group.expanded = true;
      for (const entry of children(group)) {
        if (entry.entry.slot !== "COMBAT") continue;
        // Open the ordinary-combat selection breadth-first until actions.
        const queue = [{ node: entry, depth: 0 }];
        while (queue.length && budget > 0) {
          const { node, depth } = queue.shift();
          if (!expandable(node) || depth >= INITIAL_DEPTH) continue;
          node.expanded = true;
          for (const child of children(node)) {
            budget--;
            if (child.kind !== "action" && child.kind !== "ref") queue.push({ node: child, depth: depth + (child.compact ? 0 : 1) });
          }
        }
      }
    }
  }

  // ------------------------------------------------------------ layout
  let layout = [], extent = { w: 0, h: 0 };
  function place() {
    layout = [];
    let cursor = 0;
    const bottoms = [];
    function visit(node, depth) {
      node.x = depth * (NODE_W + GAP_X);
      const kids = node.expanded ? children(node) : [];
      if (!kids.length) {
        node.y = Math.max(cursor, bottoms[depth] ?? -Infinity);
        cursor = node.y + node.h + GAP_Y;
      } else {
        for (const child of kids) visit(child, depth + 1);
        // Outline layout: a parent sits level with its first branch, so a
        // large subtree never pushes its siblings' links far apart.
        node.y = kids[0].y + kids[0].h / 2 - node.h / 2;
        const floor = bottoms[depth] ?? -Infinity;
        if (node.y < floor) {
          const delta = floor - node.y;
          shift(node, delta); cursor += delta;
        }
      }
      bottoms[depth] = node.y + node.h + GAP_Y;
      layout.push(node);
    }
    function shift(node, delta) {
      node.y += delta;
      if (node.expanded) for (const child of children(node)) shift(child, delta);
      const depth = Math.round(node.x / (NODE_W + GAP_X));
      bottoms[depth] = Math.max(bottoms[depth] ?? -Infinity, node.y + node.h + GAP_Y);
    }
    visit(root, 0);
    extent = { w: Math.max(...layout.map(n => n.x + NODE_W)), h: Math.max(...layout.map(n => n.y + n.h)) };
  }

  // ------------------------------------------------------------ rendering
  let transform = { x: 24, y: 24, scale: .8 };
  function apply() { scene.setAttribute("transform", `translate(${transform.x} ${transform.y}) scale(${transform.scale})`); }
  function draw() {
    place();
    scene.replaceChildren();
    const edges = svg("g"), nodes = svg("g");
    scene.append(edges, nodes);
    for (const node of layout) {
      if (!node.parent) continue;
      const p = node.parent, x1 = p.x + NODE_W + 10, y1 = p.y + p.h / 2, x2 = node.x, y2 = node.y + node.h / 2, mid = x1 + 24;
      const group = svg("g", { class: `pt-edge ${node.role || ""} ${node.uncertain ? "uncertain" : ""}` });
      const bend = Math.min(10, Math.abs(y2 - y1) / 2), down = y2 >= y1 ? 1 : -1;
      group.append(svg("path", { d: y2 === y1 ? `M${x1},${y1} H${x2 - 6}` : `M${x1},${y1} H${mid - bend} Q${mid},${y1} ${mid},${y1 + bend * down} V${y2 - bend * down} Q${mid},${y2} ${mid + bend},${y2} H${x2 - 6}` }));
      if (node.label) {
        const lines = wrap(node.label, 13), text = svg("text", { x: x2 - 10, y: y2 - (lines.length - 1) * 8 - 4 });
        lines.forEach((line, i) => text.append(svg("tspan", { x: x2 - 10, dy: i ? 16 : 0 }, line)));
        group.append(text);
      }
      edges.append(group);
    }
    for (const node of layout) nodes.append(drawNode(node));
    status.textContent = `已展开 ${layout.length} 个节点 · 点击圆钮展开或收起`;
    panel.dataset.ready = "true"; panel.dataset.nodes = String(layout.length);
    apply();
  }
  function drawNode(node) {
    const dark = node.kind === "root";
    const g = svg("g", { class: "pt-node" + (node.kind === "ref" ? " ref" : "") + (node === selected ? " selected" : "") + (matches.includes(node) && matches[matchIndex] === node ? " match" : ""), transform: `translate(${node.x} ${node.y})`, tabindex: "0", role: "button", "aria-label": node.title, "data-uid": node.uid, "data-kind": node.kind });
    const category = node.record?.presentation?.category;
    g.append(svg("rect", { class: "box", width: NODE_W, height: node.h, rx: 9, fill: node.record?.presentation?.compact ? "#f1f3f6" : fills[node.kind] || "#f1f3f6" }));
    const badge = node.compact ? "内部检查 · 分支保留" : node.kind === "root" ? "怪物" : node.kind === "group" ? "分组" : node.kind === "entry" ? (node.entry.relation === "unknown" ? "局部分支" : "行为表") : category === "distance" ? "距离判断" : category === "angle" ? "角度判断" : category === "state" || category === "phase" ? "状态判断" : badges[node.kind] || "流程";
    g.append(svg("text", { x: 12, y: 17, class: "badge", fill: dark ? "#a5c4dd" : undefined }, badge));
    if (!node.compact) {
      const text = svg("text", { x: 12, y: 38, "font-size": "13", fill: dark ? "#fff" : "#24344b" });
      node.lines.forEach((line, i) => text.append(svg("tspan", { x: 12, dy: i ? LINE : 0 }, line)));
      g.append(text);
    }
    if (node.subtitle) g.append(svg("text", { x: 12, y: 38 + node.lines.length * LINE, "font-size": "11", fill: dark ? "#cfdeec" : "#7a8899" }, node.subtitle));
    if (expandable(node)) {
      const t = svg("g", { class: "pt-toggle", transform: `translate(${NODE_W} ${node.h / 2})`, role: "button", "aria-label": node.expanded ? "收起分支" : "展开分支" });
      t.append(svg("circle", { r: 10 }), svg("text", { y: 5 }, node.expanded ? "−" : "+"));
      t.addEventListener("click", event => { event.stopPropagation(); toggle(node); });
      g.append(t);
    }
    g.addEventListener("click", () => select(node));
    g.addEventListener("dblclick", event => { event.stopPropagation(); toggle(node); });
    g.addEventListener("keydown", event => { if (event.key === "Enter") select(node); if (event.key === " ") { event.preventDefault(); toggle(node); } });
    return g;
  }
  function toggle(node) {
    if (!expandable(node)) return;
    const before = { x: node.x, y: node.y };
    node.expanded = !node.expanded;
    draw();
    // Keep the toggled node under the pointer.
    transform.x += (before.x - node.x) * transform.scale; transform.y += (before.y - node.y) * transform.scale; apply();
  }

  // ------------------------------------------------------------ details
  function path(node) {
    const items = [];
    for (let n = node; n; n = n.parent) items.unshift(n);
    return items;
  }
  function select(node) {
    selected = node;
    scene.querySelectorAll(".pt-node").forEach(e => e.classList.toggle("selected", e.dataset.uid === node.uid));
    selection.replaceChildren(html("h3", node.title));
    if (node.kind === "entry") {
      selection.append(html("p", node.entry.note || ""));
      if (node.entry.requestedBy?.length) selection.append(html("p", "请求此行为表的 AI 状态 / 中断：" + node.entry.requestedBy.join("、")));
    }
    if (node.kind === "ref") {
      const button = html("button", "定位首次展开的位置");
      button.onclick = () => { const target = shown.get(node.refKey); if (target) { reveal(target); focus(target); select(target); } };
      selection.append(html("p", "相同的判断状态已在树的其他位置展开，这里不重复绘制。"), button);
    }
    const steps = path(node).slice(1).map(n => n.label ? `${n.label.split("\n")[0]} → ${n.title}` : n.title);
    if (steps.length) {
      const list = html("ol");
      for (const step of steps) list.append(html("li", step));
      selection.append(html("p", "从怪物到此节点的路径："), list);
    }
    const rec = node.record;
    if (rec) {
      if (rec.presentation?.compact) selection.append(html("p", "此检查会影响分支选择，具体内部条件仍需核查。"));
      if (rec.afterAction) selection.append(html("p", "动作或状态变化后，这里的条件需要重新判断。"));
      if (rec.kind === "weighted_random") selection.append(html("p", "候选权重只描述本次抽签，不是整场战斗的出招概率。"));
      const details = html("details"), summary = html("summary", "原始判断、调用路径与证据");
      details.append(summary);
      details.addEventListener("toggle", () => {
        if (!details.open || details.querySelector("pre")) return;
        const refs = [...new Set([...(rec.via || []).map(n => n.sourceRef), rec.sourceRef])];
        details.append(html("pre", JSON.stringify({ path: refs.map(ref => ({ ref, node: sources.get(ref)?.node, evidence: sources.get(ref)?.table.evidence })), profile: graph.profile }, null, 2)));
      });
      selection.append(details);
    }
    if (body.classList.contains("no-details")) body.classList.remove("no-details");
  }
  function reveal(node) {
    for (let n = node.parent; n; n = n.parent) n.expanded = true;
    draw();
  }
  function focus(node, scale = Math.max(transform.scale, .8)) {
    transform = { scale, x: viewport.clientWidth * .35 - node.x * scale, y: viewport.clientHeight * .45 - (node.y + node.h / 2) * scale };
    apply();
  }

  // ------------------------------------------------------------ search
  let matches = [], matchIndex = -1, lastQuery = "";
  function search() {
    const query = $("player-search").value.trim();
    if (!query) return;
    if (query !== lastQuery) {
      lastQuery = query; matches = []; matchIndex = -1;
      // Breadth-first over the lazily built tree, opening branches as needed.
      const queue = [root]; let visited = 0;
      while (queue.length && visited < 6000) {
        const node = queue.shift(); visited++;
        if (node !== root && (node.title.includes(query) || (node.label || "").includes(query))) matches.push(node);
        if (expandable(node) && node.kind !== "ref") for (const child of children(node)) queue.push(child);
      }
    }
    if (!matches.length) { status.textContent = "未找到：" + query; return; }
    matchIndex = (matchIndex + 1) % matches.length;
    const node = matches[matchIndex];
    reveal(node); focus(node); select(node);
    status.textContent = `第 ${matchIndex + 1} / ${matches.length} 处：${query}`;
  }

  // ------------------------------------------------------------ scenario inputs
  function inputLabel(option) { return option.label ?? String(option.value); }
  const box = $("player-inputs");
  // Timers and table variables can be numerous; keep them in a sub-section.
  const extra = html("details", undefined, "player-inputs-extra"), extraBox = html("div", undefined, "player-inputs");
  extra.append(html("summary", "计时器与行为表变量"), extraBox);
  for (const [key, field] of Object.entries(view.inputs || {})) {
    if (!field.options?.length) continue;
    const target = field.group === "timer" || field.group === "variable" ? extraBox : box;
    const label = html("label"), select = html("select");
    label.append(field.label || key, select);
    select.append(new Option("任意", ""));
    field.options.forEach((option, index) => select.append(new Option(inputLabel(option), String(index))));
    select.onchange = () => {
      if (select.value === "") delete inputs[key];
      else inputs[key] = field.options[Number(select.value)].value;
      matches = []; lastQuery = "";
      build(); draw(); fit();
    };
    target.append(label);
  }
  if (extraBox.children.length) box.after(extra);
  if (!box.children.length && !extraBox.children.length) $("player-scenario").hidden = true;

  // ------------------------------------------------------------ toolbar & gestures
  function fit() {
    const scale = Math.min((viewport.clientWidth - 40) / extent.w, (viewport.clientHeight - 40) / extent.h, .9);
    transform = { x: 20, y: 20, scale: Math.max(scale, .05) }; apply();
  }
  $("player-search").addEventListener("keydown", event => { if (event.key === "Enter") search(); });
  $("player-search-next").onclick = search;
  $("player-expand").onclick = () => {
    const frontier = layout.filter(n => !n.expanded && expandable(n) && n.kind !== "action");
    for (const node of frontier.slice(0, 120)) node.expanded = true;
    draw();
  };
  $("player-collapse").onclick = () => { for (const node of layout) if (node !== root) node.expanded = false; draw(); fit(); };
  $("player-fit").onclick = fit;
  $("player-zoom-in").onclick = () => { transform.scale = Math.min(2.5, transform.scale * 1.2); apply(); };
  $("player-zoom-out").onclick = () => { transform.scale = Math.max(.03, transform.scale / 1.2); apply(); };
  $("player-details-toggle").onclick = () => body.classList.toggle("no-details");
  $("player-export").onclick = () => {
    const clone = canvas.cloneNode(true), group = clone.querySelector("g");
    group.setAttribute("transform", "translate(20 60)");
    clone.setAttribute("viewBox", `0 0 ${extent.w + 60} ${extent.h + 100}`);
    clone.setAttribute("width", extent.w + 60); clone.setAttribute("height", extent.h + 100);
    clone.prepend(svg("text", { x: 20, y: 30, "font-size": "18", fill: "#24344b" }, (graph.enemyName || graph.enemyId) + " · 行为决策树（当前展开部分）"));
    const style = [...document.styleSheets].flatMap(sheet => { try { return [...sheet.cssRules].map(r => r.cssText).filter(t => t.includes(".pt-")); } catch { return []; } }).join("\n");
    clone.prepend(svg("style", {}, style));
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml;charset=utf-8" }));
    const link = html("a"); link.href = url; link.download = graph.enemyId + ".tree.svg"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  let drag = null;
  viewport.addEventListener("pointerdown", event => {
    if (event.target.closest(".pt-node")) return;
    drag = { x: event.clientX, y: event.clientY, tx: transform.x, ty: transform.y };
    viewport.setPointerCapture(event.pointerId); viewport.classList.add("dragging");
  });
  viewport.addEventListener("pointermove", event => { if (drag) { transform.x = drag.tx + event.clientX - drag.x; transform.y = drag.ty + event.clientY - drag.y; apply(); } });
  viewport.addEventListener("pointerup", () => { drag = null; viewport.classList.remove("dragging"); });
  viewport.addEventListener("wheel", event => {
    event.preventDefault();
    const rect = viewport.getBoundingClientRect(), x = event.clientX - rect.left, y = event.clientY - rect.top;
    const scale = Math.max(.03, Math.min(2.5, transform.scale * (event.deltaY < 0 ? 1.12 : 1 / 1.12)));
    transform.x = x - (x - transform.x) * scale / transform.scale; transform.y = y - (y - transform.y) * scale / transform.scale; transform.scale = scale; apply();
  }, { passive: false });
  $("technical-toggle").onclick = () => {
    const technical = $("technical-panel"), showing = technical.hidden;
    technical.hidden = !showing; body.hidden = showing; $("player-scenario").hidden = showing || !box.children.length;
    $("technical-toggle").textContent = showing ? "返回决策树" : "技术图";
    if (showing) window.startTechnicalGraph();
  };

  build(); draw();
  const combat = layout.find(n => n.kind === "entry" && n.entry.slot === "COMBAT");
  if (combat) { focus(combat, .75); select(combat); } else fit();
})();
