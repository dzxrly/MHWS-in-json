"""Short-circuit conditions bound by the current resource order-bank hashes."""

import json
from functools import lru_cache

from ..config import EVIDENCE_DIR
from ..resources.reader import typed
from .commands import leaf_expression
from .common_conditions import recover_condition


@lru_cache(maxsize=1)
def receipt():
    return json.loads(
        (EVIDENCE_DIR / "compound_conditions.v1.json").read_text(encoding="utf8")
    )


def verify_compound_conditions(pe, metadata):
    for row in receipt()["methods"]:
        method = (metadata.get(row["type"]) or {}).get("methods", {}).get(row["method"])
        if not method or int(method["function"], 16) != int(row["address"], 16):
            raise ValueError("组合条件的原生方法身份变化")
        native = bytes.fromhex(row["bytes"])
        if pe.read(int(row["address"], 16), len(native)) != native:
            raise ValueError("组合条件的原生字节变化")


def recover_compound_condition(node, enemy_id, resources, body, registry, leaves):
    commands = receipt()["commands"]
    if node.get("commandType") not in commands:
        return None
    factories = resources.factories_by_hash(body)
    evidence, definitions = [], {}

    def recover(command, argument_type, argument, depth=0):
        if depth > 16:
            raise ValueError("组合条件嵌套超过核实范围")
        if command in commands:
            spec = commands[command]
            if argument_type != spec["argumentType"]:
                raise ValueError("组合条件的参数类型变化")
            evidence.append(
                {
                    k: v
                    for k, v in receipt()["methods"][spec["methodIndex"]].items()
                    if k != "bytes"
                }
            )
            items = []
            for wrapper in argument["argumentCommands"]:
                _, child = typed(wrapper)
                identity = child["_ArgumentCommandHash"]
                factory = factories.get(identity)
                if factory is None:
                    items.append(
                        dict(
                            kind="unknown",
                            reason=f"组合条件的命令哈希未绑定：{identity}",
                        )
                    )
                    continue
                child_type, child_arg = typed(child["_ArgumentCommandArgument"])
                if child_type != factory["_ArgumentType"]:
                    raise ValueError("组合条件子命令的资源参数类型不匹配")
                items.append(
                    recover(factory["_OrderType"], child_type, child_arg, depth + 1)
                )
            # Both current native implementations return false for an empty list.
            return (
                dict(kind=spec["operator"], items=items)
                if items
                else dict(kind="constant", value=False)
            )
        predicate = registry.bind(command, argument_type, argument)
        if predicate.get("status") == "verified":
            return dict(kind="predicate", predicate=predicate)
        child = dict(commandType=command, argumentType=argument_type, argument=argument)
        recovered = recover_condition(child, enemy_id, resources)
        if recovered is not None:
            evidence.extend(recovered.get("semanticEvidence", []))
            definitions.update(recovered.get("inputDefinitions", {}))
            return recovered["expression"]
        leaf = leaves.get(command)
        if leaf and leaf.get("argumentType") in (None, argument_type):
            expression = leaf_expression(leaf, argument)
            if expression is not None:
                return expression
        return dict(kind="unknown", reason="组合条件子命令尚未核实：" + command)

    expression = recover(node["commandType"], node["argumentType"], node["argument"])
    return dict(
        expression=expression,
        semanticEvidence=evidence,
        inputDefinitions=definitions,
        summary="依次检查组合条件",
        semanticStatus="verified_compound_command_with_bounded_children",
    )
