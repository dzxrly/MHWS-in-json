"""Compile reviewed graph semantics into JSON for a player-facing path reader.

No control-flow edge is inferred here. Calls and their saved return positions
remain explicit, and inputs describe one selection snapshot, not a game loop.
"""

import json
from pathlib import Path

from ..logic.values import enum_number, scalar
from ..logic.predicates import RuleRegistry
from ..logic.expressions import expression_unknown
from ..logic.weights import candidate_node_id
from ..resources.action_names import CLASS_EXPLANATIONS


def ref(table, node):
    return f"{table}/{node}"


def unknown(reason):
    return dict(op="unknown", reason=reason)


def comparison(key, operator, value):
    return dict(op="compare", key=key, operator=operator, value=value)


def distance_intervals(thresholds, *, maximum=None, unit="游戏距离值"):
    """Partition at exact boundaries; equality is never absorbed into a band."""
    points = sorted({0.0, *(float(v) for v in thresholds if v >= 0)})
    if maximum is not None:
        points = sorted({*points, float(maximum)})
    result = []
    for index, point in enumerate(points):
        result.append(
            dict(
                id=f"point:{point:g}",
                label=f"恰好 {point:g}",
                value=dict(min=point, max=point, minClosed=True, maxClosed=True),
            )
        )
        end = points[index + 1] if index + 1 < len(points) else maximum
        if end is None or end > point:
            result.append(
                dict(
                    id=f"band:{point:g}:{end}",
                    label=(
                        f"{point:g} ～ {end:g}（不含边界）"
                        if end is not None
                        else f"大于 {point:g}"
                    ),
                    value=dict(min=point, max=end, minClosed=False, maxClosed=False),
                )
            )
    return dict(unit=unit, options=result)


