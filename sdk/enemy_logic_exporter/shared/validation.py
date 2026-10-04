"""Validate frozen graph structure and provenance without game inputs."""

import re
from .scope import TRAINING_ENEMY_ID
from .weights import weighted_pool
from .values import scalar
from .audit import combat_entry_recovered, validate_native_evidence
from .expression_schema import validate_expression, expression_unknown
from .action_name_schema import validate_action_names


def validate_candidate_filters(node, source_hashes):
    mode = node.get("filteringMode")
    if mode not in (None, "shared", "per_candidate"):
        raise ValueError("随机候选筛选模式无效")
    if mode != "per_candidate":
        return
    if "argumentIndex" in node:
        raise ValueError("逐候选筛选不能绑定共同参数槽位")
    for candidate in node["candidates"]:
        index = candidate.get("skipArgumentIndex")
        argument_type = candidate.get("skipArgumentType", "")
        argument = candidate.get("skipArgument")
        raw_references = (
            scalar(argument.get("_SkipActionTblList"))
            if isinstance(argument, dict)
            else None
        )
        if (
            type(index) is not int
            or index < 0
            or argument_type != candidate.get("expectedSkipArgumentType")
            or not argument_type.endswith("cSetSkipActionTblArg")
            or not isinstance(candidate.get("skipArgument"), dict)
            or not isinstance(raw_references, list)
            or not isinstance(candidate.get("skipTableReferences"), list)
            or any(
                not isinstance(value, str) for value in candidate["skipTableReferences"]
            )
            or candidate.get("skipSourceResource") not in source_hashes
            or candidate.get("skipSourceBodyPointer")
            != f"/_CommandArgArray/{index}/{argument_type}"
        ):
            raise ValueError("随机候选缺少独立跳过列表与来源绑定")
        if candidate["skipTableReferences"] != [
            scalar(value) for value in raw_references
        ]:
            raise ValueError("随机候选的跳过列表与所绑定参数不一致")


def validate_graph(graph):
    validate_action_names(graph)
    if graph.get("documentType", "enemy_battle_logic") != "enemy_battle_logic":
        raise ValueError("正式图只接受语义行动模型，不能接受原生索引或资源清单")
    if graph.get("enemyId") == TRAINING_ENEMY_ID:
        raise ValueError("训练靶不能进入怪物行动图")
    if graph.get("schemaVersion") != 1 or not re.fullmatch(
        r"EM\d{4}_\d{2}_\d+", graph.get("enemyId", "")
    ):
        raise ValueError("行动图格式或怪物标识无效")
    profile = graph["profile"]
    if profile != graph["rules"]["profile"]:
        raise ValueError("行动图与规则的来源版本不匹配")
    if not profile.get("gameVersion") or any(
        not re.fullmatch(r"[0-9a-f]{64}", profile.get(key, ""))
        for key in ("exeSha256", "metadataSha256")
    ):
        raise ValueError("行动图来源版本证据无效")
    if graph["metadataVerification"] not in ("matched", "not_supplied"):
        raise ValueError("行动图元数据核对状态无效")
    if not graph.get("sourceHashes") or any(
        not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in graph["sourceHashes"].values()
    ):
        raise ValueError("行动图缺少资源来源证据")
    tables = {table["tableGuid"]: table for table in graph["tables"]}
    if (
        not tables
        or len(tables) != len(graph["tables"])
        or graph["entry"] not in tables
    ):
        raise ValueError("行动图子表重复或入口无效")
    node_count = random_count = unknown_count = unknown_conditions = complete_count = 0
    for table in tables.values():
        nodes = {node["id"]: node for node in table["nodes"]}
        if len(nodes) != len(table["nodes"]) or table["entry"] not in nodes:
            raise ValueError("行动图节点重复或子表入口无效")
        node_count += len(nodes)
        complete_count += table.get("flowStatus", "verified") == "verified"
        for node in nodes.values():
            required = {
                "condition": ("true", "false"),
                "action": ("resume",),
                "call": ("targetTable", "resume"),
                "mutation": ("next",),
                "weighted_random": ("candidates", "fallback"),
                "return": ("value",),
                "unknown": ("reason",),
            }
            if any(key not in node for key in required.get(node["kind"], ())):
                raise ValueError("行动图节点缺少必需的连接或字段")
            if node["kind"] not in {
                "condition",
                "action",
                "call",
                "mutation",
                "return",
                "weighted_random",
                "unknown",
            }:
                raise ValueError("行动图节点类型无效")
            for role in ("true", "false", "next", "resume"):
                if role in node and node[role] not in nodes:
                    raise ValueError("行动图连接指向缺失节点")
            if node["kind"] == "call" and (
                node["targetTable"] not in tables or "resume" not in node
            ):
                raise ValueError("行动图调用或恢复位置无效")
            if node.get("dispatchTarget") is not None and (
                node["kind"] != "mutation" or node["dispatchTarget"] not in tables
            ):
                raise ValueError("异步表请求指向缺失或无效目标")
            if node["kind"] == "action" and (
                "resume" not in node or not node.get("action", {}).get("actionClass")
            ):
                raise ValueError("行动图动作请求缺少动作绑定或恢复位置")
            if node["kind"] == "weighted_random":
                random_count += 1
                weighted_pool(node["candidates"])
                validate_candidate_filters(node, graph["sourceHashes"])
                if node["fallback"] not in nodes:
                    raise ValueError("行动图随机回退位置无效")
                for candidate in node["candidates"]:
                    target = nodes.get(candidate["id"], {})
                    if (
                        candidate["targetTable"] not in tables
                        or target.get("kind") != "call"
                        or target["targetTable"] != candidate["targetTable"]
                    ):
                        raise ValueError("行动图随机候选与调用连接不一致")
            if node["kind"] == "condition":
                if "expression" in node:
                    validate_expression(node["expression"])
                    unknown_conditions += expression_unknown(node["expression"])
                else:
                    unknown_conditions += node["predicate"]["status"] != "verified"
            if node["kind"] == "unknown":
                unknown_count += 1
                if not node.get("reason"):
                    raise ValueError("未知节点必须说明未核实的部分")
    expected = dict(
        localTables=len(tables),
        nodes=node_count,
        weightedSelections=random_count,
        unknownFlowNodes=unknown_count,
        unknownConditions=unknown_conditions,
        completeLocalTables=complete_count,
    )
    if any(
        type(graph["coverage"].get(key)) is not int or graph["coverage"][key] != value
        for key, value in expected.items()
    ):
        raise ValueError("行动图覆盖统计与实际节点不一致")
    for entry in graph.get("entryPoints", []):
        target = tables.get(entry.get("table"), {})
        if entry.get("node") not in {n["id"] for n in target.get("nodes", [])}:
            raise ValueError("行动图事件入口指向缺失位置")
        if entry.get("kind") not in {
            "local",
            "combat_enter",
            "combat_update",
            "interrupt",
            "resume",
            "combat_exit",
        }:
            raise ValueError("事件入口类别无效")
        if entry.get("status") not in {"verified", "partial"} or not entry.get(
            "evidence"
        ):
            raise ValueError("事件入口缺少核实状态或原生证据")
        validate_native_evidence(entry["evidence"])
    if graph["coverage"].get(
        "globalCombatEntryRecovered", False
    ) != combat_entry_recovered(graph):
        raise ValueError("战斗入口恢复标志与实际入口证据不一致")
