"""Verified logical comparisons under a valid command-work context.

Missing state is unknown. These comparisons do not simulate native floating-point
vector arithmetic, target selection, or the game loop bit for bit.
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from .paths import MODEL_DIR
from .values import scalar, enum_number, MissingState


@dataclass(frozen=True)
class Outcome:
    truth: bool | None
    reason: str


def number(value):
    value = scalar(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MissingState("缺少数值")
    if not math.isfinite(value):
        raise MissingState("数值不是有限数")
    return value


def required(mapping, key):
    if key not in mapping:
        raise MissingState(f"缺少状态：{key}")
    return mapping[key]


class RuleRegistry:
    def __init__(self, data):
        if data.get("schemaVersion") != 1:
            raise ValueError("不支持的行动判断规则版本")
        self.data = data
        self.by_command = {r["commandType"]: r for r in data["rules"]}
        self.by_argument = {
            r["argumentType"]: r for r in data["rules"] if r["argumentType"]
        }
        if len(self.by_command) != len(data["rules"]):
            raise ValueError("规则存在重复命令类型")

    @classmethod
    def load(cls, path=None):
        path = Path(path) if path is not None else MODEL_DIR / "rules.v1.json"
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def bind(self, command_type, argument_type, argument):
        rule = self.by_command.get(command_type)
        if rule is None:
            return {
                "status": "unknown",
                "commandType": command_type,
                "argumentType": argument_type,
                "argument": argument,
                "summary": "尚未核实此命令的原生判断语义",
            }
        if rule["argumentType"] != argument_type:
            raise ValueError(f"命令与参数类型不匹配：{command_type} / {argument_type}")
        missing = set(rule["bindings"].values()) - argument.keys()
        if missing:
            raise ValueError(f"判断参数缺少字段：{sorted(missing)}")
        values = {
            role: scalar(argument[field]) for role, field in rule["bindings"].items()
        }
        return {
            "status": "verified",
            "commandType": command_type,
            "argumentType": argument_type,
            "kind": rule["kind"],
            "scope": rule["scope"],
            "summary": rule["summary"],
            "values": values,
            "argument": argument,
            "contextBinding": rule["contextBinding"],
            "evidence": rule["evidence"],
        }

    def evaluate(self, bound, context):
        if bound.get("status") != "verified":
            return Outcome(None, bound.get("summary", "未知判断"))
        if context.get("valid_command_work") is False:
            return Outcome(False, "命令上下文无效")
        try:
            truth = self._evaluate(bound, context)
        except (MissingState, KeyError, TypeError, ValueError) as error:
            return Outcome(None, str(error))
        return Outcome(bool(truth), bound["summary"])

    def _evaluate(self, bound, context):
        kind, values = bound["kind"], bound["values"]
        if kind == "occlusion_hits":
            from .navigation_conditions import occlusion_hits

            return occlusion_hits(context)
        if kind == "distance":
            axis, base = enum_number(values["axis"]), enum_number(values["base"])
            if axis not in (0, 1, 2) or base not in (0, 1):
                raise MissingState("不支持的距离轴或基准位置")
            measured = number(required(context, f"distance:{axis}:{base}"))
            modifiers = self.by_command[bound["commandType"]]["distanceModifiers"]
            trigger = modifiers["triggerAIState"]
            current = (
                enum_number(context["ai_state_current"])
                if "ai_state_current" in context
                else None
            )
            pending = (
                enum_number(context["ai_state_pending"])
                if "ai_state_pending" in context
                else None
            )
            if current == trigger or pending == trigger:
                module = required(required(context, "objects"), modifiers["moduleType"])
                scale = number(required(module, modifiers["scaleField"]))
                offset = number(required(module, modifiers["offsetField"]))
            elif current is not None and pending is not None:
                scale, offset = modifiers["defaultScale"], modifiers["defaultOffset"]
            else:
                scale = number(required(context, "distance_scale"))
                offset = number(required(context, "distance_offset"))
            threshold = number(values["threshold"]) * scale + offset
            if axis == 2:
                height = enum_number(values["height"])
                if height == 0:
                    return measured > threshold
                if height == 1:
                    return -measured > threshold
                if height == 2:
                    return abs(measured) < threshold
                raise MissingState("不支持的高度比较")
            compare = enum_number(values["compare"])
            if compare not in (0, 1):
                raise MissingState("不支持的近远比较")
            return measured < threshold if compare == 0 else measured > threshold
        if kind == "angle":
            if enum_number(values["option"]) or enum_number(values["option2"]):
                raise MissingState("角度 Option 特殊分支尚未固化")
            base = enum_number(values["base"])
            if base not in (0, 1, 2, 3):
                raise MissingState("不支持的角度基准")
            vectors_valid = required(context, "angle_vectors_valid")
            if type(vectors_valid) is not bool:
                raise MissingState("角度向量有效性必须是布尔值")
            if not vectors_valid:
                return False
            angle = number(required(context, f"angle:{base}"))
            if not 0 <= angle <= 180:
                raise MissingState("相对夹角必须在 0 到 180 度之间")
            return angle <= number(values["width"]) * 0.5
        if kind == "timer":
            timer = required(required(context, "timers"), str(values["variable"]))
            return number(timer) <= 0
        if kind == "variable_bool":
            actual = required(required(context, "variables"), str(values["variable"]))
            expected = values["value"]
            if type(actual) is not bool or type(expected) is not bool:
                raise MissingState("布尔变量或期望值不是布尔值")
            return actual == expected
        if kind == "self_status":
            category = enum_number(values["category"])
            if context.get("enemy_context_enabled") is False:
                return False
            if category == 3:
                selector = enum_number(scalar(bound["argument"]["Status"]))
                status = (
                    self.by_command[bound["commandType"]]
                    .get("statusBindings", {})
                    .get(str(selector))
                )
                if status is None:
                    raise MissingState("此状态子分类尚未固化")
                state = required(required(context, "objects"), "app.cEnemyContext")
                value = required(state, status["contextKey"])
                if type(value) is not bool:
                    raise MissingState("怒或疲劳输入须是原生 getter 的最终布尔结果")
                return value
            if category == 4:
                ratio = number(required(context, "self_health_ratio"))
                return ratio <= number(values["health"]) / 100
            if category == 1:
                state = required(required(context, "objects"), "app.cEnemyContext")
                holder = values["stand"]
                holder_type = enum_number(holder["STRUCT__Value_Type"])
                expected = number(holder["STRUCT__Value_Value"])
                fixed = required(state, "UniqueStateFixedID")
                if holder_type == 2:
                    return fixed is not None and fixed == expected
                if fixed is not None:
                    return False
                extra = required(state, "ExtraState")
                if holder_type == 1:
                    return extra == expected
                if holder_type == 0:
                    return extra == -1 and required(state, "StandState") == expected
                raise MissingState("不支持的站立状态分类")
            if category == 5:
                selector = enum_number(values["ai"])
                target = {0: 1, 1: 2, 2: 3, 3: 6, 9: 7, 11: 4, 13: 10}.get(selector)
                if target is None:
                    raise MissingState("此 AI 状态分支尚未固化")
                if (
                    context.get("ai_state_current") == target
                    or context.get("ai_state_pending") == target
                ):
                    return True
                current = required(context, "ai_state_current")
                pending = required(context, "ai_state_pending")
                return current == target or pending == target
            raise MissingState("此自身状态分类尚未固化")
        binding = bound["contextBinding"]
        state = required(required(context, "objects"), binding["type"])
        if state.get("valid") is False:
            return False
        actual = number(required(state, binding["field"]))
        if type(actual) is not int:
            raise MissingState("专用内部状态必须是整数")
        if kind == "catch_mushroom":
            return actual in (0, 1, 2, 3, 4, 5, 7)
        expected = (
            enum_number(values["value"])
            if kind != "fang_count"
            else number(values["value"])
        )
        if kind == "mushroom":
            return actual == expected or actual == 5 and expected != 0
        if kind == "electric":
            return actual in (2, 3) if expected == 2 else actual == expected
        if kind == "unique_state":
            return actual == expected
        if kind == "fang_count":
            compare = enum_number(values["compare"])
            if compare == 0:
                return actual >= expected
            if compare == 1:
                return actual <= expected
            if compare == 2:
                return actual == expected
            raise MissingState("不支持的断牙数量比较")
        raise MissingState(f"尚未实现规则：{kind}")
