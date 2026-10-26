"""Build reviewed conditions that only combine plain field comparisons.

Monster modules declare, per command, a small tree read from the native code:

- ``("all" | "any", *items)`` and ``("not", item)``;
- ``(field,)``: a boolean field is true;
- ``(field, operator, value)``: an integer/enum field compared with a constant.

A field is ``"extend:<path>"`` (relative to the monster's Extend type), a
``"context:<path>"`` under cEnemyContext, or a plain runtime key already used
by shared recipes (``"key:<name>"``). This module holds no monster constants.
"""

from copy import deepcopy
from functools import lru_cache
import json

from .expressions import combined, compare, invert, runtime

OPERATORS = {"==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}


@lru_cache(maxsize=1)
def _recovered_document():
    from ..config import EVIDENCE_DIR

    return json.loads(
        (EVIDENCE_DIR / "recovered_conditions.v1.json").read_text(encoding="utf-8")
    )


def condition_evidence(key):
    return _recovered_document()["evidence"][key]


def verify_recovered_conditions(pe, metadata):
    """Reject relocated methods, changed field layouts or changed native bytes."""
    document = _recovered_document()
    for rows in document["evidence"].values():
        for row in rows:
            method = (
                (metadata.get(row["type"]) or {}).get("methods", {}).get(row["method"])
            )
            if method is None or int(method.get("function", "0"), 16) != int(
                row["address"], 16
            ):
                raise ValueError(
                    "已核实条件的方法身份变化：" + row["type"] + "." + row["method"]
                )
    for proofs in document["nativeProofs"].values():
        for proof in proofs:
            start, end = int(proof["address"], 16), int(proof["end"], 16)
            expected = bytes.fromhex(proof["bytes"])
            if (
                end - start != len(expected)
                or pe.read(start, len(expected)) != expected
            ):
                raise ValueError("已核实条件的原生字节变化：" + proof["address"])
    for check in document.get("fieldChecks", []):
        field = metadata.fields(check["type"]).get(check["field"], {})
        if (
            field.get("type") != check["fieldType"]
            or field.get("offset_from_base") != check["offset"]
        ):
            raise ValueError(
                "已核实条件的字段布局变化：" + check["type"] + "." + check["field"]
            )
    for check in document.get("enumChecks", []):
        field = (
            (metadata.get(check["type"]) or {})
            .get("fields", {})
            .get(check["field"], {})
        )
        if field.get("default") != check["value"]:
            raise ValueError(
                "已核实条件的枚举值变化：" + check["type"] + "." + check["field"]
            )
    # The ready-end recipe intentionally follows the inherited constant-true
    # slot; a new derived type/override requires reviewing that dispatch again.
    depletion = document.get("depletionDispatch")
    if depletion:
        record = metadata.get(depletion["type"]) or {}
        if record.get("parent") != depletion["parent"] or metadata.subclasses(
            depletion["type"]
        ):
            raise ValueError("能量枯竭结束就绪的虚调用类型范围变化")
        if any(name.startswith("isReadyEnd") for name in record.get("methods", {})):
            raise ValueError("能量枯竭结束就绪的虚调用被覆盖")


def _key(extend, field):
    kind, _, path = field.partition(":")
    if kind == "extend":
        return f"extend:{extend}.{path}"
    if kind == "context":
        return f"context:{path}"
    if kind == "key":
        return path
    raise ValueError("字段检查的字段种类无效：" + field)


def _expression(extend, item):
    if item[0] in ("all", "any"):
        return combined(item[0], *(_expression(extend, x) for x in item[1:]))
    if item[0] == "not":
        return invert(_expression(extend, item[1]))
    key = _key(extend, item[0])
    if len(item) == 1:
        return runtime(key, item[0].partition(":")[2] + " 为真")
    field, operator, value = item
    return compare(key, value, OPERATORS[operator], source=field.partition(":")[2])


def reviewed_condition(expression, evidence, *, summary, extend=None, inputs=None):
    """Keep the native work/type guards on a reviewed field or query formula."""
    guards = [runtime("enemy_command_work_valid", "命令工作存在且原生类型检查通过")]
    if extend is not None:
        guards.append(runtime("self_extend_valid", f"自身 Extend 存在且是 {extend}"))
    result = dict(
        expression=combined("all", *guards, expression),
        summary=summary,
        semanticStatus="reviewed_native_semantics",
        semanticEvidence=deepcopy(list(evidence)),
    )
    if inputs:
        result["inputDefinitions"] = deepcopy(inputs)
    return result


def field_condition(spec, extend, evidence, *, summary, enums=None):
    """The recovered condition for one reviewed command recipe.

    ``extend`` is the exact Extend type checked by the command (None when it
    only reads cEnemyContext); the command-work guard is always required.
    """
    result = reviewed_condition(
        _expression(extend, spec), evidence, summary=summary, extend=extend
    )
    if enums:
        result["inputEnums"] = {
            _key(extend, field): dict(names) for field, names in enums.items()
        }
    return result


def declared_condition(table, node):
    """Look up ``node``'s command in a module's recipe table.

    A value is ``dict(spec=..., extend=..., evidence=..., summary=...,
    enums=...)`` or a function of the resource argument returning one (or
    None when that argument is not reviewed).
    """
    recipe = table.get(node.get("commandType"))
    if callable(recipe):
        recipe = recipe(node.get("argument") or {})
    if recipe is None:
        return None
    return field_condition(
        recipe["spec"],
        recipe.get("extend"),
        recipe["evidence"],
        summary=recipe["summary"],
        enums=recipe.get("enums"),
    )
