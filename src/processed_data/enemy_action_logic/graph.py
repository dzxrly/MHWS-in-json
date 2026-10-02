"""Graph contract shared by native import, rendering, and HTML validation."""

from collections import defaultdict, deque

KINDS = frozenset({"process", "decision", "action", "unknown", "end"})
EVIDENCE = frozenset({"resource", "native", "unresolved", "context"})


def validate_graph(graph: dict) -> None:
    if not isinstance(graph.get("id"), str) or not graph["id"]:
        raise ValueError("Graph requires a phase ID")
    nodes = graph.get("nodes", [])
    ids = {node["id"] for node in nodes}
    if not nodes or len(ids) != len(nodes) or graph.get("entry") not in ids:
        raise ValueError("Duplicate nodes or missing graph entry")
    for node in nodes:
        if node.get("kind") not in KINDS or node.get("evidence") not in EVIDENCE:
            raise ValueError(f"Invalid node kind/evidence: {node['id']}")
        if not isinstance(node.get("label"), str) or not node["label"]:
            raise ValueError("Every node requires a label")
    outgoing, incoming = defaultdict(list), defaultdict(list)
    for edge in graph.get("edges", []):
        if edge.get("from") not in ids or edge.get("to") not in ids:
            raise ValueError("Dangling graph edge")
        if edge.get("evidence") not in EVIDENCE:
            raise ValueError("Every edge requires an evidence category")
        outgoing[edge["from"]].append(edge["to"])
        incoming[edge["to"]].append(edge["from"])
    if _reachable(graph["entry"], outgoing) != ids:
        raise ValueError("Disconnected or unreachable graph node")
    terminals = {
        node["id"]
        for node in nodes
        if node["kind"] == "end" and node["id"] != graph["entry"]
    }
    # Every path must have a possible return to entry or an explicit exit.
    closed = set()
    for node in terminals | {graph["entry"]}:
        closed |= _reachable(node, incoming)
    if closed != ids:
        raise ValueError(
            f"Graph contains a path with no return/exit: {sorted(ids - closed)[:5]}"
        )


def _reachable(start: str, links: dict) -> set[str]:
    seen, pending = set(), deque([start])
    while pending:
        node = pending.popleft()
        if node in seen:
            continue
        seen.add(node)
        pending.extend(links.get(node, []))
    return seen
