"""Bind frozen control flow to resource values. No native binary is read here."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .predicates import RuleRegistry, scalar
from .resources import Resources, structure_signature, typed
from .random_choice import choose_with_uint32, weighted_pool
from .definitions import DEFAULT_TEMPLATE


def build_chain(natives, template_path=None, *, metadata_path=None, rules_path=None):
    registry = RuleRegistry.load(rules_path)
    if template_path is None:
        template_path = DEFAULT_TEMPLATE
    model = json.loads(Path(template_path).read_text(encoding="utf-8"))
    if model.get("schemaVersion") != 1 or model["profile"] != registry.data["profile"]:
        raise ValueError("表模板与判断规则的来源版本不匹配")
    metadata_status = "not_supplied"
    if metadata_path is not None:
        metadata_path = Path(metadata_path)
        if metadata_path.suffix.lower() != ".json":
            raise ValueError("版本核对只接受元数据 JSON")
        digest = hashlib.sha256()
        with metadata_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != model["profile"]["metadataSha256"]:
            raise ValueError("当前元数据版本与固化规则不匹配，需要重新核实")
        metadata_status = "matched"
    resources = Resources(natives)
    definitions = model.get("resources") or {
        model["resource"]: {"structureSignature": model["structureSignature"]}
    }
    sources = {}
    for source, definition in definitions.items():
        body = resources.read(source)
        factories = resources.factories(body)
        if structure_signature(body, factories) != definition["structureSignature"]:
            raise ValueError("行为表结构与固化模板不匹配，必须重新核实原生控制流")
        sources[source] = body, factories
    graph = deepcopy(model)
    table_ids = {table["tableGuid"] for table in graph["tables"]}
    if graph["entry"] not in table_ids or len(table_ids) != len(graph["tables"]):
        raise ValueError("表入口无效或表 GUID 重复")
    unknown_conditions = 0
    for table in graph["tables"]:
        source = table.get("resource", model["resource"])
        if source not in sources:
            raise ValueError("子表引用未核实的资源")
        body, factories = sources[source]
        node_ids = {node["id"] for node in table["nodes"]}
        if len(node_ids) != len(table["nodes"]) or table["entry"] not in node_ids:
            raise ValueError("节点重复或局部入口无效")
        for node in table["nodes"]:
            for role in ("true", "false", "next", "resume"):
                if role in node and node[role] not in node_ids:
                    raise ValueError(
                        f"连接指向缺失节点：{table['tableGuid']}:{node['id']}"
                    )
            if node["kind"] == "call" and node["targetTable"] not in table_ids:
                raise ValueError("子表未固化，不能伪造调用关系")
            if "argumentIndex" not in node:
                continue
            index = node["argumentIndex"]
            if type(index) is not int or not 0 <= index < len(body["_CommandArgArray"]):
                raise ValueError("参数槽位无效")
            if node["kind"] == "weighted_random":
                argument_type, argument = typed(body["_CommandArgArray"][index])
                if argument_type != node["expectedArgumentType"]:
                    raise ValueError("随机筛选参数类型发生变化")
                node["argument"] = argument
                node["argumentType"] = argument_type
                node["sourceResource"] = source
                node["sourceBodyPointer"] = f"/_CommandArgArray/{index}/{argument_type}"
                entries = scalar(argument["_SkipActionTblList"])
                if not isinstance(entries, list):
                    raise ValueError("跳过表列表结构未知")
                node["skipTableReferences"] = [scalar(item) for item in entries]
                weighted_pool(node["candidates"])
                for candidate in node["candidates"]:
                    if (
                        candidate["id"] not in node_ids
                        or candidate["targetTable"] not in table_ids
                    ):
                        raise ValueError("随机候选指向缺失位置")
                if node["fallback"] not in node_ids:
                    raise ValueError("随机回退位置缺失")
                continue
            slot = node["commandIndex"]
            if type(index) is not int or type(slot) is not int or index < 0 or slot < 0:
                raise ValueError("参数或命令槽位无效")
            argument_type, argument = typed(body["_CommandArgArray"][index])
            command_type = factories[slot]["_OrderType"]
            if (
                argument_type != node["expectedArgumentType"]
                or command_type != node["expectedCommandType"]
            ):
                raise ValueError("原生命令与资源绑定发生变化")
            node["argument"] = argument
            node["argumentType"] = argument_type
            node["commandType"] = command_type
            node["sourceBodyPointer"] = f"/_CommandArgArray/{index}/{argument_type}"
            node["sourceResource"] = source
            if node["kind"] == "condition":
                node["predicate"] = registry.bind(command_type, argument_type, argument)
                if node["predicate"].get("kind") == "timer":
                    node["timer"] = resources.timer(
                        body, node["predicate"]["values"]["variable"]
                    )
                unknown_conditions += node["predicate"]["status"] != "verified"
            elif node["kind"] == "action":
                node["action"] = resources.action(body, argument)
            elif node["kind"] == "mutation":
                if node["effect"] == "set_timer_state":
                    node["timerGuid"] = scalar(argument["_TargetVariableIndex"])
                    node["setType"] = scalar(argument["_SetType"])
                    node["timer"] = resources.timer(body, node["timerGuid"])
                elif node["effect"] == "set_float_value":
                    node["variableGuid"] = scalar(argument["_TargetVariableIndex"])
                    node["method"] = scalar(argument["_Method"])
                    node["value"] = scalar(argument["_Value"])
    graph["rules"] = registry.data
    graph["sourceHashes"] = dict(sorted(resources.hashes.items()))
    graph["metadataVerification"] = metadata_status
    graph["coverage"] = {
        "localTables": len(graph["tables"]),
        "nodes": sum(len(t["nodes"]) for t in graph["tables"]),
        "unknownConditions": unknown_conditions,
        "globalCombatEntryRecovered": False,
        "weightedSelections": sum(
            n["kind"] == "weighted_random" for t in graph["tables"] for n in t["nodes"]
        ),
        "unknownFlowNodes": sum(
            n["kind"] == "unknown" for t in graph["tables"] for n in t["nodes"]
        ),
        "resourceTables": len(sources),
        "completeLocalTables": sum(
            t.get("flowStatus", "verified") == "verified" for t in graph["tables"]
        ),
    }
    return graph


def trace_until_request(graph, context, *, position=None, max_steps=256):
    """Inspect a local path; stop on missing state, mutations, or an action request.

    Does not execute an action. A yielded request includes its continuation and
    caller stack, keeping separate request and resume contexts.
    """
    registry = RuleRegistry(graph["rules"])
    tables = {t["tableGuid"]: t for t in graph["tables"]}
    if position is None:
        table_id = graph["entry"]
        state, stack = tables[table_id]["entry"], []
    else:
        table_id, state = position["table"], position["node"]
        stack = deepcopy(position.get("stack", []))
    path = []
    for _ in range(max_steps):
        table = tables.get(table_id)
        if table is None:
            raise ValueError("未知表位置")
        nodes = {n["id"]: n for n in table["nodes"]}
        if state not in nodes:
            raise ValueError("未知节点位置")
        node = nodes[state]
        path.append({"table": table_id, "node": state, "kind": node["kind"]})
        if node["kind"] == "condition":
            outcome = registry.evaluate(node["predicate"], context)
            path[-1]["truth"] = outcome.truth
            if outcome.truth is None:
                return {"status": "unknown", "reason": outcome.reason, "path": path}
            state = node["true" if outcome.truth else "false"]
        elif node["kind"] == "weighted_random":
            key = f"{table_id}:{state}"
            if node["skipTableReferences"]:
                matches = context.get("skip_list_matches_current_action", {}).get(key)
                if type(matches) is not bool:
                    return {
                        "status": "unknown",
                        "reason": "非空跳过列表缺少运行时字符串键匹配结果",
                        "path": path,
                    }
            else:
                matches = False
            excluded = [c["id"] for c in node["candidates"]] if matches else []
            pool = weighted_pool(node["candidates"], excluded=excluded)
            if not pool:
                state = node["fallback"]
                path[-1]["selection"] = "empty_pool_fallback"
                continue
            draws = context.get("random_draws", {})
            if key not in draws:
                return {
                    "status": "random_draw_required",
                    "pool": pool,
                    "path": path,
                    "position": {"table": table_id, "node": state, "stack": stack},
                    "reason": "候选权重已确定；需要原生 uint32 抽样值才能选择具体分支",
                }
            state = choose_with_uint32(
                node["candidates"], draws[key], excluded=excluded
            )
            path[-1]["selection"] = state
        elif node["kind"] == "call":
            stack.append({"table": table_id, "node": node["resume"]})
            table_id = node["targetTable"]
            state = tables[table_id]["entry"]
        elif node["kind"] == "return":
            if not stack:
                return {"status": "completed", "path": path}
            position = stack.pop()
            table_id, state = position["table"], position["node"]
        elif node["kind"] == "action":
            return {
                "status": "action_requested",
                "action": node["action"],
                "path": path,
                "continuation": {
                    "table": table_id,
                    "node": node["resume"],
                    "stack": stack,
                },
            }
        elif node["kind"] == "mutation":
            return {
                "status": "state_change_required",
                "mutation": node,
                "path": path,
                "continuation": {
                    "table": table_id,
                    "node": node["next"],
                    "stack": stack,
                },
            }
        else:
            return {
                "status": "unknown",
                "reason": node.get("reason", "未实现节点语义"),
                "path": path,
            }
    return {"status": "unknown", "reason": "达到步数限制，可能存在循环", "path": path}