class PlayerCompiler:
    def __init__(self, graph):
        self.graph = graph
        self.inputs = {}
        self.thresholds = {}
        self.rules = {r["commandType"]: r for r in graph["rules"]["rules"]}
        identities = sorted(
            {
                (
                    n["action"]["source"],
                    n["action"]["actionGuid"],
                    n["action"]["parameterVariantGuid"],
                )
                for t in graph["tables"]
                for n in t["nodes"]
                if n["kind"] == "action"
            }
        )
        self.action_numbers = {
            identity: index + 1 for index, identity in enumerate(identities)
        }

    def boolean(self, key, label):
        self.inputs.setdefault(
            key,
            dict(
                label=label,
                options=[dict(label="是", value=True), dict(label="否", value=False)],
            ),
        )
        return comparison(key, "eq", True)

    def choices(self, key, label, options):
        self.inputs.setdefault(key, dict(label=label, options=options))

    def predicate(self, predicate):
        if predicate.get("status") != "verified":
            return unknown("此条件的判断方式尚未核实")
        kind, values = predicate.get("kind"), predicate.get("values", {})
        if kind == "battle_phase":
            value = enum_number(values["value"])
            options = self.rules[predicate["commandType"]]["enumValues"]
            self.choices(
                "battle_phase",
                "当前战斗阶段",
                [
                    dict(label=name.replace("PHASE_", "阶段 "), value=number)
                    for name, number in options.items()
                    if name.startswith("PHASE_")
                ],
            )
            return comparison("battle_phase", "eq", value)
        if kind == "distance":
            axis, base = enum_number(values["axis"]), enum_number(values["base"])
            if axis != 0 or base != 0:
                return unknown("此处还需要高度、空间距离或小队中心位置")
            modifiers = self.rules[predicate["commandType"]].get(
                "distanceModifiers", {}
            )
            states = modifiers.get("aiStateEnum", {})
            if states.get("COMBAT") == modifiers.get("triggerAIState") or not modifiers:
                return unknown("普通战斗的距离修正尚未核实")
            threshold = (
                float(values["threshold"]) * modifiers["defaultScale"]
                + modifiers["defaultOffset"]
            )
            key = "distance_horizontal"
            self.thresholds.setdefault(key, set()).add(threshold)
            operator = "lt" if enum_number(values["compare"]) == 0 else "gt"
            if enum_number(values["compare"]) not in (0, 1):
                return unknown("此距离比较尚未支持")
            return dict(
                op="all",
                items=[
                    comparison("ordinary_combat_snapshot", "eq", True),
                    comparison(key, operator, threshold),
                ],
            )
        if kind == "angle":
            if enum_number(values["option"]) or enum_number(values["option2"]):
                return unknown("此角度使用尚未核实的特殊判断")
            direction = {0: "前方", 1: "左方", 2: "右方", 3: "后方"}.get(
                enum_number(values["base"])
            )
            if direction is None:
                return unknown("此角度基准尚未核实")
            key = "angle_" + str(enum_number(values["base"]))
            threshold = float(values["width"]) / 2
            self.thresholds.setdefault(key, set()).add(threshold)
            self.inputs.setdefault(
                key, dict(label=f"目标相对{direction}的夹角", angle=True)
            )
            return comparison(key, "le", threshold)
        if kind == "self_status":
            category = enum_number(values["category"])
            if category == 3:
                status = enum_number(scalar(predicate["argument"]["Status"]))
                selected = {0: ("angry", "愤怒状态"), 1: ("tired", "疲劳状态")}.get(
                    status
                )
                if selected:
                    return self.boolean(*selected)
            if category == 1:
                holder = values["stand"]
                if enum_number(holder["STRUCT__Value_Type"]) == 0:
                    state = holder["STRUCT__Value_Value"]
                    self.choices(
                        "posture",
                        "普通姿态",
                        [dict(label="地面", value=0), dict(label="飞行", value=1)],
                    )
                    return dict(
                        op="all",
                        items=[
                            comparison("posture", "eq", state),
                            unknown("仍需确认没有覆盖普通姿态的特殊状态"),
                        ],
                    )
            if category == 4:
                self.inputs.setdefault(
                    "health_percent",
                    dict(label="生命值百分比", number=True, min=0, max=100, unit="%"),
                )
                return comparison("health_percent", "le", float(values["health"]))
        return unknown("此处需要额外的战斗状态或计时器信息")

    def expression(self, expression):
        kind = expression["kind"]
        if kind == "predicate":
            return self.predicate(expression["predicate"])
        if kind in ("all", "any"):
            return dict(
                op=kind, items=[self.expression(x) for x in expression["items"]]
            )
        if kind == "not":
            return dict(op="not", item=self.expression(expression["item"]))
        if kind in ("runtime", "compare"):
            operand = expression if kind == "runtime" else expression["left"]
            right = (
                dict(kind="constant", value=True)
                if kind == "runtime"
                else expression["right"]
            )
            keys = {
                "selected_target_key_type": ("selected_target_key_type", None),
                "selected_hunter_stun_active": ("hunter_stunned", "玩家眩晕"),
                "environment_current_rank": ("quest_rank", "任务等级"),
                "self_basic_legendary_id": ("legendary_id", "怪物历战分类"),
            }
            key = operand.get("key")
            if (
                operand.get("kind") == "runtime"
                and key in keys
                and right.get("kind") == "constant"
            ):
                mapped, label = keys[key]
                if mapped == "hunter_stunned":
                    self.boolean(mapped, label)
                elif label:
                    self.inputs.setdefault(mapped, dict(label=label, options=[]))
                    option = dict(label=str(right["value"]), value=right["value"])
                    if option not in self.inputs[mapped]["options"]:
                        self.inputs[mapped]["options"].append(option)
                return comparison(
                    mapped, expression.get("operator", "eq"), right["value"]
                )
        return unknown("此处需要尚未提供或尚未核实的内部条件")

    def condition(self, node):
        result = (
            self.expression(node["expression"])
            if "expression" in node
            else self.predicate(node["predicate"])
        )
        text = self.describe(result)
        return result, text

    def describe(self, expression):
        op = expression["op"]
        if op == "compare":
            key, value = expression["key"], expression["value"]
            if key == "ordinary_combat_snapshot":
                return "仍是本次普通战斗选招"
            if key == "selected_target_key_type":
                return "当前目标是玩家"
            label = self.inputs.get(key, {}).get("label", "距离")
            if key == "distance_horizontal":
                label = "玩家与怪物的水平距离"
            operator = {
                "lt": "<",
                "le": "≤",
                "gt": ">",
                "ge": "≥",
                "eq": "=",
                "ne": "≠",
            }[expression["operator"]]
            if type(value) is bool:
                positive = value if expression["operator"] == "eq" else not value
                return label + ("成立" if positive else "不成立")
            if key == "battle_phase" and expression["operator"] == "eq":
                return f"当前为阶段 {value + 1}" if 0 <= value <= 4 else "指定战斗阶段"
            if key == "posture":
                return "处于" + {0: "地面", 1: "飞行"}.get(value, "指定") + "姿态"
            return (
                f"{label} {operator} {value:g}"
                if isinstance(value, (int, float))
                else f"{label} {operator} {value}"
            )
        if op in ("all", "any"):
            items = [
                self.describe(x)
                for x in expression["items"]
                if x.get("key") != "ordinary_combat_snapshot"
            ]
            items = list(dict.fromkeys(items))
            if len(items) == 1:
                return items[0]
            return ("，并且" if op == "all" else "，或者").join(items)
        if op == "not":
            return "不满足：" + self.describe(expression["item"])
        return expression["reason"]

    def presentation(self, condition):
        """Labels describe both outcomes; ordinary-selection guards stay explicit."""
        parts = (
            condition.get("items", [condition])
            if condition["op"] == "all"
            else [condition]
        )
        shown = [p for p in parts if p.get("key") != "ordinary_combat_snapshot"]
        comparisons = [p for p in shown if p["op"] == "compare"]
        keys = {p["key"] for p in comparisons}
        category = (
            "distance"
            if "distance_horizontal" in keys
            else (
                "angle"
                if any(k.startswith("angle_") for k in keys)
                else (
                    "phase"
                    if "battle_phase" in keys
                    else "state" if keys - {"selected_target_key_type"} else "internal"
                )
            )
        )
        if len(shown) == 1 and len(comparisons) == 1:
            test = comparisons[0]
            reverse = {
                "lt": "ge",
                "le": "gt",
                "gt": "le",
                "ge": "lt",
                "eq": "ne",
                "ne": "eq",
            }
            negative = dict(test, operator=reverse[test["operator"]])
            title = self.inputs.get(test["key"], {}).get("label", "目标检查")
            if test["key"] == "distance_horizontal":
                title = "玩家与怪物的水平距离"
            true_label, false_label = self.describe(test), self.describe(negative)
            if test["key"] == "battle_phase":
                false_label = "其他阶段"
        else:
            title = (
                self.describe(condition) if category != "internal" else "额外状态条件"
            )
            true_label, false_label = "满足上述条件", "不满足上述条件"
        return dict(
            category=category,
            title=title,
            trueLabel=true_label,
            falseLabel=false_label,
            snapshotGuard=len(shown) != len(parts),
            compact=category == "internal",
        )

    def node(self, table, node):
        kind = node["kind"]
        result = dict(kind=kind, sourceRef=ref(table, node["id"]))
        for role in ("true", "false", "next", "resume", "fallback"):
            if role in node:
                result[role] = ref(table, node[role])
        if kind == "condition":
            result["condition"], result["title"] = self.condition(node)
            result["presentation"] = self.presentation(result["condition"])
            result["executionGuard"] = node.get("summary", "").startswith(
                ("有效命令工作", "当前 actor")
            )
        elif kind == "action":
            action = node["action"]
            name = action.get("displayName", "")
            if name == action["actionClass"]:
                name = CLASS_EXPLANATIONS.get(name)
            identity = (
                action["source"],
                action["actionGuid"],
                action["parameterVariantGuid"],
            )
            result["title"] = name or f"未命名动作 {self.action_numbers[identity]:02d}"
            result["nameStatus"] = "explanatory" if name else "unresolved"
            result["identity"] = [
                action["source"],
                action["actionGuid"],
                action["parameterVariantGuid"],
            ]
            result["note"] = "动作请求；执行结果仍受游戏状态影响。"
        elif kind == "call":
            target = next(
                t for t in self.graph["tables"] if t["tableGuid"] == node["targetTable"]
            )
            result.update(
                title="继续判断", target=ref(target["tableGuid"], target["entry"])
            )
            if "resultKey" in node:
                result["resultKey"] = node["resultKey"]
        elif kind == "weighted_random":
            result.update(
                title="从仍可用的候选中选择",
                candidates=[
                    dict(
                        id=c["id"],
                        target=ref(table, candidate_node_id(c)),
                        weight=c["weight"],
                        filteringUnknown=bool(
                            c.get(
                                "skipTableReferences",
                                node.get("skipTableReferences", []),
                            )
                        ),
                    )
                    for c in node["candidates"]
                ],
                note="这里只展示当前选择的权重。候选排除和随机结果未知时保留全部可能分支。",
            )
        elif kind == "return":
            result.update(title="结束本段判断，返回此前流程", value=node.get("value"))
        elif kind == "mutation":
            effect = node["effect"]
            titles = {
                "set_destination": "调整移动目标",
                "set_timer_state": "更新出招计时",
                "set_float_value": "更新行为记录",
                "request_btable": "等待切换战斗流程",
                "yield_without_action_request": "本次动作请求被暂缓",
                "request_actor_helper_skipped_then_yield": "等待动作调度",
            }
            result.update(title=titles.get(effect, "更新战斗状态"), effect=effect)
            result["invalidateSnapshot"] = effect not in (
                "set_destination",
                "set_timer_state",
                "set_float_value",
            )
            if (
                effect == "write_context_field"
                and node.get("nativeField")
                == "app.cEmModuleUnfair.<IsActiveUnfairRoutine>k__BackingField"
            ):
                result["invalidateSnapshot"] = False
            if (
                effect == "write_context_field"
                and node.get("nativeField")
                == "app.cEmModuleUnfair.<IsActiveUnfairRoutine>k__BackingField"
            ):
                result["invalidateSnapshot"] = False
            if node.get("dispatchTarget"):
                target = next(
                    t
                    for t in self.graph["tables"]
                    if t["tableGuid"] == node["dispatchTarget"]
                )
                result["dispatch"] = ref(target["tableGuid"], target["entry"])
        else:
            result.update(
                title="此处仍有未核实的战斗逻辑",
                note="接入关系、判断或副作用需要继续核查。",
                invalidateSnapshot=True,
            )
            if "resume" in node and node.get("parameterBindingBoundary"):
                result.update(
                    title="动作身份待核查",
                    note="动作请求与保存的继续位置已恢复，具体动作参数尚未对应。",
                )
            if "resume" in node and node.get("parameterBindingBoundary"):
                result.update(
                    title="动作身份待核查",
                    note="动作请求与保存的继续位置已恢复，具体动作参数尚未对应。",
                )
        return result


