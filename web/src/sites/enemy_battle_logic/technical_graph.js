/* The behaviour tables' original flow, laid out by ELK, for checking against the data. */
const ROLES = ["true", "false", "next", "resume", "call", "dispatch", "random", "fallback"];

function element(tag, attributes = {}, text = null) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  if (text !== null) node.textContent = text;
  return node;
}

/**
 * Lay out `diagram` in `scene` (inside `svg`, inside `viewport`) with a
 * minimap in `mini`. `onStatus(text | null)`, `onZoom(percent)` and
 * `onInspect(info)` report back to the page.
 */
export function createTechnicalGraph({ graph, diagram, viewport, svg, scene, mini, onStatus, onZoom, onInspect }) {
  if (graph.playerView) {
    const tables = new Map(graph.tables.map(table => [table.tableGuid, table]));
    for (const detail of Object.values(diagram.details)) {
      const table = tables.get(detail.tableGuid);
      detail.node = table.nodes.find(node => node.id === detail.localId);
      detail.tableEvidence = table.evidence;
    }
  }
  const nodes = new Map(), groups = new Map();
  let layout = null,
    transform = { x: 0, y: 0, scale: 1 },
    selectedId = null,
    drag = null,
    moving = false,
    layoutRun = 0,
    direction = "DOWN";

  function apply() {
    scene.setAttribute("transform", `translate(${transform.x},${transform.y}) scale(${transform.scale})`);
    onZoom(Math.round(transform.scale * 100));
    const rect = mini.querySelector(".mini-view");
    if (rect) {
      rect.setAttribute("x", -transform.x / transform.scale);
      rect.setAttribute("y", -transform.y / transform.scale);
      rect.setAttribute("width", viewport.clientWidth / transform.scale);
      rect.setAttribute("height", viewport.clientHeight / transform.scale);
    }
  }
  function fitBox(box) {
    const width = viewport.clientWidth, height = viewport.clientHeight;
    transform.scale = Math.min(1.3, (width - 90) / box.width, (height - 90) / box.height);
    transform.x = (width - box.width * transform.scale) / 2 - box.x * transform.scale;
    transform.y = (height - box.height * transform.scale) / 2 - box.y * transform.scale;
    apply();
  }
  function focus(id) {
    const node = nodes.get(id);
    if (!node) return;
    transform.scale = 0.85;
    transform.x = viewport.clientWidth * 0.28 - (node.x + node.width / 2) * transform.scale;
    transform.y = viewport.clientHeight / 2 - (node.y + node.height / 2) * transform.scale;
    apply();
    inspect(id);
  }
  function zoom(factor, x = viewport.clientWidth / 2, y = viewport.clientHeight / 2) {
    const scale = Math.max(0.025, Math.min(2.5, transform.scale * factor));
    transform.x = x - ((x - transform.x) * scale) / transform.scale;
    transform.y = y - ((y - transform.y) * scale) / transform.scale;
    transform.scale = scale;
    apply();
  }
  function inspect(id) {
    selectedId = id;
    const detail = diagram.details[id], node = nodes.get(id);
    if (!detail || !node) return;
    scene.querySelectorAll(".node").forEach(n => n.classList.toggle("selected", n.dataset.key === id));
    scene.querySelectorAll(".edge").forEach(edge => {
      edge.classList.toggle("highlight", edge.dataset.source === id || edge.dataset.target === id);
    });
    const target = detail.node.targetTable || detail.node.dispatchTarget;
    onInspect({
      tableGuid: detail.tableGuid,
      kicker: detail.table + " · 节点 " + detail.node.id,
      title: node.title,
      summary: node.subtitle,
      detail: JSON.stringify(detail, null, 2),
      call: target ? { label: detail.node.dispatchTarget ? "定位请求的行为表" : "定位调用子表", target } : null,
    });
  }
  function drawEdge(edge, ox, oy) {
    const role = ROLES.includes(edge.role) ? edge.role : "next";
    for (const section of edge.sections || []) {
      const points = [section.startPoint, ...(section.bendPoints || []), section.endPoint];
      const d = points.map((p, i) => `${i ? "L" : "M"}${p.x + ox},${p.y + oy}`).join(" ");
      const path = element("path", {
        d,
        class: `edge role-${role}`,
        "data-source": edge.sources[0],
        "data-target": edge.targets[0],
        "data-role": edge.role,
      });
      if (edge.continuation || edge.role === "fallback") path.setAttribute("stroke-dasharray", "6 5");
      scene.append(path);
    }
    for (const label of edge.labels || [])
      if (label.x !== undefined)
        scene.append(element("text", { x: label.x + ox, y: label.y + oy + 15, class: `edge-label role-${role}` }, label.text));
  }
  function render(result) {
    scene.replaceChildren();
    mini.replaceChildren();
    nodes.clear();
    groups.clear();
    const edgeRecords = [];
    function walk(parent, ox = 0, oy = 0) {
      for (const child of parent.children || []) {
        const x = ox + child.x, y = oy + child.y;
        if (child.children) {
          groups.set(child.id, { ...child, x, y });
          scene.append(element("rect", { x, y, width: child.width, height: child.height, rx: 20, class: "group-box" }));
          scene.append(element("text", { x: x + 22, y: y + 29, class: "group-title" }, child.title));
          if (child.id === graph.entry)
            scene.append(element("text", { x: x + 22, y: y + 44, class: "group-entry" }, "当前局部入口 · 全局入口未核实"));
          walk(child, x, y);
        } else nodes.set(child.id, { ...child, x, y });
      }
      for (const edge of parent.edges || []) edgeRecords.push([edge, ox, oy]);
    }
    walk(result);
    for (const record of edgeRecords) drawEdge(...record);
    for (const node of nodes.values()) {
      const g = element("g", {
        class: `node kind-${node.kind}`,
        role: "button",
        tabindex: "0",
        "data-key": node.id,
        "aria-label": `${diagram.details[node.id].table} 节点 ${node.localId} ${node.title}`,
      });
      g.append(element("rect", { x: node.x, y: node.y, width: node.width, height: node.height, rx: 12 }));
      const foreign = element("foreignObject", { x: node.x + 16, y: node.y + 12, width: node.width - 32, height: node.height - 24 });
      const box = document.createElementNS("http://www.w3.org/1999/xhtml", "div");
      box.setAttribute("class", "node-text");
      for (const [tag, text] of [
        ["small", `节点 ${node.localId}${node.entry ? " · 子表入口" : ""}`],
        ["b", node.title],
        ["span", node.subtitle],
      ]) {
        const e = document.createElementNS("http://www.w3.org/1999/xhtml", tag);
        e.textContent = text;
        box.append(e);
      }
      foreign.append(box);
      g.append(foreign);
      g.addEventListener("click", () => {
        if (!moving) inspect(node.id);
      });
      g.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          inspect(node.id);
        }
      });
      scene.append(g);
      mini.append(element("rect", { x: node.x, y: node.y, width: node.width, height: node.height, class: node.kind === "unknown" ? "mini-unknown" : "mini-node" }));
    }
    mini.setAttribute("viewBox", `0 0 ${result.width} ${result.height}`);
    mini.append(element("rect", { class: "mini-view" }));
    focus(selectedId && nodes.has(selectedId) ? selectedId : diagram.entry);
    onStatus(null);
    svg.dataset.ready = "true";
    svg.dataset.nodes = String(nodes.size);
    svg.dataset.groups = String(groups.size);
    svg.dataset.edges = String(edgeRecords.length);
  }
  async function arrange() {
    const run = ++layoutRun;
    onStatus("正在自动排列全部子表…");
    try {
      const { default: ELK } = await import("elkjs/lib/elk.bundled.js");
      const elk = new ELK(), input = JSON.parse(JSON.stringify(diagram.layout));
      // Keep each state machine compact, then route calls between the table boxes.
      // Call edges retain their exact source/target IDs as data, rather than
      // inventing return edges from shared callees to every caller.
      const options = { ...input.layoutOptions, "elk.hierarchyHandling": "SEPARATE_CHILDREN", "elk.direction": direction };
      const local = [];
      for (const group of input.children) {
        const edges = input.edges.filter(e => !["call", "dispatch"].includes(e.role) && e.sources[0].startsWith(group.id + "/"));
        local.push(await elk.layout({ ...group, layoutOptions: { ...options, ...group.layoutOptions, "elk.direction": "RIGHT" }, edges }));
      }
      const cross = input.edges
        .filter(e => ["call", "dispatch"].includes(e.role))
        .map(e => {
          const source = e.sources[0].split("/"), target = e.targets[0].split("/");
          const text = "节点 " + source[1] + (e.role === "dispatch" ? " 请求切换 → 入口 " : " 调用 → 入口 ") + target[1];
          return { ...e, sources: [source[0]], targets: [target[0]], actualSources: e.sources, actualTargets: e.targets, labels: [{ text, width: 168, height: 20 }] };
        });
      const outer = await elk.layout({
        id: "monster",
        layoutOptions: { ...options, "elk.spacing.nodeNode": "100", "elk.layered.spacing.nodeNodeBetweenLayers": "130" },
        children: local.map(g => ({ id: g.id, width: g.width, height: g.height })),
        edges: cross,
      });
      outer.children = outer.children.map(g => ({ ...local.find(t => t.id === g.id), x: g.x, y: g.y }));
      outer.edges = outer.edges.map(e => ({ ...e, sources: e.actualSources, targets: e.actualTargets }));
      if (run !== layoutRun) return;
      layout = outer;
      render(outer);
    } catch (error) {
      onStatus("自动布局失败：" + error.message);
      console.error(error);
    }
  }

  function onWheel(event) {
    event.preventDefault();
    const r = viewport.getBoundingClientRect();
    zoom(Math.exp(-event.deltaY * 0.0015), event.clientX - r.left, event.clientY - r.top);
  }
  function onPointerDown(event) {
    if (event.button !== 0 || event.target.closest(".minimap")) return;
    drag = { x: event.clientX, y: event.clientY, tx: transform.x, ty: transform.y };
    moving = false;
  }
  function onPointerMove(event) {
    if (!drag) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    if (Math.hypot(dx, dy) > 4) {
      moving = true;
      viewport.classList.add("dragging");
      transform.x = drag.tx + dx;
      transform.y = drag.ty + dy;
      apply();
    }
  }
  function onPointerUp() {
    drag = null;
    viewport.classList.remove("dragging");
    setTimeout(() => (moving = false), 0);
  }
  function onMiniClick(event) {
    if (!layout) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(mini.getScreenCTM().inverse());
    transform.x = viewport.clientWidth / 2 - point.x * transform.scale;
    transform.y = viewport.clientHeight / 2 - point.y * transform.scale;
    apply();
  }
  function onKey(event) {
    if (event.target !== viewport) return;
    const step = 80;
    const shift = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[event.key];
    if (shift) {
      event.preventDefault();
      transform.x += shift[0];
      transform.y += shift[1];
      apply();
    } else if (event.key === "+" || event.key === "=") zoom(1.3);
    else if (event.key === "-") zoom(1 / 1.3);
  }
  viewport.addEventListener("wheel", onWheel, { passive: false });
  viewport.addEventListener("pointerdown", onPointerDown);
  viewport.addEventListener("keydown", onKey);
  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp);
  mini.addEventListener("click", onMiniClick);
  const resize = new ResizeObserver(() => apply());
  resize.observe(viewport);

  function download() {
    if (!layout) return;
    const exported = svg.cloneNode(true);
    exported.setAttribute("viewBox", `0 0 ${layout.width} ${layout.height}`);
    exported.setAttribute("width", layout.width);
    exported.setAttribute("height", layout.height);
    exported.querySelector(".scene").removeAttribute("transform");
    const tokens = getComputedStyle(viewport);
    const variables = ["--font", "--canvas", "--surface", "--surface-high", "--outline", "--outline-variant", "--on-surface", "--on-surface-variant", "--primary", ...["condition", "action", "call", "mutation", "return", "weighted_random", "unknown"].map(k => `--t-${k}`), ...ROLES.map(r => `--r-${r}`)];
    const style = element("style");
    style.textContent =
      `svg { ${variables.map(v => `${v}: ${tokens.getPropertyValue(v)};`).join(" ")} background: var(--canvas); }\n` +
      [...document.styleSheets].flatMap(sheet => { try { return [...sheet.cssRules].map(r => r.cssText).filter(t => /\.(node|edge|group-|role-|kind-)/.test(t)); } catch { return []; } }).join("\n");
    exported.prepend(style);
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(exported)], { type: "image/svg+xml;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = graph.enemyId + ".logic.svg";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  arrange();
  return {
    fit: () => layout && fitBox({ x: 0, y: 0, width: layout.width, height: layout.height }),
    focusEntry: () => focus(diagram.entry),
    focus,
    zoom,
    showTable(id) {
      const group = groups.get(id);
      if (group) {
        fitBox(group);
        inspect(group.entry);
      }
    },
    followCall: target => focus(groups.get(target).entry),
    setDirection(value) {
      direction = value;
      arrange();
    },
    download,
    destroy() {
      layoutRun++;
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      resize.disconnect();
    },
  };
}
