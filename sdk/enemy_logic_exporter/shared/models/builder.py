"""Bind frozen control flow to resource values. No native binary is read here."""

from copy import deepcopy
import json
import re
from pathlib import Path
from ..logic.predicates import RuleRegistry
from ..logic.values import scalar
from ..resources.reader import Resources, ActionBindingError, structure_signature, typed
from ..logic.weights import choose_with_uint32, weighted_pool, candidate_node_id
from ..native.evidence import digest
from .io import load_model
from .audit import combat_entry_recovered
from ..logic.expressions import evaluate_expression, expression_unknown
from ..resources.action_names import ActionNames
from ..logic.common_conditions import recover_condition
from ..logic.commands import leaf_expression
from .player_view import build_player_view


def bind_skip_argument(body, index, expected_type, source):
    if type(index) is not int or not 0 <= index < len(body["_CommandArgArray"]):
        raise ValueError("随机筛选参数槽位无效")
    argument_type, argument = typed(body["_CommandArgArray"][index])
    if argument_type != expected_type or not argument_type.endswith(
        "cSetSkipActionTblArg"
    ):
        raise ValueError("随机筛选参数类型发生变化")
    entries = scalar(argument["_SkipActionTblList"])
    if not isinstance(entries, list):
        raise ValueError("跳过表列表结构未知")
    return dict(
        argument=argument,
        argumentType=argument_type,
        sourceResource=source,
        sourceBodyPointer=f"/_CommandArgArray/{index}/{argument_type}",
        skipTableReferences=[scalar(item) for item in entries],
    )


def bind_action_node(node, body, argument, resources, names):
    try:
        node["action"] = names.bind(resources.action(body, argument))
    except ActionBindingError as error:
        node.update(
            kind="unknown",
            reason=str(error),
            parameterBindingBoundary=error.context,
            summary="原生动作请求已确认；参数定义缺失",
        )
        return error.context
    return None


def referenced_enemy_names(graph, resources):
    """Official names of the EM IDs that resource arguments compare against."""
    names = {}
    for found in sorted(set(re.findall(r"\] (EM\d{4}_\d{2}_\d)", json.dumps(graph)))):
        try:
            names[found] = resources.enemy_name(found)["displayName"]
        except ValueError:
            pass
    return names


