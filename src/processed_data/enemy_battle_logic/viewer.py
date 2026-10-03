"""Embed one monster's combined graph, renderer and ELK into an offline HTML."""

from html import escape
import json
from pathlib import Path
import re

from .diagram import combined_diagram


def render_html(graph):
    here = Path(__file__).resolve().parent
    vendor = here / "vendor/elkjs"
    coverage = graph["coverage"]
    enemy = graph.get("enemyName") or {"EM0001_00_0": "雌火龙"}.get(
        graph["enemyId"], graph["enemyId"]
    )
    payload = json.dumps(
        {"graph": graph, "diagram": combined_diagram(graph)},
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("<", "\\u003c")
    values = {
        "TITLE": escape(enemy + " · 行动逻辑大图"),
        "COUNTS": f"{coverage['localTables']} 个子表 · {coverage['nodes']} 个节点 · {coverage.get('weightedSelections', 0)} 个权重选择点",
        "SCOPE": escape(graph["scope"])
        + f"。其中 {coverage.get('completeLocalTables', 0)} 个局部流程已核实，{coverage.get('unknownFlowNodes', 0)} 个节点仍未知。",
        "CSS": (here / "viewer.css").read_text(encoding="utf-8"),
        "JS": (here / "viewer.js").read_text(encoding="utf-8"),
        "DATA": payload,
        "ELK": (vendor / "elk.bundled.js")
        .read_text(encoding="utf-8")
        .replace("</script", "<\\/script"),
        "LICENSE": "<details><summary>开源许可证</summary><pre>"
        + escape((vendor / "LICENSE.md").read_text(encoding="utf-8"))
        + "</pre></details>",
    }
    template = (here / "viewer.html").read_text(encoding="utf-8")
    return re.sub(
        r"__(TITLE|COUNTS|SCOPE|CSS|JS|DATA|ELK|LICENSE)__",
        lambda match: values[match[1]],
        template,
    )
