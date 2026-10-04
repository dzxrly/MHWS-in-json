/* Render the SDK's declared conditions and continuations as a branch tree. */
(function () {
  "use strict";
  const { graph } = JSON.parse(document.getElementById("data").textContent);
  const view = graph.playerView, panel = document.getElementById("player-panel");
  if (!view) { panel.hidden = true; window.startTechnicalGraph(); return; }
  const engine = window.BattlePlayer, ns = "http://www.w3.org/2000/svg";
  const sources = new Map();
  for (const table of graph.tables) for (const node of table.nodes) sources.set(`${table.tableGuid}/${node.id}`, { table, node });
  function html(tag, text, className) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (className) e.className = className;
    return e;
  }
  function svgElement(tag, attrs, text) {
    const e = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attrs || {})) e.setAttribute(key, value);
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function lines(text, width = 15) {
    const result = [];
    for (const word of String(text).split("\n")) {
      let line = "", used = 0;
      for (const char of word) {
        const size = char.codePointAt(0) > 255 ? 1 : .55;
        if (used + size > width && line) { result.push(line); line = ""; used = 0; }
        line += char; used += size;
      }
      if (line) result.push(line);
    }
    return result;
  }
  function textLines(parent, text, x, y, width, attributes = {}) {
    const textNode = svgElement("text", { x, y, ...attributes });
    lines(text, width).forEach((line, i) => textNode.append(svgElement("tspan", { x, dy: i ? 18 : 0 }, line)));
    parent.append(textNode);
  }
  function sourceDetails(record, target) {
    target.replaceChildren();
    target.append(html("h3", record.presentation?.title || record.title));
    if (record.presentation?.compact) target.append(html("p", "此检查会影响分支选择，具体内部条件仍需核查。"));
    if (record.via.some(n => n.kind === "mutation")) target.append(html("p", "到达此节点前有状态写入；展开依据可查看被压缩的路径。"));
    if (record.afterAction) target.append(html("p", "动作或状态变化后，这里的条件需要重新判断。"));
    const details = html("details"), summary = html("summary", "原始判断、调用路径与证据"); details.append(summary);
    details.addEventListener("toggle", () => {
      if (!details.open || details.querySelector("pre")) return;
      const refs = [...new Set([...(record.trail || []).map(n => n.sourceRef), ...record.via.map(n => n.sourceRef), record.sourceRef])];
      details.append(html("pre", JSON.stringify({ upstreamBranches: record.trail || [], path: refs.map(ref => ({ ref, node: sources.get(ref)?.node, evidence: sources.get(ref)?.table.evidence })), profile: graph.profile }, null, 2)));
    });
    target.append(details);
  }
  const fills = { condition: "#edf7f0", action: "#e8f2fc", weighted_random: "#fff6de", mutation: "#f3eefb", unknown: "#fff0e7", return: "#f0f3f7", loop: "#f0f3f7" };
  function createTree(entry, mount, initialDepth = 8) {
    const toolbar = html("div", undefined, "player-map-toolbar"), viewport = html("div", undefined, "player-tree-viewport");
    const canvas = svgElement("svg", { role: "img", "aria-label": entry.label + "：距离、角度与动作分支树" });
    const context = html("p", undefined, "player-note player-branch-context");
    const scene = svgElement("g"), detail = html("aside", undefined, "player-selection"), status = html("output");
    const button = (label, action) => { const e = html("button", label); e.onclick = action; toolbar.append(e); return e; };
    viewport.append(canvas); canvas.append(scene); mount.append(toolbar, context, viewport, detail);
    const nodes = new Map(), pending = [], interned = new Map();
    let layout, run = 0, selected = null, transform = { x: 24, y: 24, scale: .85 }, drag;
    function apply() { scene.setAttribute("transform", `translate(${transform.x} ${transform.y}) scale(${transform.scale})`); }
    function stateKey(state) { return JSON.stringify([state.key, state.stack, state.afterAction, state.inputs, Object.entries(state.assumptions).sort()]); }
    function intern(state) {
      const key = stateKey(state);
      if (interned.has(key)) return interned.get(key);
      const record = engine.step(view, { ...state, seen: [] });
      const id = "p" + nodes.size, compact = record.presentation?.compact;
      const title = record.presentation?.title || record.title;
      const node = { id, record, state, title, width: compact ? 148 : 218, height: 42 + lines(title, compact ? 10 : 15).length * 18 + (record.children.length ? 24 : 0), children: null };
      interned.set(key, id); nodes.set(id, node); return id;
    }
    const rootId = intern(engine.initial(view, entry, {}));
    let scopeRoot = rootId;
    function grow(start, depth, includeAction = false) {
      pending.push({ id: start, depth, includeAction });
      let added = 0;
      while (pending.length && added < 250) {
        const item = pending.shift(), node = nodes.get(item.id);
        if (node.children !== null || !node.record.children.length) continue;
        if ((node.record.kind === "action" || node.record.children.some(child => child.role === "resume")) && !item.includeAction) continue;
        const nextDepth = item.depth - (node.record.presentation?.compact ? 0 : 1);
        if (item.depth <= 0 && !node.record.presentation?.compact) continue;
        node.children = node.record.children.map((child, index) => {
          const state = { ...child.state, trail: [...(node.state.trail || []), { label: child.label, category: node.record.presentation?.category || node.record.kind, sourceRef: node.record.sourceRef }] };
          return { ...child, id: intern(state), edgeId: `${node.id}:${index}` };
        });
        added++;
        for (const child of node.children) pending.push({ id: child.id, depth: nextDepth, includeAction: false });
      }
      pending.length = 0;
    }
    grow(rootId, initialDepth);
    function subtree(start) {
      const ids = new Set(), todo = [start];
      while (todo.length) { const id = todo.pop(); if (ids.has(id)) continue; ids.add(id); for (const child of nodes.get(id).children || []) todo.push(child.id); }
      return ids;
    }
    function preferredBranch() {
      const visible = new Set(layout.children.map(node => node.id)), next = new Map();
      for (const edge of layout.edges) {
        const id = edge.sources[0];
        if (!next.has(id)) next.set(id, []);
        next.get(id).push(edge.targets[0]);
      }
      let best = rootId, score = -1;
      for (const node of nodes.values()) {
        const category = node.record.presentation?.category;
        if (!visible.has(node.id) || !["distance", "angle"].includes(category)) continue;
        const reached = new Set(), pending = [{ id: node.id, depth: 0 }];
        let nearest = Infinity, actions = 0, otherSpatial = 0;
        while (pending.length) {
          const item = pending.shift(); if (reached.has(item.id)) continue; reached.add(item.id);
          const target = nodes.get(item.id), targetCategory = target.record.presentation?.category;
          if (["distance", "angle"].includes(targetCategory) && targetCategory !== category) otherSpatial++;
          if (target.record.kind === "action" && target.record.nameStatus !== "unresolved") { actions++; nearest = Math.min(nearest, item.depth); }
          if (item.depth < 3) for (const id of next.get(item.id) || []) pending.push({ id, depth: item.depth + 1 });
        }
        const value = actions ? 1000 - nearest * 150 + Math.min(actions, 2) * 20 + Math.min(otherSpatial, 2) * 100 - reached.size : 0;
        if (value > score) { score = value; best = node.id; }
      }
      return best;
    }
    function focus(id, scale = .85) {
      if (!layout) return;
      const p = layout.children.find(n => n.id === id); if (!p) return;
      transform = { scale, x: 35 - p.x * scale, y: Math.max(28, viewport.clientHeight * .3 - p.height * scale / 2) - p.y * scale }; apply();
    }
    function select(id) {
      selected = id; sourceDetails({ ...nodes.get(id).record, trail: nodes.get(id).state.trail }, detail);
      const trail = nodes.get(id).state.trail || [], meaningful = trail.filter(n => n.category !== "internal");
      context.textContent = "树中同时保留各条件分支。当前定位分支的上游路径：" + (meaningful.map(n => n.label).join(" → ") || "已恢复的战斗入口") + (trail.length > meaningful.length ? `；另有 ${trail.length - meaningful.length} 项内部检查，原始路径保留在详情中。` : "");
      scene.querySelectorAll(".player-svg-node").forEach(n => n.classList.toggle("selected", n.dataset.id === id));
    }
    function exportSvg() {
      if (!layout) return;
      const clone = canvas.cloneNode(true), group = clone.querySelector("g"); group.removeAttribute("transform");
      group.setAttribute("transform", "translate(0 72)");
      clone.setAttribute("viewBox", `-20 -20 ${layout.width + 40} ${layout.height + 120}`);
      clone.setAttribute("width", layout.width + 40); clone.setAttribute("height", layout.height + 120); clone.setAttribute("xmlns", ns);
      clone.prepend(svgElement("text", { x: 0, y: 16, "font-size": "18", fill: "#24344b" }, (graph.enemyName || graph.enemyId) + " · " + entry.label));
      clone.insertBefore(svgElement("text", { x: 0, y: 42, "font-size": "12", fill: "#627188" }, "距离为游戏判断值；动作请求不保证成功执行；＋ 表示后续未展开；未知接入不补线。"), group);
      const style = svgElement("style", {}, ".player-svg-node text{font-family:system-ui,Microsoft YaHei,sans-serif;fill:#24344b;font-size:13px}.player-svg-node .player-badge{font-size:10px;fill:#667c90}.player-svg-edge text{font-family:system-ui,Microsoft YaHei,sans-serif;font-size:12px;fill:#415c72}.player-svg-node.selected rect{stroke:#3476b8;stroke-width:3}"); clone.prepend(style);
      const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml;charset=utf-8" }));
      const link = html("a"); link.href = url; link.download = graph.enemyId + "." + (entry.relation === "unknown" ? "local-" + view.entries.indexOf(entry) : "battle") + ".tree.svg"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    async function draw(resetFocus = false) {
      const ticket = ++run; status.textContent = "正在排列行动分支…"; mount.dataset.ready = "false";
      const visible = subtree(scopeRoot), scoped = new Map(), projectedEdges = [], todo = [scopeRoot];
      // Compact SDK-marked internal checks into conditional paths, preserving
      // both outcomes and the exact list of checks behind each projected edge.
      function project(source, child) {
        const pending = [{ id: child.id, path: [] }], visited = new Set(), endpoints = new Map(), foldedGraph = [];
        while (pending.length) {
          const item = pending.pop(); if (visited.has(item.id)) continue; visited.add(item.id);
          const target = nodes.get(item.id);
          if (target.record.presentation?.compact && target.children !== null && target.id !== scopeRoot && item.path.length < 64) {
            foldedGraph.push({ id: target.id, sourceRef: target.record.sourceRef, via: target.record.via, stack: target.state.stack, children: target.children.map(branch => ({ target: branch.id, role: branch.role, label: branch.label })) });
            for (const branch of target.children) pending.push({ id: branch.id, path: [...item.path, { sourceRef: target.record.sourceRef, role: branch.role, label: branch.label, via: target.record.via }] });
          } else endpoints.set(target.id, item.path);
        }
        // A closed internal cycle remains an explicit boundary in the drawing.
        if (!endpoints.size) endpoints.set(child.id, []);
        for (const [id, folded] of endpoints) { projectedEdges.push({ source, child: { ...child, id, edgeId: child.edgeId + "/" + id }, folded, foldedGraph }); todo.push(id); }
      }
      while (todo.length) {
        const id = todo.pop(); if (scoped.has(id)) continue;
        const node = nodes.get(id); scoped.set(id, node);
        for (const child of node.children || []) project(id, child);
      }
      const trail = nodes.get(scopeRoot).state.trail || [];
      const meaningful = trail.filter(n => n.category !== "internal");
      const internal = trail.length - meaningful.length;
      context.textContent = scopeRoot === rootId ? "从已恢复的入口展示全部上游分支。" : "当前距离 / 角度分支的上游路径：" + (meaningful.map(n => n.label).join(" → ") || "普通战斗入口") + (internal ? `；另有 ${internal} 项内部检查，详情中保留原始路径。` : "") + " 可用“上游入口与其他分支”查看其他路径。";
      const edges = [];
      for (const { source, child, folded, foldedGraph } of projectedEdges) {
        const node = nodes.get(source);
        let label = child.label;
        if (folded.length) label += "\n还有内部状态条件";
        const target = nodes.get(child.id);
        if (target.record.via.some(n => n.kind === "mutation")) label += "\n状态更新后继续";
        const labelLines = lines(label, 14);
        edges.push({ id: child.edgeId, sources: [node.id], targets: [child.id], labels: [{ text: label, width: Math.min(210, Math.max(76, Math.max(...labelLines.map(s => s.length)) * 12)), height: labelLines.length * 18 + 8 }], role: child.role, slot: child.slot, folded, foldedGraph });
      }
      try {
        const result = await new ELK().layout({ id: "player-tree", layoutOptions: { "elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.edgeRouting": "ORTHOGONAL", "elk.layered.spacing.nodeNodeBetweenLayers": "70", "elk.spacing.nodeNode": "24", "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX", "elk.layered.crossingMinimization.forceNodeModelOrder": "true" }, children: [...scoped.values()].map(n => ({ id: n.id, width: n.width, height: n.height })), edges });
        if (ticket !== run) return; layout = result; scene.replaceChildren();
        for (const edge of layout.edges) {
          const group = svgElement("g", { class: "player-svg-edge", "data-slot": edge.slot || "", "data-role": edge.role || "next", "data-folded": JSON.stringify(edge.folded), "data-source": nodes.get(edge.sources[0]).record.sourceRef, "data-target": nodes.get(edge.targets[0]).record.sourceRef });
          group.onclick = () => { sourceDetails({ title: "分支条件与被压缩的路径", via: edge.foldedGraph.flatMap(n => [...n.via, { sourceRef: n.sourceRef }]), sourceRef: nodes.get(edge.targets[0]).record.sourceRef, trail: nodes.get(edge.targets[0]).state.trail || [] }, detail); const branches = html("details"); branches.append(html("summary", "全部内部条件分支")); branches.append(html("pre", JSON.stringify(edge.foldedGraph, null, 2))); detail.append(branches); };
          for (const section of edge.sections || []) {
            const points = [section.startPoint, ...(section.bendPoints || []), section.endPoint];
            group.append(svgElement("path", { d: points.map((p, i) => `${i ? "L" : "M"}${p.x},${p.y}`).join(" "), fill: "none", stroke: edge.role === "false" ? "#ae7777" : edge.role === "resume" ? "#9479ad" : "#91a9bc", "stroke-width": "1.8", ...(edge.role === "resume" ? { "stroke-dasharray": "6 4" } : {}) }));
          }
          for (const label of edge.labels || []) textLines(group, label.text, label.x + 4, label.y + 15, 14, { "font-size": "12", fill: "#415c72", "paint-order": "stroke", stroke: "#fff", "stroke-width": "4" });
          scene.append(group);
        }
        const badges = { condition: "条件判断", weighted_random: "候选选择", action: "动作请求", mutation: "战斗流程变化", unknown: "逻辑待核查", return: "返回 / 本轮结束", loop: "返回此前判断" };
        for (const p of layout.children) {
          const node = nodes.get(p.id), record = node.record;
          const group = svgElement("g", { class: "player-svg-node", transform: `translate(${p.x} ${p.y})`, "data-id": p.id, "data-source": record.sourceRef, "data-category": record.presentation?.category || record.kind, tabindex: "0", role: "button", "aria-label": node.title });
          group.append(svgElement("rect", { width: node.width, height: node.height, rx: 9, fill: record.presentation?.compact ? "#f1f3f6" : fills[record.kind] || "#f1f3f6", stroke: "#bdcddb", "stroke-width": "1.4" }));
          textLines(group, record.presentation?.compact ? "内部检查 · 分支保留" : badges[record.kind] || "流程", 12, 17, 22, { class: "player-badge", "font-size": "10", fill: "#667c90" });
          textLines(group, node.title, 12, 38, record.presentation?.compact ? 10 : 15, { "font-size": "13", fill: "#24344b" });
          if (node.children === null && record.children.length) {
            const expand = svgElement("g", { class: "player-svg-expand", role: "button", tabindex: "0", "aria-label": record.kind === "action" ? "展开动作请求后的继续流程" : "展开后续条件分支" });
            expand.append(svgElement("rect", { x: 8, y: node.height - 27, width: node.width - 16, height: 21, rx: 4, fill: "#fff", stroke: "#cad6e1" }));
            expand.append(svgElement("text", { x: 14, y: node.height - 12, "font-size": "11", fill: "#3476b8" }, record.kind === "action" ? "＋ 动作后的继续流程" : "＋ 后续条件与动作"));
            const expandNode = event => { event.stopPropagation(); grow(p.id, 4, true); draw(); };
            expand.onclick = expandNode; expand.onkeydown = event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); expandNode(event); } }; group.append(expand);
          }
          group.onclick = () => select(p.id); group.onkeydown = event => { if (event.key === "Enter") select(p.id); }; scene.append(group);
        }
        status.textContent = "分支线直接标注条件 · 点击节点查看依据";
        mount.dataset.ready = "true"; mount.dataset.nodes = String(scoped.size);
        mount.dataset.spatial = String([...scoped.values()].filter(n => ["distance", "angle"].includes(n.record.presentation?.category)).length);
        if (resetFocus) {
          const preferred = preferredBranch(); focus(preferred, .8); select(preferred);
        } else apply(); if (selected) select(selected);
      } catch (error) { status.textContent = "树状图排列失败：" + error.message; mount.dataset.error = error.message; }
    }
    button("上游入口与其他分支", () => { scopeRoot = rootId; selected = null; draw().then(() => focus(rootId)); });
    button("距离 / 角度分支", () => {
      const spatial = [...nodes.values()].filter(n => ["distance", "angle"].includes(n.record.presentation?.category));
      const at = spatial.findIndex(n => n.id === selected), node = spatial[(at + 1) % spatial.length];
      if (node) { select(node.id); focus(node.id, .8); }
    });
    button("全图", () => { if (layout) { const scale = Math.min((viewport.clientWidth - 40) / layout.width, (viewport.clientHeight - 40) / layout.height, 1); transform = { x: 20, y: 20, scale }; apply(); } });
    button("＋", () => { transform.scale = Math.min(2, transform.scale * 1.2); apply(); });
    button("－", () => { transform.scale = Math.max(.03, transform.scale / 1.2); apply(); });
    button("展开下一层", () => { const frontier = [...nodes.values()].filter(n => n.children === null && n.record.kind !== "action"); for (const n of frontier.slice(0, 80)) grow(n.id, 1); draw(); });
    button("导出这棵树 SVG", exportSvg); toolbar.append(status);
    viewport.onpointerdown = event => { if (event.target.closest(".player-svg-node")) return; drag = { x: event.clientX, y: event.clientY, tx: transform.x, ty: transform.y }; viewport.setPointerCapture(event.pointerId); };
    viewport.onpointermove = event => { if (drag) { transform.x = drag.tx + event.clientX - drag.x; transform.y = drag.ty + event.clientY - drag.y; apply(); } };
    viewport.onpointerup = () => { drag = null; };
    viewport.addEventListener("wheel", event => { event.preventDefault(); const rect = viewport.getBoundingClientRect(), x = event.clientX - rect.left, y = event.clientY - rect.top, scale = Math.max(.03, Math.min(2, transform.scale * (event.deltaY < 0 ? 1.12 : 1 / 1.12))); transform.x = x - (x - transform.x) * scale / transform.scale; transform.y = y - (y - transform.y) * scale / transform.scale; transform.scale = scale; apply(); }, { passive: false });
    draw(true);
  }
  const main = document.getElementById("player-tree"), mainEntry = view.entries[0];
  main.append(html("h3", mainEntry.label), html("p", mainEntry.note, "player-note")); createTree(mainEntry, main);
  const unattached = document.getElementById("player-unattached");
  function hasSpatialCondition(entry) {
    const seen = new Set(), pending = [entry.id];
    while (pending.length) {
      const id = pending.pop(); if (seen.has(id)) continue; seen.add(id);
      const node = view.nodes[id];
      if (["distance", "angle"].includes(node.presentation?.category)) return true;
      if (node.kind === "action") continue;
      for (const role of ["true", "false", "next", "target", "resume", "fallback", "dispatch"]) if (node[role]) pending.push(node[role]);
      for (const candidate of node.candidates || []) pending.push(candidate.target);
    }
    return false;
  }
  if (view.entries.length > 1) {
    unattached.append(html("h3", "接入位置待核查的分支树"), html("p", "下面保留已恢复的局部判断和动作。它们与上方战斗入口的连接尚未核实，因此没有绘制接入线。", "player-note"));
    let revealLocal = view.coverage.connectedActions === 0;
    for (const entry of view.entries.slice(1)) {
      const details = html("details", undefined, "player-local-tree"), summary = html("summary", entry.label); details.append(summary);
      const mount = html("div"); details.append(mount); unattached.append(details);
      let made = false;
      details.addEventListener("toggle", () => { if (details.open && !made) { made = true; createTree(entry, mount, 5); } });
      if (entry.label.startsWith("普通攻击局部入口")) details.open = true;
      if (revealLocal && hasSpatialCondition(entry)) { details.open = true; revealLocal = false; }
    }
  }
  document.getElementById("technical-toggle").onclick = () => {
    const technical = document.getElementById("technical-panel"); technical.hidden = !technical.hidden;
    document.getElementById("technical-toggle").textContent = technical.hidden ? "查看完整技术图" : "收起完整技术图";
    if (!technical.hidden) { window.startTechnicalGraph(); technical.scrollIntoView({ behavior: "smooth", block: "start" }); }
  };
})();
