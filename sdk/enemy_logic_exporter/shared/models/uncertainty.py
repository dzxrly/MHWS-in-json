"""Measure which player-tree conditions stay undecided, to steer rule work.

A condition is uncertain when its outcome cannot be decided even after every
player-settable input (distance, angle, anger, timers ...) is known: it still
depends on an ``unknown`` leaf or on a runtime key the scenario does not fix.
Random draws are probabilities, not uncertainty, and are counted separately.
"""

from collections import Counter
import json
from pathlib import Path

INPUT = "input"
GROUP = "与玩家战斗"


def evaluate(expression, scenario, inputs):
    op = expression.get("op")
    if op == "compare":
        key = expression["key"]
        if key in scenario:
            value, expected = scenario[key], expression["value"]
            if type(value) is not type(expected) and not (
                isinstance(value, (int, float)) and isinstance(expected, (int, float))
            ):
                return None
            return {
                "eq": value == expected,
                "ne": value != expected,
                "lt": value < expected,
                "le": value <= expected,
                "gt": value > expected,
                "ge": value >= expected,
            }[expression["operator"]]
        return INPUT if key in inputs else None
    if op == "not":
        result = evaluate(expression["item"], scenario, inputs)
        return result if result in (None, INPUT) else not result
    if op in ("all", "any"):
        results = [evaluate(item, scenario, inputs) for item in expression["items"]]
        dominant = op == "any"
        if dominant in results:
            return dominant
        if None in results:
            return None
        return INPUT if INPUT in results else not dominant
    return None


def reachable(view, group=GROUP):
    nodes, seen = view["nodes"], set()
    pending = [e["id"] for e in view["entries"] if e.get("group") == group]
    while pending:
        key = pending.pop()
        if key in seen or key not in nodes:
            continue
        seen.add(key)
        node = nodes[key]
        for role in ("true", "false", "next", "target", "resume", "fallback", "dispatch"):
            if node.get(role):
                pending.append(node[role])
        pending.extend(c["target"] for c in node.get("candidates", []))
    return seen


def measure(model):
    view = model["playerView"]
    raw = {
        f"{t['tableGuid']}/{n['id']}": n for t in model["tables"] for n in t["nodes"]
    }
    scenario, inputs = view["scenario"]["inputs"], view["inputs"]
    result = dict(conditions=0, random=0, uncertain=0, commands=Counter())
    for key in reachable(view):
        node = view["nodes"][key]
        if node["kind"] != "condition":
            continue
        result["conditions"] += 1
        if node.get("presentation", {}).get("category") == "random":
            result["random"] += 1
        elif evaluate(node["condition"], scenario, inputs) is None:
            result["uncertain"] += 1
            source = raw.get(key, {})
            command = source.get("commandType") or source.get("summary") or node["title"]
            result["commands"][str(command).rsplit(".", 1)[-1]] += 1
    return result


def uncertainty_report(models_dir, top=30):
    total = Counter()
    commands = Counter()
    monsters = {}
    for path in sorted(Path(models_dir).glob("em*.v*.json")):
        model = json.loads(path.read_text(encoding="utf8"))
        if model.get("storage"):
            raise ValueError("不确定性报告需要 .agents 中的完整研究模型")
        result = measure(model)
        commands.update(result.pop("commands"))
        total.update(result)
        monsters[model["enemyId"]] = result
    return dict(
        total=dict(total),
        monsters=monsters,
        topCommands=commands.most_common(top),
    )


def _unknown_reasons(expression, out):
    kind = expression.get("kind")
    if kind == "unknown":
        out.add(expression.get("reason", ""))
    elif kind == "predicate" and expression["predicate"].get("status") != "verified":
        out.add("规则未核实：" + str(expression["predicate"].get("status")))
    elif kind in ("all", "any"):
        for item in expression["items"]:
            _unknown_reasons(item, out)
    elif kind == "not":
        _unknown_reasons(expression["item"], out)


def unknown_census(models_dir, top=40):
    """Group every condition with an unknown part by command and by reason.

    Unlike ``uncertainty_report`` this covers all tables (ecology, other
    monsters, unattached parts), so it shows the largest classes to work on.
    The total equals the summed ``coverage.unknownConditions``.
    """
    from ..logic.expressions import expression_unknown

    commands, reasons, total = Counter(), Counter(), 0
    for path in sorted(Path(models_dir).glob("em*.v*.json")):
        model = json.loads(path.read_text(encoding="utf8"))
        if model.get("storage"):
            raise ValueError("分类统计需要 .agents 中的完整研究模型")
        for table in model["tables"]:
            for node in table["nodes"]:
                if node["kind"] != "condition":
                    continue
                expression = node.get("expression")
                if expression is None:
                    if node["predicate"].get("status") == "verified":
                        continue
                    found = {"规则未核实：" + str(node["predicate"].get("status"))}
                elif expression_unknown(expression):
                    found = set()
                    _unknown_reasons(expression, found)
                else:
                    continue
                total += 1
                command = node.get("commandType") or node.get("expectedCommandType")
                commands[str(command or "（命令外的流程条件）").rsplit(".", 1)[-1]] += 1
                reasons.update(reason[:80] for reason in found)
    return dict(
        unknownConditions=total,
        topCommands=commands.most_common(top),
        topReasons=reasons.most_common(top),
    )
