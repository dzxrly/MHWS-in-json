"""Construct, validate and evaluate conditions; missing state stays unknown."""

from .values import Outcome


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


def expression_unknown(expression):
    if expression["kind"] == "unknown":
        return True
    if expression["kind"] == "predicate":
        return expression["predicate"].get("status") != "verified"
    if expression["kind"] in ("all", "any"):
        return any(expression_unknown(item) for item in expression["items"])
    if expression["kind"] == "not":
        return expression_unknown(expression["item"])
    return False


def validate_expression(expression):
    kind = expression.get("kind")
    if kind in ("all", "any"):
        if not expression.get("items"):
            raise ValueError("组合条件不能为空")
        for item in expression["items"]:
            validate_expression(item)
    elif kind == "not":
        validate_expression(expression["item"])
    elif kind == "predicate":
        if "predicate" not in expression:
            raise ValueError("条件表达式缺少已绑定判断")
    elif kind == "runtime":
        if not expression.get("key") or not expression.get("source"):
            raise ValueError("运行时条件必须保留输入键和来源")
    elif kind == "compare":
        if expression.get("operator") not in ("eq", "ne", "lt", "le", "gt", "ge"):
            raise ValueError("未知比较运算")
        for operand in (expression["left"], expression["right"]):
            if operand.get("kind") not in ("constant", "runtime"):
                raise ValueError("比较操作数无效")
            if operand["kind"] == "runtime":
                validate_expression(operand)
            elif "value" not in operand:
                raise ValueError("常量缺少值")
    elif kind == "unknown":
        if not expression.get("reason"):
            raise ValueError("未知条件必须说明范围")
    else:
        raise ValueError("未知条件表达式类型")


def runtime(key, source):
    return dict(kind="runtime", key=key, source=source)


def compare(key, value, operator="eq", *, source):
    return dict(
        kind="compare",
        operator=operator,
        left=runtime(key, source),
        right=dict(kind="constant", value=value),
    )


def combined(kind, *items):
    return dict(kind=kind, items=list(items))


def invert(item):
    return dict(kind="not", item=item)