def build_chain(
    natives,
    template_path=None,
    *,
    metadata_path=None,
    rules_path=None,
    resources=None,
    model=None,
):
    registry = RuleRegistry.load(rules_path)
    if model is not None and template_path is not None:
        raise ValueError("只能指定内存模型或模型 JSON 文件之一")
    if model is None:
        if template_path is None:
            raise ValueError("需要怪物模块原生配方生成的模型或模型 JSON 文件")
        model = load_model(template_path)
    else:
        model = deepcopy(model)
    if model.get("schemaVersion") != 1 or model["profile"] != registry.data["profile"]:
        raise ValueError("表模板与判断规则的来源版本不匹配")
    metadata_status = "not_supplied"
    if metadata_path is not None:
        metadata_path = Path(metadata_path)
        if metadata_path.suffix.lower() != ".json":
            raise ValueError("版本核对只接受元数据 JSON")
        if digest(metadata_path) != model["profile"]["metadataSha256"]:
            raise ValueError("当前元数据版本与固化规则不匹配，需要重新核实")
        metadata_status = "matched"
    resources = resources if resources is not None else Resources(natives)
    resources.accessed.clear()
    names = ActionNames(
        resources, model["enemyId"], model.get("actionNameBindings", ())
    )
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
    prefix = "app.Em" + model["enemyId"][2:9] + "_"
    own_export = any(
        body["_ExportBTableType"].startswith(prefix) for body, _ in sources.values()
    )
    owner = "Em" + model["enemyId"][2:9]
    list_path = f"STM/GameDesign/Enemy/{owner[:6]}/{owner[7:]}/BTable/{owner}_BTableList.user.3.json"
    try:
        listed = resources.read(list_path)
    except FileNotFoundError:
        listed = None
    if listed is not None:
        declared = set(resources.table_references(listed, allow_missing=True))
        pending, visited = list(declared), set()
        pending.sort(key=lambda source: source not in sources, reverse=True)
        while set(sources) - declared and pending:
            source = pending.pop()
            if source in visited:
                continue
            visited.add(source)
            imports = set(
                resources.table_references(
                    resources.read(source)["_ImportBTableList"], allow_missing=True
                )
            )
            declared.update(imports)
            pending.extend(imports - visited)
        if set(sources) - declared:
            raise ValueError(
                "怪物模型使用了 BTableList 及导入资源之外的行为表，不能复制其他怪物的图"
            )
    elif not own_export:
        raise ValueError("怪物模型未绑定本怪物的行为资源，不能复制其他怪物的图")
    graph = deepcopy(model)
    if model.get("bindEnemyNameFromResources"):
        graph["enemyNameBinding"] = resources.enemy_name(model["enemyId"])
        graph["enemyName"] = graph["enemyNameBinding"]["displayName"]
    table_ids = {table["tableGuid"] for table in graph["tables"]}
    if graph["entry"] not in table_ids or len(table_ids) != len(graph["tables"]):
        raise ValueError("表入口无效或表 GUID 重复")
    unknown_conditions = 0
    action_binding_boundaries = []
    for table in graph["tables"]:
        source = table.get("resource") or model.get("resource")
        if source is not None and source not in sources:
            raise ValueError("子表引用未核实的资源")
        body, factories = sources[source] if source is not None else (None, None)
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
            if node["kind"] == "weighted_random":
                if body is None:
                    raise ValueError("随机筛选缺少实际资源绑定")
                if node.get("filteringMode") == "per_candidate":
                    for candidate in node["candidates"]:
                        bound = bind_skip_argument(
                            body,
                            candidate["skipArgumentIndex"],
                            candidate["expectedSkipArgumentType"],
                            source,
                        )
                        candidate.update(
                            skipArgument=bound["argument"],
                            skipArgumentType=bound["argumentType"],
                            skipSourceResource=source,
                            skipSourceBodyPointer=bound["sourceBodyPointer"],
                            skipTableReferences=bound["skipTableReferences"],
                        )
                else:
                    node.update(
                        bind_skip_argument(
                            body,
                            node["argumentIndex"],
                            node["expectedArgumentType"],
                            source,
                        )
                    )
                weighted_pool(node["candidates"])
                for candidate in node["candidates"]:
                    if (
                        candidate_node_id(candidate) not in node_ids
                        or candidate["targetTable"] not in table_ids
                    ):
                        raise ValueError("随机候选指向缺失位置")
                if node["fallback"] not in node_ids:
                    raise ValueError("随机回退位置缺失")
                continue
            if "argumentIndex" not in node:
                leaf = model.get("leafRules", {}).get(node.get("expectedCommandType"))
                recovered = None
                if (
                    node["kind"] == "condition"
                    and node.get("expectedCommandType")
                    and expression_unknown(node.get("expression", dict(kind="unknown")))
                ):
                    # Parameterless commands: the same reviewed recipes, no argument.
                    recovered = recover_condition(
                        dict(
                            node, commandType=node["expectedCommandType"], argument={}
                        ),
                        model["profile"],
                        model["enemyId"],
                        resources,
                    )
                    if recovered is not None:
                        node.update(recovered)
                if (
                    recovered is None
                    and node["kind"] == "condition"
                    and leaf
                    and not leaf["argumentField"]
                ):
                    expression = leaf_expression(leaf)
                    if expression is not None:
                        node.update(
                            expression=expression,
                            semanticStatus=leaf["semanticStatus"],
                            semanticEvidence=deepcopy(leaf["evidence"]),
                        )
                continue
            if body is None:
                raise ValueError("参数节点缺少经过核实的资源绑定")
            index = node["argumentIndex"]
            if type(index) is not int or not 0 <= index < len(body["_CommandArgArray"]):
                raise ValueError("参数槽位无效")
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
                if (
                    "expression" not in node
                    and node["predicate"]["status"] != "verified"
                ):
                    recovered = recover_condition(
                        node, model["profile"], model["enemyId"], resources
                    )
                    if recovered is not None:
                        node.update(recovered)
                    leaf = model.get("leafRules", {}).get(command_type)
                    if recovered is None and leaf and leaf["argumentType"] in (None, argument_type):
                        expression = leaf_expression(leaf, argument)
                        if expression is not None:
                            node.update(
                                expression=expression,
                                semanticStatus=leaf["semanticStatus"],
                                semanticEvidence=deepcopy(leaf["evidence"]),
                            )
                if node["predicate"].get("kind") == "timer":
                    node["timer"] = resources.timer(
                        body, node["predicate"]["values"]["variable"]
                    )
                unknown_conditions += node["predicate"]["status"] != "verified"
            elif node["kind"] == "action":
                boundary = bind_action_node(node, body, argument, resources, names)
                if boundary is not None:
                    action_binding_boundaries.append(
                        dict(
                            boundary,
                            tableGuid=table["tableGuid"],
                            node=node["id"],
                            requestSite=node.get("requestSite"),
                            sourceResource=source,
                        )
                    )
            elif node["kind"] == "mutation":
                if node["effect"] == "set_timer_state":
                    node["timerGuid"] = scalar(argument["_TargetVariableIndex"])
                    node["setType"] = scalar(argument["_SetType"])
                    node["timer"] = resources.timer(body, node["timerGuid"])
                elif node["effect"] == "set_float_value":
                    node["variableGuid"] = scalar(argument["_TargetVariableIndex"])
                    node["method"] = scalar(argument["_Method"])
                    node["value"] = scalar(argument["_Value"])
    # After binding: resource arguments name the compared enemies.
    graph["enemyNames"] = referenced_enemy_names(graph, resources)
    unknown_conditions = sum(
        (
            expression_unknown(node["expression"])
            if "expression" in node
            else node["predicate"]["status"] != "verified"
        )
        for table in graph["tables"]
        for node in table["nodes"]
        if node["kind"] == "condition"
    )
    for table in graph["tables"]:
        if any(
            node["kind"] == "condition"
            and (
                expression_unknown(node["expression"])
                if "expression" in node
                else node["predicate"]["status"] != "verified"
            )
            for node in table["nodes"]
        ):
            table["flowStatus"] = "partial"
    graph["rules"] = registry.data
    graph["actionBindingCoverage"] = dict(
        bound=sum(
            node["kind"] == "action"
            for table in graph["tables"]
            for node in table["nodes"]
        ),
        unresolved=len(action_binding_boundaries),
        boundaries=action_binding_boundaries,
    )
    graph["actionNameCatalog"] = names.catalog()
    graph["sources"] = sorted(resources.accessed)
    graph["metadataVerification"] = metadata_status
    graph["coverage"] = {
        "localTables": len(graph["tables"]),
        "nodes": sum(len(t["nodes"]) for t in graph["tables"]),
        "unknownConditions": unknown_conditions,
        "globalCombatEntryRecovered": combat_entry_recovered(graph),
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
    graph["playerView"] = build_player_view(graph)
    return graph


def trace_until_request(graph, context, *, position=None, max_steps=256):
    """Inspect a local path; stop on missing state, mutations, or an action request.

    Does not execute an action. A yielded request includes its continuation and
    caller stack, keeping separate request and resume contexts.
    """
    registry = RuleRegistry(graph["rules"])
    context = dict(context)
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
            outcome = (
                evaluate_expression(node["expression"], registry, context)
                if "expression" in node
                else registry.evaluate(node["predicate"], context)
            )
            path[-1]["truth"] = outcome.truth
            if outcome.truth is None:
                return {"status": "unknown", "reason": outcome.reason, "path": path}
            state = node["true" if outcome.truth else "false"]
        elif node["kind"] == "weighted_random":
            key = f"{table_id}:{state}"
            excluded = []
            if node.get("filteringMode") == "per_candidate":
                candidate_matches = context.get(
                    "candidate_skip_matches_current_action", {}
                ).get(key, {})
                for candidate in node["candidates"]:
                    if not candidate["skipTableReferences"]:
                        continue
                    matches = candidate_matches.get(candidate["id"])
                    if type(matches) is not bool:
                        return {
                            "status": "unknown",
                            "reason": "候选独立跳过列表缺少运行时字符串键匹配结果",
                            "path": path,
                        }
                    if matches:
                        excluded.append(candidate["id"])
            elif node["skipTableReferences"]:
                matches = context.get("skip_list_matches_current_action", {}).get(key)
                if type(matches) is not bool:
                    return {
                        "status": "unknown",
                        "reason": "非空跳过列表缺少运行时字符串键匹配结果",
                        "path": path,
                    }
                if matches:
                    excluded = [c["id"] for c in node["candidates"]]
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
            selection = choose_with_uint32(
                node["candidates"], draws[key], excluded=excluded
            )
            path[-1]["selection"] = selection
            candidate = next(c for c in node["candidates"] if c["id"] == selection)
            state = candidate_node_id(candidate)
        elif node["kind"] == "call":
            stack.append(
                {
                    "table": table_id,
                    "node": node["resume"],
                    **({"resultKey": node["resultKey"]} if "resultKey" in node else {}),
                }
            )
            table_id = node["targetTable"]
            state = tables[table_id]["entry"]
        elif node["kind"] == "return":
            if not stack:
                return {"status": "completed", "path": path}
            position = stack.pop()
            if "resultKey" in position:
                context[position["resultKey"]] = node["value"]
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