def successors(node):
    result = [
        node[k]
        for k in ("true", "false", "next", "resume", "fallback", "target", "dispatch")
        if k in node
    ]
    return result + [c["target"] for c in node.get("candidates", [])]


def reachable(nodes, start):
    seen, pending = set(), [start]
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        pending.extend(successors(nodes[key]))
    return seen


def build_player_view(graph):
    compiler = PlayerCompiler(graph)
    nodes = {
        ref(t["tableGuid"], n["id"]): compiler.node(t["tableGuid"], n)
        for t in graph["tables"]
        for n in t["nodes"]
    }
    tables = {t["tableGuid"]: t for t in graph["tables"]}
    local = graph.get("localBattleEntry", graph["entry"])
    main = ref(local, tables[local]["entry"])
    connected = reachable(nodes, main)
    entries = [
        dict(
            id=main,
            label="普通战斗选招",
            relation="local_verified",
            note="从本怪物已恢复的 Combat 选招入口开始；进入战斗的全部过程仍有未知部分。",
        )
    ]
    # A native dispatcher entry proves a local entry, not its upstream scheduling.
    for source, entry in graph.get("resourceEntries", {}).items():
        if "_CommonAttack." not in source or entry.get("tableGuid") not in tables:
            continue
        t = tables[entry["tableGuid"]]
        key = ref(t["tableGuid"], t["entry"])
        if key not in connected:
            entries.append(
                dict(
                    id=key,
                    label="普通攻击局部入口（接入位置待核查）",
                    relation="unknown",
                    note="该局部入口来自本资源调度器。不能据此断言普通战斗会在当前条件下进入这里。",
                )
            )
    covered = set(connected)
    for entry in entries[1:]:
        covered.update(reachable(nodes, entry["id"]))
    incoming = {target for n in nodes.values() for target in successors(n)}
    candidates = [
        t
        for t in graph["tables"]
        if any(part in t.get("resource", "") for part in ("_Combat.", "_CommonAttack."))
    ]
    for t in sorted(
        candidates,
        key=lambda t: (ref(t["tableGuid"], t["entry"]) in incoming, t["tableGuid"]),
    ):
        key = ref(t["tableGuid"], t["entry"])
        if key in covered:
            continue
        branch = reachable(nodes, key)
        if not any(nodes[n]["kind"] == "action" for n in branch):
            continue
        names = list(
            dict.fromkeys(
                nodes[n]["title"]
                for n in sorted(branch)
                if nodes[n]["kind"] == "action"
            )
        )
        entries.append(
            dict(
                id=key,
                label="局部分支：" + "、".join(names[:2]) + "（接入待核查）",
                relation="unknown",
                note="保留已恢复的本地条件与动作；上游入口尚未接通。",
            )
        )
        covered.update(branch)
    for key, thresholds in compiler.thresholds.items():
        field = compiler.inputs.setdefault(key, dict(label="水平距离"))
        field.update(
            distance_intervals(
                thresholds,
                maximum=180 if field.get("angle") else None,
                unit="度" if field.get("angle") else "游戏距离值",
            )
        )
        field["numericRange"] = dict(min=0, max=180 if field.get("angle") else None)
        field["numericRange"] = dict(min=0, max=180 if field.get("angle") else None)
    return dict(
        schemaVersion=1,
        scenario=dict(
            label="当前目标是该玩家，怪物正在普通战斗中选招",
            inputs=dict(selected_target_key_type=0, ordinary_combat_snapshot=True),
        ),
        inputs=compiler.inputs,
        entries=entries,
        nodes=nodes,
        coverage=dict(
            connectedNodes=len(connected),
            connectedActions=sum(nodes[k]["kind"] == "action" for k in connected),
            unattachedEntries=len(entries) - 1,
        ),
        limits=[
            "初始条件只筛选第一次选招。动作执行或等待后，后续条件需要重新判断。",
            "距离采用游戏判断值，尚未确认与米的换算。",
            "接入位置未恢复的局部流程不计入已知入口的下一招。",
        ],
    )


