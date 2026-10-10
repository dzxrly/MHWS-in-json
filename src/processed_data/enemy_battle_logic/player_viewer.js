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

  // Node widths follow their text per column; MIN_W/MAX_W bound a column.
  const MIN_W = 168, MAX_W = 320, PAD = 14, GAP_X = 190, GAP_Y = 12, LABEL_W = 150, MAX_LINES = 5;
  const INITIAL_BUDGET = 600, INITIAL_DEPTH = 10;
  const badges = { condition: "条件", weighted_random: "抽选", action: "动作", mutation: "状态变化", unknown: "待核查", return: "返回", loop: "循环", ref: "别处已展开" };
  const fontFamily = getComputedStyle(document.body).getPropertyValue("--font").trim() || "sans-serif";
  const fonts = {
    title: { font: `13px ${fontFamily}`, line: 18 },
    group: { font: `650 14px ${fontFamily}`, line: 20 },
    root: { font: `650 16px ${fontFamily}`, line: 22 },
    sub: { font: `11px ${fontFamily}`, line: 15 },
    badge: { font: `600 11px ${fontFamily}`, line: 16 },
    label: { font: `12px ${fontFamily}`, line: 16 },
  };

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
  // Text is measured with the page font, so wrapping holds for any installed font.
  const context = document.createElement("canvas").getContext("2d"), widths = new Map();
  function measure(text, font) {
    const key = font + "\u0000" + text;
    let width = widths.get(key);
    if (width === undefined) { context.font = font; width = context.measureText(text).width; widths.set(key, width); }
    return width;
  }
  function natural(text, font) {
    return text ? Math.max(...String(text).split("\n").map(part => measure(part, font))) : 0;
  }
  const HANGING = /^[，。、；：！？）】》」』”’,.;:!?)\]]$/;
  // Prefer a camel-case hump or underscore when an identifier must be cut.
  function cut(word, font, max) {
    let end = 1;
    while (end < word.length && measure(word.slice(0, end + 1), font) <= max) end++;
    for (let i = end; i > end * .4; i--) if (/[a-z0-9][A-Z]|_[^_]/.test(word.slice(i - 1, i + 1))) return i;
    return end;
  }
  function wrap(text, font, max, limit = Infinity) {
    const lines = [];
    for (const part of String(text).split("\n")) {
      let line = "";
      // Latin runs stay whole; CJK characters may break anywhere, and an
      // opening bracket stays with what follows it.
      for (let token of part.match(/[（【《「『“‘]*[!-~]+|\s+|[（【《「『“‘]*./gu) || []) {
        if (/^\s+$/.test(token)) { if (line) line += " "; continue; }
        if (measure(line + token, font) <= max || (line && HANGING.test(token))) { line += token; continue; }
        if (line.trim()) lines.push(line.trimEnd());
        while (measure(token, font) > max) {
          const at = cut(token, font, max);
          lines.push(token.slice(0, at)); token = token.slice(at);
        }
        line = token;
      }
      if (line.trim()) lines.push(line.trimEnd());
    }
    if (!lines.length) lines.push("");
    if (lines.length > limit) {
      lines.length = limit;
      let last = lines[limit - 1];
      while (last && measure(last + "…", font) > max) last = last.slice(0, -1);
      lines[limit - 1] = last + "…";
      lines.clipped = true;
    }
    return lines;
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
    if (node.compact) node.title = node.record?.checks || "内部检查";
    node.titleFont = fonts[kind === "root" ? "root" : kind === "group" ? "group" : "title"];
    node.badge = badgeText(node);
    const text = node.compact
      ? natural(node.badge, fonts.badge.font)
      : Math.max(natural(node.title, node.titleFont.font), natural(node.subtitle, fonts.sub.font), natural(node.badge, fonts.badge.font));
    node.natural = Math.min(MAX_W, Math.max(MIN_W, Math.ceil(text) + PAD * 2 + 4));
    return node;
  }
  function badgeText(node) {
    if (node.compact) {
      // Only unsettled checks reach the tree; name what they read.
      const subject = node.title.length > 22 ? node.title.slice(0, 21) + "…" : node.title;
      return "待核实 · " + subject;
    }
    if (node.kind === "root") return "";
    if (node.kind === "group") return "分组";
    if (node.kind === "entry") return node.entry.relation === "unknown" ? "局部分支" : "行为表";
    if (node.kind === "condition") {
      const category = node.record?.presentation?.category;
      return { distance: "距离", angle: "角度", state: "状态", phase: "状态" }[category] || badges.condition;
    }
    return badges[node.kind] || "流程";
  }
  // Wrap at the column width chosen by place(); height follows the line count.
  function measureNode(node, width) {
    node.w = width;
    const inner = width - PAD * 2 - 4;
    node.lines = node.compact ? [] : wrap(node.title, node.titleFont.font, inner, MAX_LINES);
    node.subLines = node.subtitle && !node.compact ? wrap(node.subtitle, fonts.sub.font, inner, 3) : [];
    node.h = node.compact ? 30
      : 10 + (node.badge ? fonts.badge.line + 2 : 2) + node.lines.length * node.titleFont.line
        + (node.subLines.length ? 3 + node.subLines.length * fonts.sub.line : 0) + 10;
  }
  function recordNode(state, label, parent, extra = {}) {
    const { key, record: rec } = record(state);
    const kind = rec.kind;
    if (shown.has(key)) {
      return make("ref", rec.presentation?.title || rec.title, { label, parent, refKey: key, record: rec, state, ...extra });
    }
    // Actions without a reviewed explanation are titled by their ActionID class.
    const subtitle = kind !== "action" ? undefined : rec.nameStatus === "unresolved" ? "暂无中文名" : rec.technicalName;
    const node = make(kind, rec.presentation?.title || rec.title, { label, parent, record: rec, state, stateKey: key, subtitle, ...extra });
    shown.set(key, node);
    return node;
  }
  // Internal checks stay as small nodes: folding them would multiply edges
  // for every unresolved check, while a node per check keeps growth linear.
  function project(rec, parent) {
    return rec.children.map(child => {
      const { record: target } = record(child.state);
      let label = child.label;
      if (target.via?.some(n => n.kind === "mutation")) label += "\n（状态更新后）";
      return recordNode(child.state, label, parent, { role: child.role || (child.slot ? "random" : "next") });
    });
  }
  function requestedBy(entry) {
    const names = entry.requestedBy || [];
    if (!names.length) return entry.relation === "unknown" ? "接入位置待核查" : "";
    return "由 " + names.slice(0, 2).join("、") + (names.length > 2 ? ` 等 ${names.length} 个状态` : "") + "切入";
  }
  function children(node) {
    if (node.children) return node.children;
    if (node.kind === "root") node.children = groups.map(g => make("group", g.name, { parent: node, group: g, subtitle: g.entries.length + " 张行为表" }));
    // The badge and subtitle already say "local branch, entry unverified".
    else if (node.kind === "group") node.children = node.group.entries.map(entry => make("entry", entry.relation === "unknown" ? entry.label.replace(/^局部分支：/, "").replace(/（接入待核查）$/, "") : entry.label, { parent: node, entry, subtitle: requestedBy(entry) }));
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
    root = make("root", graph.enemyName || graph.enemyId, { subtitle: view.entries.length + " 个行为表入口" });
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
    // Every visible node in a column shares the widest natural width there.
    const columns = [];
    (function collect(node, depth) {
      node.depth = depth;
      columns[depth] = Math.max(columns[depth] || 0, node.natural);
      if (node.expanded) for (const child of children(node)) collect(child, depth + 1);
    })(root, 0);
    const lefts = [0];
    for (let i = 1; i < columns.length; i++) lefts[i] = lefts[i - 1] + columns[i - 1] + GAP_X;
    let cursor = 0;
    const bottoms = [];
    function visit(node, depth) {
      measureNode(node, columns[depth]);
      node.x = lefts[depth];
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
      bottoms[node.depth] = Math.max(bottoms[node.depth] ?? -Infinity, node.y + node.h + GAP_Y);
    }
    visit(root, 0);
    extent = { w: Math.max(...layout.map(n => n.x + n.w)), h: Math.max(...layout.map(n => n.y + n.h)) };
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
      const p = node.parent, x1 = p.x + p.w + 10, y1 = p.y + p.h / 2, x2 = node.x, y2 = node.y + node.h / 2, mid = x1 + 22;
      const group = svg("g", { class: `pt-edge ${node.role || ""} ${node.uncertain ? "uncertain" : ""}` });
      const bend = Math.min(10, Math.abs(y2 - y1) / 2), down = y2 >= y1 ? 1 : -1;
      group.append(svg("path", { d: y2 === y1 ? `M${x1},${y1} H${x2 - 6}` : `M${x1},${y1} H${mid - bend} Q${mid},${y1} ${mid},${y1 + bend * down} V${y2 - bend * down} Q${mid},${y2} ${mid + bend},${y2} H${x2 - 6}` }));
      if (node.label) {
        const line = fonts.label.line, lines = wrap(node.label, fonts.label.font, LABEL_W, 3);
        const text = svg("text", { x: x2 - 10, y: y2 - (lines.length - 1) * line / 2 - 4 });
        lines.forEach((part, i) => text.append(svg("tspan", { x: x2 - 10, dy: i ? line : 0 }, part)));
        if (lines.clipped) text.append(svg("title", {}, node.label));
        group.append(text);
      }
      edges.append(group);
    }
    for (const node of layout) nodes.append(drawNode(node));
    status.textContent = `显示 ${layout.length} 个节点`;
    panel.dataset.ready = "true"; panel.dataset.nodes = String(layout.length);
    apply();
  }
  function drawNode(node) {
    const kind = node.compact ? "compact" : node.kind;
    const g = svg("g", { class: `pt-node k-${kind}` + (node === selected ? " selected" : "") + (matches.includes(node) && matches[matchIndex] === node ? " match" : ""), transform: `translate(${node.x} ${node.y})`, tabindex: "0", role: "button", "aria-label": node.title, "data-uid": node.uid, "data-kind": node.kind });
    g.append(svg("rect", { class: "box", width: node.w, height: node.h, rx: 8 }));
    if (node.kind !== "root") g.append(svg("rect", { class: "stripe", x: 0, y: 6, width: 3, height: Math.max(0, node.h - 12), rx: 1.5 }));
    let y = 10;
    if (node.badge) {
      g.append(svg("text", { x: PAD, y: y + 11, class: "badge" }, node.badge));
      y += fonts.badge.line + 2;
    } else y += 2;
    if (node.lines.length && node.lines[0]) {
      const line = node.titleFont.line, text = svg("text", { x: PAD, y: y + line * .72, class: "title" });
      node.lines.forEach((part, i) => text.append(svg("tspan", { x: PAD, dy: i ? line : 0 }, part)));
      g.append(text);
      y += node.lines.length * line;
    }
    if (node.subLines.length) {
      const line = fonts.sub.line, text = svg("text", { x: PAD, y: y + 3 + line * .72, class: "sub" });
      node.subLines.forEach((part, i) => text.append(svg("tspan", { x: PAD, dy: i ? line : 0 }, part)));
      g.append(text);
    }
    if (node.compact || node.lines.clipped || node.subLines.clipped) g.append(svg("title", {}, [node.title, node.subtitle].filter(Boolean).join("\n")));
    if (expandable(node)) {
      const t = svg("g", { class: "pt-toggle", transform: `translate(${node.w} ${node.h / 2})`, role: "button", "aria-label": node.expanded ? "收起分支" : "展开分支" });
      t.append(svg("circle", { r: 10 }), svg("text", { y: 4.5 }, node.expanded ? "−" : "+"));
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
    selection.className = "selection k-" + (node.compact ? "compact" : node.kind);
    selection.replaceChildren();
    if (node.badge) selection.append(html("div", node.badge, "kind"));
    selection.append(html("h3", node.title));
    if (node.subtitle) selection.append(html("p", node.subtitle, "sub"));
    const rec = node.record;
    const note = text => selection.append(html("p", text, "note"));
    if (node.kind === "entry" && node.entry.note) note(node.entry.note);
    if (node.kind === "ref") {
      const button = html("button", "跳到首次展开处");
      button.onclick = () => { const target = shown.get(node.refKey); if (target) { reveal(target); focus(target); select(target); } };
      note("同一判断已在树的其他位置展开，这里不再重复。");
      selection.append(button);
    }
    if (rec) {
      if (rec.kind === "action" && rec.nameStatus === "unresolved") note("游戏资源里没有这个动作的中文名，标题直接用 ActionID 的类名；同一类有多套参数时用“分支参数 n”区分。");
      if (rec.presentation?.compact) note("这个内部检查会影响分支走向，但它读取的状态还没核实或无法由当前设定判断，所以两条分支都保留。");
      const checks = (rec.via || []).filter(n => n.kind === "check");
      if (checks.length) {
        const passed = html("details"), list = html("ul");
        passed.append(html("summary", `途经的内部检查（${checks.length} 个，按当前设定已确定）`), list);
        for (const check of checks) list.append(html("li", `${check.title}：${check.truth ? "成立" : "不成立"}`));
        selection.append(passed);
      }
      if (rec.afterAction) note("这里位于动作或状态变化之后，条件会重新判断。");
      if (rec.kind === "weighted_random") note("权重只在本次抽选的候选之间比较。");
    }
    const steps = path(node).slice(1).map(n => n.label ? `${n.label.split("\n")[0]} → ${n.title}` : n.title);
    if (steps.length > 1) {
      const route = html("details"), list = html("ol");
      route.append(html("summary", `从怪物到这里（${steps.length} 步）`), list);
      for (const step of steps) list.append(html("li", step));
      selection.append(route);
    }
    if (rec) {
      const details = html("details"), summary = html("summary", "原始数据");
      details.append(summary);
      details.addEventListener("toggle", () => {
        if (!details.open || details.querySelector("pre")) return;
        const refs = [...new Set([...(rec.via || []).map(n => n.sourceRef), rec.sourceRef])];
        details.append(html("pre", JSON.stringify({ path: refs.map(ref => ({ ref, node: sources.get(ref)?.node, evidence: sources.get(ref)?.table.evidence })), profile: graph.profile }, null, 2)));
      });
      selection.append(details);
    }
    if (body.classList.contains("no-details")) setDetails(true);
  }
  function reveal(node) {
    for (let n = node.parent; n; n = n.parent) n.expanded = true;
    draw();
  }
  function focus(node, scale = Math.max(transform.scale, 1)) {
    transform = { scale, x: viewport.clientWidth * (viewport.clientWidth < 600 ? .06 : .35) - node.x * scale, y: viewport.clientHeight * .45 - (node.y + node.h / 2) * scale };
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
        if (node !== root && [node.title, node.label, node.subtitle].some(text => (text || "").toLowerCase().includes(query.toLowerCase()))) matches.push(node);
        if (expandable(node) && node.kind !== "ref") for (const child of children(node)) queue.push(child);
      }
    }
    if (!matches.length) { status.textContent = "没有找到“" + query + "”"; return; }
    matchIndex = (matchIndex + 1) % matches.length;
    const node = matches[matchIndex];
    reveal(node); focus(node); select(node);
    status.textContent = `第 ${matchIndex + 1} / ${matches.length} 处`;
  }

  // ------------------------------------------------------------ scenario inputs
  function inputLabel(option) { return option.label ?? String(option.value); }
  const box = $("player-inputs");
  // Timers and table variables can be numerous; keep them in a sub-section.
  const extra = html("details", undefined, "inputs-extra"), extraBox = html("div", undefined, "inputs");
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
  function setDetails(open) {
    body.classList.toggle("no-details", !open);
    $("player-details-toggle").setAttribute("aria-pressed", String(open));
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
  function zoom(factor, x = viewport.clientWidth / 2, y = viewport.clientHeight / 2) {
    const scale = Math.max(.03, Math.min(2.5, transform.scale * factor));
    transform.x = x - (x - transform.x) * scale / transform.scale; transform.y = y - (y - transform.y) * scale / transform.scale; transform.scale = scale; apply();
  }
  $("player-zoom-in").onclick = () => zoom(1.2);
  $("player-zoom-out").onclick = () => zoom(1 / 1.2);
  $("player-details-toggle").onclick = () => setDetails(body.classList.contains("no-details"));
  setDetails(true);
  $("player-export").onclick = () => {
    const clone = canvas.cloneNode(true), group = clone.querySelector("g");
    group.setAttribute("transform", "translate(20 60)");
    clone.setAttribute("viewBox", `0 0 ${extent.w + 60} ${extent.h + 100}`);
    clone.setAttribute("width", extent.w + 60); clone.setAttribute("height", extent.h + 100);
    clone.prepend(svg("text", { x: 20, y: 30, "font-size": "18", fill: "currentColor", "font-family": fontFamily }, (graph.enemyName || graph.enemyId) + " · 行动决策树（当前展开部分）"));
    // Carry the colour tokens along with the tree rules into the standalone file.
    const style = [...document.styleSheets].flatMap(sheet => { try { return [...sheet.cssRules].map(r => r.cssText).filter(t => /\.pt-|\.k-|:root/.test(t)); } catch { return []; } }).join("\n");
    clone.prepend(svg("style", {}, style + "\nsvg { background: var(--canvas); color: var(--ink); }"));
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
    const rect = viewport.getBoundingClientRect();
    zoom(event.deltaY < 0 ? 1.12 : 1 / 1.12, event.clientX - rect.left, event.clientY - rect.top);
  }, { passive: false });
  function technical(showing) {
    $("technical-panel").hidden = !showing; panel.hidden = showing;
    if (showing) window.startTechnicalGraph();
  }
  $("technical-toggle").onclick = () => technical(true);
  $("technical-back").hidden = false;
  $("technical-back").onclick = () => technical(false);

  build(); draw();
  const combat = layout.find(n => n.kind === "entry" && n.entry.slot === "COMBAT");
  if (combat) { focus(combat, 1); select(combat); } else fit();
})();
