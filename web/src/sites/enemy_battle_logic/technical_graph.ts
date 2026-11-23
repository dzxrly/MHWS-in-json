/* The behaviour tables' original flow, laid out by ELK, for checking against the data. */
import { formatDecimalText } from "../../composables/numbers";
import type { ElkShape } from "elkjs/lib/elk.bundled.js";
import type { BattleGraph, FlowDiagram, FlowEdge, FlowGroup, FlowInspection, FlowNode } from "./types";

const ROLES = ["true", "false", "next", "resume", "call", "dispatch", "random", "fallback"];

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}
export type FlowDirection = "DOWN" | "RIGHT";
interface TechnicalGraphOptions {
  graph: BattleGraph;
  diagram: FlowDiagram;
  viewport: HTMLElement;
  svg: SVGSVGElement;
  scene: SVGGElement;
  mini: SVGSVGElement;
  onStatus: (text: string | null) => void;
  onZoom: (percent: number) => void;
  onInspect: (info: FlowInspection) => void;
}

function box(shape: ElkShape, ox = 0, oy = 0): Box {
  const { x = 0, y = 0, width, height } = shape;
  if (width === undefined || height === undefined) {
    throw new Error(`布局缺少 ${shape.id ?? ""} 的宽度或高度`);
  }
  return { x: ox + x, y: oy + y, width, height };
}

function element<Tag extends keyof SVGElementTagNameMap>(tag: Tag, attributes: Record<string, string | number> = {}, text: string | null = null) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  if (text !== null) node.textContent = text;
  return node;
}

/**
 * Lay out `diagram` in `scene` (inside `svg`, inside `viewport`) with a
 * minimap in `mini`. `onStatus(text | null)`, `onZoom(percent)` and
 * `onInspect(info)` report back to the page.
 */
