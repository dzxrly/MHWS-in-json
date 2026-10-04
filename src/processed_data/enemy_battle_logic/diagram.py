"""Combine every recovered table into one compound directed graph for ELK."""

from .viewer_labels import label
from .weights import candidate_node_id


def table_name(table, graph):
    if table.get("name"):
        return table["name"]
    resource = table.get("resource") or graph["resource"]
    kind = resource.rsplit("_BTable_", 1)[-1].split(".", 1)[0]
    return f"{kind} · 子表 {table['tableIndex']}"


def node_id(table_guid, local_id):
    return f"{table_guid}/{local_id}"


def combined_diagram(graph):
    tables = {table["tableGuid"]: table for table in graph["tables"]}
    groups, edges, details = [], [], {}

    def edge(source, target, role, text, **extra):
        edges.append(
            dict(
                id=f"edge-{len(edges)}",
                sources=[source],
                targets=[target],
                role=role,
                text=text,
                labels=[dict(text=text, width=max(26, len(text) * 13), height=20)],
                **extra,
            )
        )

    for table in graph["tables"]:
        guid = table["tableGuid"]
        children = []
        name = table_name(table, graph)
        for node in table["nodes"]:
            key = node_id(guid, node["id"])
            title, subtitle = label(node)
            if node["kind"] == "call":
                title = "调用 " + table_name(tables[node["targetTable"]], graph)
                subtitle = f"结束后恢复至本表节点 {node['resume']}"
            children.append(
                dict(
                    id=key,
                    width=330,
                    height=132,
                    kind=node["kind"],
                    title=title,
                    subtitle=subtitle,
                    localId=node["id"],
                    tableGuid=guid,
                    entry=node["id"] == table["entry"],
                )
            )
            details[key] = dict(
                node=node,
                table=name,
                tableGuid=guid,
                tableEvidence=table["evidence"],
                profile=graph["profile"],
            )
            for role, text in (
                ("true", "是"),
                ("false", "否"),
                ("next", "随后"),
                ("resume", "子表返回后" if node["kind"] == "call" else "动作结束后"),
            ):
                if role in node:
                    edge(
                        key,
                        node_id(guid, node[role]),
                        role,
                        text,
                        continuation=role == "resume",
                    )
            if node["kind"] == "call":
                target = tables[node["targetTable"]]
                edge(key, node_id(target["tableGuid"], target["entry"]), "call", "调用")
            if node["kind"] == "mutation" and node.get("dispatchTarget"):
                target = tables[node["dispatchTarget"]]
                edge(
                    key,
                    node_id(target["tableGuid"], target["entry"]),
                    "dispatch",
                    "请求切换（等待调度）",
                    asynchronous=True,
                )
            if node["kind"] == "weighted_random":
                for candidate in node["candidates"]:
                    edge(
                        key,
                        node_id(guid, candidate_node_id(candidate)),
                        "random",
                        f"权重 {candidate['weight']}",
                        candidateId=candidate["id"],
                        **{
                            name: candidate[name]
                            for name in ("nativeCandidateIndex", "nativeKey")
                            if name in candidate
                        },
                    )
                if "fallback" in node:
                    edge(key, node_id(guid, node["fallback"]), "fallback", "候选为空时")
        groups.append(
            dict(
                id=guid,
                title=name,
                entry=node_id(guid, table["entry"]),
                children=children,
                layoutOptions={"elk.padding": "[top=56,left=28,bottom=28,right=28]"},
            )
        )
    return {
        "layout": {
            "id": "monster",
            "layoutOptions": {
                "elk.algorithm": "layered",
                "elk.direction": "RIGHT",
                "elk.hierarchyHandling": "INCLUDE_CHILDREN",
                "elk.edgeRouting": "ORTHOGONAL",
                "elk.spacing.nodeNode": "44",
                "elk.layered.spacing.nodeNodeBetweenLayers": "72",
                "elk.spacing.edgeNode": "22",
                "elk.layered.mergeEdges": "false",
            },
            "children": groups,
            "edges": edges,
        },
        "details": details,
        "entry": node_id(graph["entry"], tables[graph["entry"]]["entry"]),
        "entryPoints": [
            dict(entry, target=node_id(entry["table"], entry["node"]))
            for entry in graph.get("entryPoints", [])
        ],
    }
