"""Evaluate bound conditions offline; missing runtime state stays unknown."""

from .predicates import Outcome
from .expression_schema import expression_unknown, validate_expression


def evaluate_expression(expression, registry, context):
    validate_expression(expression)
    kind = expression["kind"]
    if kind == "predicate":
        return registry.evaluate(expression["predicate"], context)
    if kind == "unknown":
        return Outcome(None, expression["reason"])
    if kind == "not":
        result = evaluate_expression(expression["item"], registry, context)
        return Outcome(
            None if result.truth is None else not result.truth, result.reason
        )
    if kind in ("all", "any"):
        unknown = None
        for item in expression["items"]:
            result = evaluate_expression(item, registry, context)
            if result.truth is (False if kind == "all" else True):
                return result
            if result.truth is None:
                unknown = result
        return unknown or Outcome(kind == "all", "组合条件已求值")
    if kind == "runtime":
        value = context.get(expression["key"])
        return Outcome(value if type(value) is bool else None, expression["source"])
    operands = []
    for operand in (expression["left"], expression["right"]):
        if operand["kind"] == "constant":
            operands.append(operand["value"])
        elif context.get(operand["key"]) is not None:
            operands.append(context[operand["key"]])
        else:
            return Outcome(None, "缺少运行时值：" + operand["key"])
    left, right = operands
    operations = {
        "eq": lambda: left == right,
        "ne": lambda: left != right,
        "lt": lambda: left < right,
        "le": lambda: left <= right,
        "gt": lambda: left > right,
        "ge": lambda: left >= right,
    }
    try:
        return Outcome(bool(operations[expression["operator"]]()), "比较条件已求值")
    except (TypeError, ValueError):
        return Outcome(None, "运行时比较值类型无效")
