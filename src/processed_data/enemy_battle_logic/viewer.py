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
        '<details id="action-names"><summary>动作名称对照表</summary><p>'
        + escape(catalog["boundary"])
        + "</p><table><thead><tr><th>Shell UID</th><th>原名</th><th>原注释</th></tr></thead><tbody>"
        + rows
        + "</tbody></table></details>"
    )


def render_html(graph):
    here = Path(__file__).resolve().parent
    vendor = here / "vendor/elkjs"
    coverage = graph["coverage"]
    game_version = graph.get("profile", {}).get("gameVersion")
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
        "TITLE": escape(enemy + " · 行动逻辑"),
        "NAME": escape(enemy),
        "META": escape(
            graph["enemyId"] + (f" · 游戏版本 {game_version}" if game_version else "")
        ),
        "SCOPE": (
            f"共 {coverage['localTables']} 个子表、{coverage['nodes']} 个节点，"
            f"其中 {coverage.get('completeLocalTables', 0)} 个子表的流程已核实；"
            f"{coverage.get('unknownFlowNodes', 0)} 处后继、"
            f"{coverage.get('unknownConditions', 0)} 处条件待核查。"
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
        "LICENSE": "<details><summary>elkjs 许可证</summary><pre>"
        + escape((vendor / "LICENSE.md").read_text(encoding="utf-8"))
        + "</pre></details>",
    }
    template = (here / "viewer.html").read_text(encoding="utf-8")
    return re.sub(
        r"__(TITLE|NAME|META|SCOPE|CSS|JS|DATA|ELK|LICENSE|ACTION_NAMES|PLAYER_ENGINE|PLAYER_JS|PLAYER_HIDDEN|TECHNICAL_HIDDEN)__",
        lambda match: values[match[1]],
        template,
    )
