"""Deterministic SVG geometry, with optional imported vector layout."""

from collections import defaultdict, deque
import math
import unicodedata


def compact_layout(layout: dict) -> dict:
    """Remove redundant collinear samples at subpixel precision, in place."""
    for edge in layout.get("edges", []):
        points = []
        for x, y in edge.get("points", []):
            point = [round(x, 2), round(y, 2)]
            if points and point == points[-1]:
                continue
            while len(points) >= 2:
                a, b = points[-2:]
                dx, dy = point[0] - a[0], point[1] - a[1]
                distance = math.hypot(dx, dy)
                cross = abs((b[0] - a[0]) * dy - (b[1] - a[1]) * dx)
                forward = (
                    (b[0] - a[0]) * (point[0] - b[0])
                    + (b[1] - a[1]) * (point[1] - b[1])
                ) >= 0
                if not forward or cross > 0.03 * distance:
                    break
                points.pop()
            points.append(point)
        edge["points"] = points
    return layout


def wrap(text: str, width: int = 31) -> list[str]:
    result = []
    for part in text.split("\n"):
        line, used = "", 0
        for char in part:
            size = 2 if unicodedata.east_asian_width(char) in "WF" else 1
            if line and used + size > width:
                result.append(line)
                line, used = "", 0
            line += char
            used += size
        result.append(line)
    return result


def place(graph: dict) -> dict:
    imported = graph.get("layout")
    if imported is not None:
        return _checked_layout(graph, imported)
    nodes = {node["id"]: node for node in graph["nodes"]}
    outgoing = defaultdict(list)
    for edge in graph["edges"]:
        if not edge.get("back"):
            outgoing[edge["from"]].append(edge["to"])
    levels, pending = {graph["entry"]: 0}, deque([graph["entry"]])
    while pending:
        node = pending.popleft()
        for target in outgoing[node]:
            if target not in levels:
                levels[target] = levels[node] + 1
                pending.append(target)
    if graph.get("mode") == "player":
        levels = {key: node["rank"] for key, node in nodes.items()}
    ranks = defaultdict(list)
    for key in nodes:
        ranks[levels.get(key, max(levels.values()) + 1)].append(key)
    geometry = {}
    player = graph.get("mode") == "player"
    columns = min(2 if player else 7, max(len(row) for row in ranks.values()))
    stride, node_width = (430, 400) if player else (295, 270)
    page_width = columns * stride + 120
    y = 40
    for rank in sorted(ranks):
        for start in range(0, len(ranks[rank]), columns):
            row = ranks[rank][start : start + columns]
            heights = {
                key: max(
                    82,
                    len(
                        wrap(
                            nodes[key]["label"],
                            (
                                (36 if nodes[key]["kind"] == "decision" else 52)
                                if player
                                else (23 if nodes[key]["kind"] == "decision" else 31)
                            ),
                        )
                    )
                    * 17
                    + 30,
                )
                * (2 if nodes[key]["kind"] == "decision" else 1)
                for key in row
            }
            row_height = max(heights.values())
            for column, key in enumerate(row):
                grid_column = (columns - len(row)) // 2 + column
                x = 60 + grid_column * stride
                geometry[key] = {
                    "x": x,
                    "y": y,
                    "width": node_width,
                    "height": row_height,
                }
            y += row_height + 90
    edges = []
    for index, edge in enumerate(graph["edges"]):
        source, target = geometry[edge["from"]], geometry[edge["to"]]
        x1, y1 = source["x"] + source["width"] / 2, source["y"] + source["height"]
        x2, y2 = target["x"] + target["width"] / 2, target["y"]
        if y2 > y1:
            # Use the fixed grid's gaps instead of passing through intermediate
            # action boxes, which would visually invent an action sequence.
            lane = target["x"] - 13
            middle = target["y"] + target["height"] / 2
            points = [
                [x1, y1],
                [x1, y1 + 24],
                [lane, y1 + 24],
                [lane, middle],
                [target["x"], middle],
            ]
        else:
            lane = 20 + (index % 8) * 4
            points = [
                [x1, y1],
                [lane, y1 + 28],
                [lane, y2 - 28],
                [x2, y2 - 28],
                [x2, y2],
            ]
        edges.append(
            {
                "points": points,
                "labelX": (points[1][0] + points[2][0]) / 2,
                "labelY": points[1][1] - 7,
            }
        )
    return {"width": page_width, "height": y, "nodes": geometry, "edges": edges}


def _checked_layout(graph: dict, layout: dict) -> dict:
    if {node["id"] for node in graph["nodes"]} != set(layout.get("nodes", {})):
        raise ValueError("Layout nodes do not match the graph")
    if len(layout.get("edges", [])) != len(graph["edges"]):
        raise ValueError("Layout edges do not match the graph")
    width, height = layout.get("width"), layout.get("height")
    if not all(
        isinstance(v, (int, float)) and math.isfinite(v) and v > 0
        for v in (width, height)
    ):
        raise ValueError("Invalid layout bounds")
    for bounds in layout["nodes"].values():
        x, y, w, h = (bounds.get(key) for key in ("x", "y", "width", "height"))
        if (
            not all(
                isinstance(v, (int, float)) and math.isfinite(v) for v in (x, y, w, h)
            )
            or min(w, h) <= 0
            or min(x, y) < 0
            or x + w > width + 1
            or y + h > height + 1
        ):
            raise ValueError("Node exceeds imported layout bounds")
    for edge in layout["edges"]:
        if len(edge.get("points", [])) < 2:
            raise ValueError("An edge requires at least two points")
        for x, y in edge["points"]:
            if (
                not math.isfinite(x)
                or not math.isfinite(y)
                or not (0 <= x <= width and 0 <= y <= height)
            ):
                raise ValueError("Edge exceeds imported layout bounds")
    return layout