def enrich_models(models, output):
    """Add player semantics to already extracted JSON; native provenance is unchanged."""
    models, output = Path(models), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    paths = sorted(models.glob("em*.v*.json"))
    if not paths:
        raise ValueError("没有已提取的怪物图 JSON")
    for path in paths:
        graph = json.loads(path.read_text(encoding="utf8"))
        if graph.get("artifactKind") != "extracted_battle_graph":
            raise ValueError("玩家视图只接受已提取的语义图")
        registry = RuleRegistry.load()
        if registry.data["profile"] != graph["profile"]:
            raise ValueError("当前玩家配方与模型来源版本不同")
        for table in graph["tables"]:
            for node in table["nodes"]:
                if (
                    node["kind"] == "condition"
                    and node.get("commandType")
                    == "app.btable.Em0166_00BTableCommand.cCheckBattlePhase"
                ):
                    if graph["enemyId"] != "EM0166_00_0":
                        raise ValueError("EM166 阶段配方不能用于其他怪物")
                    node["predicate"] = registry.bind(
                        node["commandType"], node["argumentType"], node["argument"]
                    )
        graph["rules"] = registry.data
        graph["coverage"]["unknownConditions"] = sum(
            (
                expression_unknown(n["expression"])
                if "expression" in n
                else n["predicate"].get("status") != "verified"
            )
            for t in graph["tables"]
            for n in t["nodes"]
            if n["kind"] == "condition"
        )
        refresh_action_names(graph)
        graph["playerView"] = build_player_view(graph)
        (output / path.name).write_text(
            json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
        )
        print("PLAYER", graph["enemyId"], graph["playerView"]["coverage"], flush=True)


def refresh_action_names(graph):
    """Use the existing descriptive-name policy, keeping exact identity bindings."""
    bindings = {}
    for table in graph["tables"]:
        for node in table["nodes"]:
            if node["kind"] != "action":
                continue
            action = node["action"]
            binding = action.get("nameBinding")
            if not binding:
                continue
            name = CLASS_EXPLANATIONS.get(action["actionClass"])
            if name and binding.get("origin") == "technical_class_name":
                action["displayName"] = name
                binding.update(displayName=name, origin="action_class_explanation")
            identity = (
                action["source"],
                action["actionGuid"],
                action["parameterVariantGuid"],
            )
            bindings[identity] = binding
    if graph.get("actionNameCatalog") is not None:
        graph["actionNameCatalog"]["bindings"] = list(bindings.values())
