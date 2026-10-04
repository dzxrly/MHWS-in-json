"""Structural condition validation; runtime evaluation belongs to the SDK."""


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
