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

from .expressions import combined, compare, invert, runtime

OPERATORS = {"==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}


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


def field_condition(spec, extend, evidence, *, summary, enums=None):
    """The recovered condition for one reviewed command recipe.

    ``extend`` is the exact Extend type checked by the command (None when it
    only reads cEnemyContext); the command-work guard is always required.
    """
    guards = [runtime("enemy_command_work_valid", "命令工作存在且原生类型检查通过")]
    if extend is not None:
        guards.append(runtime("self_extend_valid", f"自身 Extend 存在且是 {extend}"))
    result = dict(
        expression=combined("all", *guards, _expression(extend, spec)),
        summary=summary,
        semanticStatus="reviewed_native_semantics",
        semanticEvidence=deepcopy(list(evidence)),
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
