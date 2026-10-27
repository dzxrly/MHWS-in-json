"""Attach reviewed target-command stages to the actual caller continuation."""

from copy import deepcopy


def attach_target_graph(machine, key, binding, detail, event, following, state):
    """An unresolved stage rejoins only through its declared normal return."""
    graph = detail["nativeGraph"]
    names = {name: key + "-" + name for name in graph["nodes"]}
    names[graph["entry"]] = key
    for name, node in graph["nodes"].items():
        machine.nodes[names[name]] = dict(
            deepcopy(node),
            **binding,
            id=names[name],
            semanticEvidence=deepcopy(detail["semanticEvidence"]),
            inputDefinitions=deepcopy(detail.get("inputDefinitions", {})),
            reviewedTargetCommand=True,
        )
    exits = {
        name: machine.walk(following, machine.complete_call(state, event, value))
        for name, value in graph["exits"].items()
    }
    for name in graph["nodes"]:
        node = machine.nodes[names[name]]
        for edge in ("true", "false", "next"):
            if edge in node:
                target = node[edge]
                node[edge] = names[target] if target in names else exits[target]
    return key
