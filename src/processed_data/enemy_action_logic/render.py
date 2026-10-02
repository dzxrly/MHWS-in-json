"""Readable action flowcharts, embedded with the viewer in one offline HTML."""

import hashlib
from html import escape
import json
from pathlib import Path

from src.processed_data.enemy_action_logic.layout import place, wrap

COLORS = {
    "process": ("#edf5fb", "#2670a6"),
    "decision": ("#fff4de", "#ac7627"),
    "action": ("#eaf8f4", "#258571"),
    "unknown": ("#fff1ed", "#b66449"),
    "end": ("#edf0f5", "#63748a"),
}


def svg(graph: dict, *, marker_id: str = "arrow") -> str:
    layout = place(graph)
    width, height = layout["width"], layout["height"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" width="{width:.1f}" height="{height:.1f}" role="img" aria-label="{escape(graph["title"], quote=True)}">',
        f'<defs><marker id="{escape(marker_id, quote=True)}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#718096"/></marker></defs>',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g font-family="Microsoft YaHei,Noto Sans CJK SC,sans-serif">',
    ]
    for group in layout.get("groups", []):
        x, y, w, h = (group[key] for key in ("x", "y", "width", "height"))
        parts.append(
            f'<rect class="region" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="10" fill="#f8fafc" stroke="#d5e0e8" stroke-width="1"/>'
        )
        if group.get("title"):
            parts.append(
                f'<text x="{x+12:.1f}" y="{y+17:.1f}" font-size="13" fill="#637b8c">{escape(group["title"])}</text>'
            )
    for edge, shape in zip(graph["edges"], layout["edges"]):
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in shape["points"])
        dash = 'stroke-dasharray="7 5"' if edge["evidence"] == "unresolved" else ""
        identity = f'data-from="{escape(edge["from"], quote=True)}" data-to="{escape(edge["to"], quote=True)}" data-role="{escape(edge.get("role", ""), quote=True)}"'
        parts.append(
            f'<polyline class="edge" {identity} points="{points}" fill="none" stroke="#8593a3" stroke-width="1.4" {dash} marker-end="url(#{escape(marker_id, quote=True)})"/>'
        )
        if edge.get("label"):
            lx, ly = shape.get("labelX", shape["points"][1][0]), shape.get(
                "labelY", shape["points"][1][1]
            )
            parts.append(
                f'<text class="edge-label" {identity} x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" fill="#566576" font-size="11" paint-order="stroke" stroke="white" stroke-width="4" stroke-linejoin="round">{escape(edge["label"])}</text>'
            )
    for node in graph["nodes"]:
        shape = layout["nodes"][node["id"]]
        x, y, w, h = (shape[key] for key in ("x", "y", "width", "height"))
        fill, stroke = COLORS[node["kind"]]
        parts.append(
            f'<g class="node" data-node="{escape(node["id"], quote=True)}" tabindex="0" role="button" aria-label="{escape(node["label"], quote=True)}"><title>{escape(node["label"])}</title>'
        )
        if node["kind"] == "decision":
            points = f"{x+w/2},{y} {x+w},{y+h/2} {x+w/2},{y+h} {x},{y+h/2}"
            parts.append(
                f'<polygon points="{points}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>'
            )
        else:
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{20 if node["kind"] == "end" else 7}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>'
            )
        text_width = w * 0.72 if node["kind"] == "decision" else w
        lines = wrap(node["label"], max(12, int((text_width - 28) / 6.8)))
        font = min(13, (h - 20) / (len(lines) * 1.4))
        top = y + h / 2 - (len(lines) - 1) * font * 0.7
        for index, line in enumerate(lines):
            parts.append(
                f'<text x="{x+w/2:.1f}" y="{top+index*font*1.4:.1f}" text-anchor="middle" dominant-baseline="middle" font-size="{font:.1f}" fill="#253648">{escape(line)}</text>'
            )
        parts.append("</g>")
    parts.append("</g></svg>")
    return "".join(parts)


def html_document(payload: dict) -> str:
    enemies = payload["enemies"]
    options, panels = [], []
    for enemy in enemies:
        options.append(
            f'<option value="{enemy["enemyId"]}">{escape(enemy["enemyId"] + " · " + enemy["name"])}</option>'
        )
        for index, graph in enumerate(enemy["graphs"]):
            panels.append(
                f'<section class="diagram" data-enemy="{enemy["enemyId"]}" data-phase="{index}" hidden>{svg(graph, marker_id="arrow-" + enemy["enemyId"] + "-" + str(index))}</section>'
            )
    data = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace("&", "\\u0026")
    )
    digest = hashlib.sha256(data.encode("utf-8")).hexdigest()
    assets = Path(__file__).parent
    style = (assets / "viewer.css").read_text(encoding="utf-8")
    script = (assets / "viewer.js").read_text(encoding="utf-8")
    return f"""<!doctype html><html lang="zh-Hans"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>怪物行动逻辑：玩家视角</title><style>{style}</style><header><h1>怪物行动逻辑 · 玩家视角</h1><p>从玩家距离与怪物状态，查看可能发动的动作。动作名称和类型直接写在图中；虚线表示尚未还原的转移条件。</p></header><nav><label>怪物 <select id="enemy">{"".join(options)}</select></label><label>阶段 <select id="phase"></select></label><button id="entry">回到入口</button><button id="minus">−</button><button id="plus">＋</button><button id="fit">查看全图</button><button id="actual">100%</button><input id="search" aria-label="查找动作或节点" placeholder="查找动作或类型"><button id="find">查找下一个</button><span id="status"></span></nav><main><div id="viewport">{"".join(panels)}</div><aside><strong id="identity"></strong><p id="notes"></p><div id="action-detail">点击动作节点，查看具体动作与条件。</div><details><summary>说明与分析范围</summary><pre id="limitations"></pre></details><details><summary>查看数据来源</summary><pre id="source-detail"></pre></details></aside></main><script type="application/json" id="enemy-catalog" data-sha256="{digest}">{data}</script><script>{script}</script></html>"""