export function createTechnicalGraph({ graph, diagram, viewport, svg, scene, mini, onStatus, onZoom, onInspect }: TechnicalGraphOptions) {
  if (graph.playerView) {
    const tables = new Map(graph.tables.map(table => [table.tableGuid, table]));
    for (const detail of Object.values(diagram.details)) {
      const table = tables.get(detail.tableGuid);
      if (!table) continue;
      detail.node = table.nodes.find(node => node.id === detail.localId);
      detail.tableEvidence = table.evidence;
    }
  }
  const nodes = new Map<string, FlowNode & Box>(), groups = new Map<string, FlowGroup & Box>();
  let layout: Box | null = null,
    transform = { x: 0, y: 0, scale: 1 },
    selectedId: string | null = null,
    drag: { x: number; y: number; tx: number; ty: number } | null = null,
    moving = false,
    layoutRun = 0,
    direction: FlowDirection = "DOWN";

  function apply() {
    scene.setAttribute("transform", `translate(${transform.x},${transform.y}) scale(${transform.scale})`);
    onZoom(Math.round(transform.scale * 100));
    const rect = mini.querySelector(".mini-view");
    if (rect) {
      rect.setAttribute("x", String(-transform.x / transform.scale));
      rect.setAttribute("y", String(-transform.y / transform.scale));
      rect.setAttribute("width", String(viewport.clientWidth / transform.scale));
      rect.setAttribute("height", String(viewport.clientHeight / transform.scale));
    }
  }
  function fitBox(box: Box) {
    const width = viewport.clientWidth, height = viewport.clientHeight;
    transform.scale = Math.min(1.3, (width - 90) / box.width, (height - 90) / box.height);
    transform.x = (width - box.width * transform.scale) / 2 - box.x * transform.scale;
    transform.y = (height - box.height * transform.scale) / 2 - box.y * transform.scale;
    apply();
  }
  function focus(id: string) {
    const node = nodes.get(id);
    if (!node) return;
    transform.scale = 0.85;
    transform.x = viewport.clientWidth * 0.28 - (node.x + node.width / 2) * transform.scale;
    transform.y = viewport.clientHeight / 2 - (node.y + node.height / 2) * transform.scale;
    apply();
    inspect(id);
  }
  function zoom(factor: number, x = viewport.clientWidth / 2, y = viewport.clientHeight / 2) {
    const scale = Math.max(0.025, Math.min(2.5, transform.scale * factor));
    transform.x = x - ((x - transform.x) * scale) / transform.scale;
    transform.y = y - ((y - transform.y) * scale) / transform.scale;
    transform.scale = scale;
    apply();
  }
  function inspect(id: string) {
    selectedId = id;
    const detail = diagram.details[id], node = nodes.get(id);
    if (!detail || !node) return;
    scene.querySelectorAll<SVGGElement>(".node").forEach(n => n.classList.toggle("selected", n.dataset.key === id));
    scene.querySelectorAll<SVGPathElement>(".edge").forEach(edge => {
      edge.classList.toggle("highlight", edge.dataset.source === id || edge.dataset.target === id);
    });
    const target = detail.node?.targetTable || detail.node?.dispatchTarget;
    onInspect({
      tableGuid: detail.tableGuid,
      kicker: detail.table + " · 节点 " + (detail.node?.id ?? node.localId),
      title: node.title,
      summary: node.subtitle,
      detail: JSON.stringify(detail, null, 2),
      call: target ? { label: detail.node?.dispatchTarget ? "定位请求的行为表" : "定位调用子表", target } : null,
    });
  }
  function drawEdge(edge: FlowEdge, ox: number, oy: number) {
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
      if (label.x !== undefined && label.y !== undefined)
        scene.append(element("text", { x: label.x + ox, y: label.y + oy + 15, class: `edge-label role-${role}` }, label.text));
  }
  function render(result: Box & { children: (FlowGroup & Box & { edges?: FlowEdge[] })[]; edges: FlowEdge[] }) {
    scene.replaceChildren();
    mini.replaceChildren();
    nodes.clear();
    groups.clear();
    const edgeRecords: [FlowEdge, number, number][] = [];
    for (const group of result.children) {
      const { x, y, width, height } = group;
      groups.set(group.id, group);
      scene.append(element("rect", { x, y, width, height, rx: 20, class: "group-box" }));
      scene.append(element("text", { x: x + 22, y: y + 29, class: "group-title" }, group.title));
      if (group.id === graph.entry)
        scene.append(element("text", { x: x + 22, y: y + 44, class: "group-entry" }, "当前局部入口 · 全局入口未核实"));
      for (const node of group.children) nodes.set(node.id, {
        ...node, ...box(node, x, y), title: formatDecimalText(node.title), subtitle: formatDecimalText(node.subtitle),
      });
      for (const edge of group.edges ?? []) edgeRecords.push([edge, x, y]);
    }
    for (const edge of result.edges) edgeRecords.push([edge, 0, 0]);
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
      const elk = new ELK(), input = structuredClone(diagram.layout);
      // Keep each state machine compact, then route calls between the table boxes.
      // Call edges retain their exact source/target IDs as data, rather than
      // inventing return edges from shared callees to every caller.
      const options = { ...input.layoutOptions, "elk.hierarchyHandling": "SEPARATE_CHILDREN", "elk.direction": direction };
      const local = new Map<string, FlowGroup & { edges: FlowEdge[] }>();
      for (const group of input.children) {
        const edges = input.edges.filter(e => !["call", "dispatch"].includes(e.role) && e.sources[0].startsWith(group.id + "/"));
        const arranged = await elk.layout({ ...group, layoutOptions: { ...options, ...group.layoutOptions, "elk.direction": "RIGHT" }, edges });
        local.set(group.id, { ...arranged, children: arranged.children ?? [] });
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
        children: [...local.values()].map(g => ({ id: g.id, width: g.width, height: g.height })),
        edges: cross,
      });
      if (run !== layoutRun) return;
      const children = (outer.children ?? []).map(placed => {
        const group = local.get(placed.id);
        if (!group) throw new Error(`找不到布局子表 ${placed.id}`);
        return { ...group, ...box({ ...group, x: placed.x, y: placed.y }) };
      });
      const edges = outer.edges.map(edge => ({ ...edge, sources: edge.actualSources, targets: edge.actualTargets }));
      layout = box(outer);
      render({ ...layout, children, edges });
    } catch (error) {
      onStatus("自动布局失败：" + (error instanceof Error ? error.message : String(error)));
      console.error(error);
    }
  }

  function onWheel(event: WheelEvent) {
    event.preventDefault();
    const r = viewport.getBoundingClientRect();
    zoom(Math.exp(-event.deltaY * 0.0015), event.clientX - r.left, event.clientY - r.top);
  }
  function onPointerDown(event: PointerEvent) {
    if (event.button !== 0 || (event.target instanceof Element && event.target.closest(".minimap"))) return;
    drag = { x: event.clientX, y: event.clientY, tx: transform.x, ty: transform.y };
    moving = false;
  }
  function onPointerMove(event: PointerEvent) {
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
  function onMiniClick(event: MouseEvent) {
    const matrix = mini.getScreenCTM();
    if (!layout || !matrix) return;
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    transform.x = viewport.clientWidth / 2 - point.x * transform.scale;
    transform.y = viewport.clientHeight / 2 - point.y * transform.scale;
    apply();
  }
  function onKey(event: KeyboardEvent) {
    if (event.target !== viewport) return;
    const step = 80;
    const offsets: Record<string, [number, number]> = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
    const shift = offsets[event.key];
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
    const exported = svg.cloneNode(true) as SVGSVGElement;
    exported.setAttribute("viewBox", `0 0 ${layout.width} ${layout.height}`);
    exported.setAttribute("width", String(layout.width));
    exported.setAttribute("height", String(layout.height));
    exported.querySelector(".scene")?.removeAttribute("transform");
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
    showTable(id: string) {
      const group = groups.get(id);
      if (group) {
        fitBox(group);
        inspect(group.entry);
      }
    },
    followCall(target: string) {
      const group = groups.get(target);
      if (group) focus(group.entry);
    },
    setDirection(value: FlowDirection) {
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
