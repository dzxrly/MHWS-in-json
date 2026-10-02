"""Keep recovered control flow and expand moves without merging their contexts."""

from copy import deepcopy
import hashlib
import json
import math
import re

from src.processed_data.enemy_action_logic.actions import (
    ACTION_NAMES,
    action_group,
    action_label,
    resource_actions,
)
from src.processed_data.enemy_action_logic.graph import validate_graph
from src.processed_data.enemy_action_logic.source import ResourceCatalog


def graph_signature(graph: dict) -> str:
    """Imported presentation geometry is valid only for this exact projection."""
    geometry = {
        "nodes": [
            {
                **{key: node.get(key) for key in ("id", "label", "kind", "group")},
                "context": node.get("detail", {}).get("context"),
            }
            for node in graph["nodes"]
        ],
        "edges": [
            {key: edge.get(key) for key in ("from", "to", "label", "role", "back")}
            for edge in graph["edges"]
        ],
    }
    return hashlib.sha256(
        json.dumps(geometry, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _checked_cases(native: dict, known: set[str]) -> None:
    for case in native.get("decisionCases", []):
        lower, upper = case["distanceMin"], case["distanceMax"]
        if (
            not isinstance(lower, (int, float))
            or not math.isfinite(lower)
            or lower < 0
            or (
                upper is not None
                and (
                    not isinstance(upper, (int, float))
                    or not math.isfinite(upper)
                    or upper <= lower
                )
            )
            or case.get("distanceBasis") not in {"command", "player"}
            or {action["type"] for action in case["actions"]} - known
        ):
            raise ValueError("Invalid distance case or unknown candidate action type")


def player_graph(
    catalog: ResourceCatalog,
    native_graph: dict | None = None,
    *,
    phase_id: str | None = None,
) -> dict:
    if native_graph is None:
        return _resource_graph(catalog, phase_id or catalog.phases[0]["id"])
    graph = deepcopy(native_graph)
    graph.pop("layout", None)
    graph.pop("playerLayout", None)
    graph.pop("playerLayoutSignature", None)
    graph.update(mode="player_flow", basis="native_flow")
    graph["phaseDefinition"] = next(
        (row for row in catalog.phases if row["id"] == graph["id"]), {}
    )
    actions = resource_actions(catalog)
    known = {row["type"] for row in actions}
    known.update(row["type"] for row in graph.get("playerActions", []))
    known.update(
        node.get("detail", {}).get("actionType", "") for node in graph["nodes"]
    )
    _checked_cases(graph, known)
    by_argument = {
        (row["source"].casefold(), row["index"]): action
        for action in actions
        for row in action["sources"]
    }
    templates = [
        node for node in graph["nodes"] if node.get("detail", {}).get("requestSites")
    ]
    represented = []
    for template in templates:
        detail = template["detail"]
        incoming = [edge for edge in graph["edges"] if edge["to"] == template["id"]]
        outgoing = [edge for edge in graph["edges"] if edge["from"] == template["id"]]
        graph["nodes"].remove(template)
        graph["edges"] = [
            edge
            for edge in graph["edges"]
            if edge["to"] != template["id"] and edge["from"] != template["id"]
        ]
        for index, site in enumerate(detail["requestSites"]):
            action = deepcopy(
                by_argument.get((site["source"].casefold(), site["index"]))
            )
            if action is None or action["type"] != detail["actionType"]:
                raise ValueError(f"Native request does not match ActionID: {site}")
            for field in ("guid", "branchGuid", "assetIndex"):
                if field in site and action[field] != site[field]:
                    raise ValueError(f"Native request version mismatch: {site}")
            action["evidence"] = "native"
            action["requestSite"] = site
            action["context"] = site.get("context", template["id"])
            key = f"{template['id']}-v{index}"
            move = {
                "id": key,
                "label": action_label(action),
                "kind": "action",
                "evidence": "native",
                "group": template.get("group", action_group(action["type"])),
                "detail": {
                    "actionType": action["type"],
                    "variantId": action["variantId"],
                    "action": action,
                    "context": action["context"],
                    "executionUnresolved": detail.get(
                        "internalStatesUnresolved", False
                    ),
                },
            }
            graph["nodes"].append(move)
            represented.append(action)
            for edge in incoming:
                graph["edges"].append({**edge, "to": key})
            last = key
            for number, stage in enumerate(detail.get("execution", [])):
                stage_id = f"{key}-stage{number}"
                graph["nodes"].append(
                    {
                        "id": stage_id,
                        "label": stage["label"],
                        "kind": stage.get("kind", "process"),
                        "evidence": stage.get("evidence", "native"),
                        "group": move["group"],
                        "detail": {
                            "actionType": action["type"],
                            "context": action["context"],
                            "executionState": stage,
                        },
                    }
                )
                graph["edges"].append(
                    {
                        "from": last,
                        "to": stage_id,
                        "label": stage.get("condition", "本段完成"),
                        "evidence": stage.get("evidence", "native"),
                        "role": "execution",
                    }
                )
                last = stage_id
            exits = _execution_flow(graph, move, detail.get("executionFlow")) or [
                (last, "正常完成")
            ]
            continuation = site.get("continuation", detail.get("continuation"))
            if continuation:
                return_id = key + "-resume"
                target = continuation.get("target")
                graph["nodes"].append(
                    {
                        "id": return_id,
                        "label": continuation["label"],
                        "kind": "process" if target else "end",
                        "evidence": continuation.get("evidence", "unresolved"),
                        "group": move["group"],
                        "detail": {
                            "context": action["context"],
                            "continuation": continuation,
                            "requestSite": site,
                        },
                    }
                )
                for source, label in exits:
                    graph["edges"].append(
                        {
                            "from": source,
                            "to": return_id,
                            "label": label,
                            "evidence": "context",
                            "role": "completion",
                        }
                    )
                if target:
                    graph["edges"].append(
                        {
                            "from": return_id,
                            "to": target,
                            "label": continuation.get("edgeLabel", "继续本路径"),
                            "evidence": continuation.get("evidence", "unresolved"),
                            "role": "continuation",
                            "back": continuation.get("back", False),
                        }
                    )
                for edge in outgoing:
                    if edge.get("role") in {"interruption", "related"}:
                        graph["edges"].append({**edge, "from": key})
            else:
                for edge in outgoing:
                    graph["edges"].append({**edge, "from": last})
    if not templates:
        for node in graph["nodes"]:
            kind = node.get("detail", {}).get("actionType")
            if node["kind"] == "action" and kind:
                node["label"] = action_label({"type": kind})
                represented.append({"type": kind, "evidence": node["evidence"]})
    graph["playerActions"] = represented
    graph["coverage"] = {
        "displayedActionTypes": len({row["type"] for row in represented}),
        "actionRequestContexts": len(represented),
        "actionVersions": len(
            {row.get("variantId", row["type"]) for row in represented}
        ),
        "distanceCases": len(graph.get("decisionCases", [])),
        "complete": False,
    }
    graph.setdefault("limitations", []).extend(
        [
            "同一动作的参数版本与请求位置分别保留；候选调用关系不表示固定连招或发生概率。",
            "只有已恢复的条件与动作内部状态使用确定连接；尚未恢复的后续停在所属路径的未知返回点。",
            "中文名称按动作类型释义；循环计时与动画过滤器是源配置，未换算成实战持续秒数。",
        ]
    )
    if native_graph.get("playerLayoutSignature") == graph_signature(graph):
        graph["layout"] = deepcopy(native_graph["playerLayout"])
    validate_graph(graph)
    return graph


def _execution_flow(
    graph: dict, move: dict, flow: dict | None
) -> list[tuple[str, str]]:
    if not flow:
        return []
    prefix = move["id"] + "-state-"
    ids = {node["id"] for node in flow["nodes"]}
    if flow["entry"] not in ids or any(
        row["from"] not in ids or row["to"] not in ids for row in flow["edges"]
    ):
        raise ValueError("Invalid action execution flow")
    for node in flow["nodes"]:
        graph["nodes"].append(
            {
                **node,
                "id": prefix + node["id"],
                "group": move["group"],
                "detail": {
                    "actionType": move["detail"]["actionType"],
                    "context": move["detail"]["context"],
                    "executionState": node,
                },
            }
        )
    graph["edges"].append(
        {
            "from": move["id"],
            "to": prefix + flow["entry"],
            "label": "进入动作",
            "evidence": "native",
            "role": "execution",
        }
    )
    for edge in flow["edges"]:
        graph["edges"].append(
            {
                **edge,
                "from": prefix + edge["from"],
                "to": prefix + edge["to"],
                "role": "wait" if edge["from"] == edge["to"] else "execution",
            }
        )
    if any(exit["id"] not in ids for exit in flow["exits"]):
        raise ValueError("Unknown execution exit")
    return [
        (prefix + exit["id"], exit.get("label", "正常完成")) for exit in flow["exits"]
    ]


def _resource_graph(catalog: ResourceCatalog, phase: str) -> dict:
    match = re.search(r"PHASE_(\d+)", phase)
    definition = next(row for row in catalog.phases if row["id"] == phase)
    title = definition.get("title") or (
        f"阶段 {match[1]}" if match else "战斗阶段未解析"
    )
    actions = resource_actions(catalog)
    graph = {
        "id": phase,
        "title": title,
        "entry": "start",
        "mode": "player",
        "basis": "resource_candidates",
        "phaseDefinition": definition,
        "nodes": [],
        "edges": [],
        "limitations": [
            "距离、角度、状态、动作派生和阶段适用条件尚未恢复；本图只显示资源关联的动作版本。",
            "虚线是待恢复的关联，不能视为怪物实际执行顺序或选招概率。",
            "中文名称按类型释义；参数数组的相邻项不表示连招。",
        ],
    }
    if definition.get("note"):
        graph["limitations"].insert(0, definition["note"])
    graph["nodes"] = [
        {
            "id": "start",
            "label": f"玩家与怪物相距 x 米\n{title}",
            "kind": "end",
            "evidence": "context",
            "rank": 0,
            "detail": {"phaseDefinition": definition},
        },
        {
            "id": "select",
            "label": "距离、角度与状态分支待恢复\n以下是资源中可关联的动作版本",
            "kind": "unknown",
            "evidence": "unresolved",
            "rank": 1,
        },
        {
            "id": "unknown-return",
            "label": "正常完成／继续原流程／外层中断\n具体去向尚未恢复",
            "kind": "end",
            "evidence": "unresolved",
            "rank": 3,
        },
    ]
    graph["edges"].append({"from": "start", "to": "select", "evidence": "unresolved"})
    for index, action in enumerate(actions):
        key = f"move-{index}"
        graph["nodes"].append(
            {
                "id": key,
                "label": action_label(action),
                "kind": "action",
                "evidence": "resource",
                "rank": 2,
                "group": action_group(action["type"]),
                "detail": {
                    "action": action,
                    "actionType": action["type"],
                    "variantId": action["variantId"],
                },
            }
        )
        graph["edges"].extend(
            [
                {
                    "from": "select",
                    "to": key,
                    "evidence": "unresolved",
                    "role": "candidate",
                },
                {
                    "from": key,
                    "to": "unknown-return",
                    "evidence": "unresolved",
                    "role": "completion",
                },
            ]
        )
    if not actions:
        graph["edges"].append(
            {"from": "select", "to": "unknown-return", "evidence": "unresolved"}
        )
    graph["coverage"] = {
        "displayedActionTypes": len({row["type"] for row in actions}),
        "actionVersions": len(actions),
        "actionRequestContexts": len(actions),
        "distanceCases": 0,
        "complete": False,
    }
    graph["playerActions"] = actions
    graph["decisionCases"] = []
    validate_graph(graph)
    return graph
