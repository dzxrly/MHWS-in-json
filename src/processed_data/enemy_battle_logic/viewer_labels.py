"""Self-contained HTML view of the verified local decision and continuation graph."""

from .predicates import enum_number, scalar
from .random_choice import weighted_pool


def label(node):
    kind = node["kind"]
    if kind == "condition":
        if "expression" in node:
            return node.get("summary", "条件表达式"), node.get(
                "detail", "具体输入和判断结构见节点详情"
            )
        predicate = node["predicate"]
        values = predicate.get("values", {})
        rule = predicate.get("kind")
        if rule == "angle":
            if enum_number(values["option"]) or enum_number(values["option2"]):
                return "角度判断：特殊 Option 分支尚未固化", str(values)
            direction = {0: "前方", 1: "左方", 2: "右方", 3: "后方"}.get(
                enum_number(values["base"]), "指定方向"
            )
            return (
                f"目标相对{direction}夹角 ≤ {values['width'] / 2:g}°",
                "有效向量；特殊 Option 另行处理",
            )
        if rule == "distance":
            operator = "<" if enum_number(values["compare"]) == 0 else ">"
            axis = {0: "XZ 水平距离", 1: "XYZ 空间距离", 2: "Y 高度"}.get(
                enum_number(values["axis"]), "未知轴"
            )
            base = {0: "自身", 1: "小队中心"}.get(
                enum_number(values["base"]), "未知基准"
            )
            return (
                f"目标命令距离 {operator} {values['threshold']:g} × 倍率 + 偏移",
                f"{axis}；基准：{base}；命令单位",
            )
        if rule == "timer":
            default = node["timer"]["definition"]["_DefaultValue"]
            return (
                "指定计时器剩余值 ≤ 0",
                f"资源默认值：{default:g}；运行时计时状态另行提供",
            )
        if rule == "self_status" and enum_number(values["category"]) == 1:
            holder = values["stand"]
            state = holder["STRUCT__Value_Value"]
            return (
                f"自身站立状态检查：{holder['STRUCT__Value_Type']} / {state}",
                "COMMON 值 1 = 飞行；同时检查额外及固定状态",
            )
        if rule == "self_status" and enum_number(values["category"]) == 3:
            status = node["argument"]["Status"]
            name = {0: "怒状态", 1: "疲劳状态"}.get(enum_number(scalar(status)), "状态")
            return (
                f"自身是否处于{name}",
                "使用原生 getter 的最终结果；缺少运行时状态则未知",
            )
        return predicate["summary"], node["commandType"]
    if kind == "action":
        action = node["action"]
        return (
            "请求动作：" + action["actionClass"],
            "参数变体：" + action["parameterVariantGuid"],
        )
    if kind == "call":
        return "调用子表", node["targetTable"] + "；返回后恢复节点 " + node["resume"]
    if kind == "mutation":
        if node["effect"] not in ("set_float_value", "set_timer_state"):
            return node.get("summary", "更新战斗状态"), node.get(
                "reason", node["effect"]
            )
        if node["effect"] == "set_float_value":
            return (
                "修改行为变量：" + str(node["method"]),
                f"值：{node['value']}；变量：{node['variableGuid']}",
            )
        default = node["timer"]["definition"]["_DefaultValue"]
        return (
            "设置计时器状态：" + str(node["setType"]),
            f"资源默认值：{default:g}；ACTIVATE 重置并启用；其他操作保留值",
        )
    if kind == "weighted_random":
        shares = weighted_pool(node["candidates"])
        return (
            "进入本分支后按候选权重选择",
            " / ".join(str(c["weight"]) for c in shares) + "；非空跳过列表需运行时核对",
        )
    if kind == "unknown":
        return "此处仍有未核实的逻辑", node["reason"]
    return "本子表结束，返回调用方", "方法返回 false；不等同于招式执行失败"
