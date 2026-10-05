"""Embed one monster's combined graph, renderer and ELK into an offline HTML."""

from html import escape
import json
from pathlib import Path
import re

from .diagram import combined_diagram


def render_action_names(graph):
    catalog = graph.get("actionNameCatalog")
    if not catalog:
        return ""
    rows = "".join(
        "<tr>"
        + "".join(
            "<td>" + escape(str(row[key])) + "</td>"
            for key in ("uniqueId", "name", "comment")
        )
        + "</tr>"
        for row in catalog["shellCatalog"]
    )
    return (
        '<details id="action-names"><summary>动作名称来源与原始名称目录</summary><p>'
        + escape(catalog["boundary"])
        + "</p><table><thead><tr><th>Shell UID</th><th>原名</th><th>原注释</th></tr></thead><tbody>"
        + rows
        + "</tbody></table></details>"
    )


def render_html(graph):
    here = Path(__file__).resolve().parent
    vendor = here / "vendor/elkjs"
    coverage = graph["coverage"]
    enemy = graph.get("enemyName") or {"EM0001_00_0": "雌火龙"}.get(
        graph["enemyId"], graph["enemyId"]
    )
    payload = json.dumps(
        {
            "graph": graph,
            "diagram": combined_diagram(
                graph, compact_details=bool(graph.get("playerView"))
            ),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    values = {
        "TITLE": escape(
            enemy + (" · 行为决策树" if graph.get("playerView") else " · 行动逻辑大图")
        ),
        "COUNTS": (
            "行为表入口 · 距离 / 角度 / 状态分支 · 动作"
            if graph.get("playerView")
            else f"{coverage['localTables']} 个子表 · {coverage['nodes']} 个节点 · {coverage.get('weightedSelections', 0)} 个权重选择点"
        ),
        "SCOPE": (
            "整只怪物的行为在同一棵树中：先按请求的行为表分组，再展开距离、角度和状态分支直到动作。未核实的判断和接入关系保留在树中，动作请求不等于一定成功出招。"
            if graph.get("playerView")
            else escape(graph["scope"])
            + f"。其中 {coverage.get('completeLocalTables', 0)} 个局部流程已核实，{coverage.get('unknownFlowNodes', 0)} 处后继与 {coverage.get('unknownConditions', 0)} 处条件仍待核实。"
        ),
        "CSS": (here / "viewer.css").read_text(encoding="utf-8"),
        "JS": (here / "viewer.js").read_text(encoding="utf-8"),
        "PLAYER_ENGINE": (here / "player_engine.js").read_text(encoding="utf-8"),
        "PLAYER_JS": (here / "player_viewer.js").read_text(encoding="utf-8"),
        "PLAYER_HIDDEN": "" if graph.get("playerView") else "hidden",
        "TECHNICAL_HIDDEN": "hidden" if graph.get("playerView") else "",
        "DATA": payload,
        "ACTION_NAMES": render_action_names(graph),
        "ELK": (vendor / "elk.bundled.js")
        .read_text(encoding="utf-8")
        .replace("</script", "<\\/script"),
        "LICENSE": "<details><summary>开源许可证</summary><pre>"
        + escape((vendor / "LICENSE.md").read_text(encoding="utf-8"))
        + "</pre></details>",
    }
    template = (here / "viewer.html").read_text(encoding="utf-8")
    return re.sub(
        r"__(TITLE|COUNTS|SCOPE|CSS|JS|DATA|ELK|LICENSE|ACTION_NAMES|PLAYER_ENGINE|PLAYER_JS|PLAYER_HIDDEN|TECHNICAL_HIDDEN)__",
        lambda match: values[match[1]],
        template,
    )
