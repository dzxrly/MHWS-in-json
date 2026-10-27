"""Reviewed variable writes and dynamic action sources from native commands.

The receipt is checked once against the extraction's PE and metadata. Recipe
lookups still require the exact command implementation identity; they do not
turn an unreviewed command with a similar name into a verified operation.
"""

from functools import lru_cache
import json
import math
import struct

from ..config import EVIDENCE_DIR, REQUEST_EFFECTS
from .expressions import combined, runtime
from .values import MissingState, enum_number, number, scalar

FLOAT_COMMAND = "ace.btable.cSetFloatValue"
BOOL_COMMAND = "ace.btable.cSetBoolValue"
TIMER_COMMAND = "ace.btable.cSetTimerValue"
SELECTED_COMMAND = "app.btable.EmCommonCommand.cRequestSelectedAction"
SWITCH_COMMAND = "app.btable.EmCommonCommand.cActionSwitch"
VARIABLE_COMMANDS = {
    FLOAT_COMMAND: "float",
    BOOL_COMMAND: "bool",
    TIMER_COMMAND: "timer",
}
FLOAT_OPERATIONS = {0: "assign", 1: "add", 2: "subtract"}
TIMER_OPERATIONS = {0: "assign", 1: "activate", 2: "deactivate", 3: "activate_no_reset"}
SELECTED_SOURCES = {
    0: ("damage", "此前选定的受击动作", "Hit.DamageActionID"),
    1: ("attack_hit", "此前选定的攻击命中反应", "Hit.AttackHitActionID"),
    2: ("obstacle", "按当前障碍类型选择的动作", "Obstacle.ObstacleType"),
    3: ("state_sign", "按当前状态提示类型选择的动作", "StateSignActionType"),
    4: ("pop_interact", "此前选定的互动动作", "Collect.ActionID"),
    5: ("detour", "按当前绕路状态选择的动作", "Detour"),
    7: ("lead_chase", "按当前追逐阶段选择的动作", "Lead.Chase._CurrentPhase"),
}
SWITCH_SOURCES = {
    0: ("current", "当前动作的分派编号", "ActionController.CurrentAction.ID"),
    1: ("damage", "选定受击动作的分派编号", "Hit.DamageActionID"),
    2: ("attack_hit", "攻击命中反应的分派编号", "Hit.AttackHitActionID"),
    3: ("obstacle", "障碍动作的分派编号", "Obstacle.ObstacleType"),
    4: ("state_sign", "状态提示动作的分派编号", "StateSignActionType"),
}


@lru_cache(maxsize=1)
def receipt():
    return json.loads(
        (EVIDENCE_DIR / "command_effects.v1.json").read_text(encoding="utf8")
    )


def verify_command_effects(pe, metadata):
    """Reject changed native implementations, field layouts, or enum values."""
    proof = receipt()
    for row in (*proof["commands"].values(), *proof["helpers"].values()):
        start, end = int(row["address"], 16), int(row["end"], 16)
        if pe.read(start, end - start).hex() != row["nativeBytes"]:
            raise ValueError("命令更新语义的原生字节变化：" + row["address"])
        if "type" in row:
            record = metadata.get(row["type"]) or {}
            method = record.get("methods", {}).get(row["method"], {})
            if int(method.get("function", "0"), 16) != start:
                raise ValueError("命令更新语义的方法身份变化：" + row["type"])
            if (
                method.get("returns", {}).get("type") != row["returns"]
                or [parameter.get("type") for parameter in method.get("params", [])]
                != row["parameters"]
            ):
                raise ValueError("命令更新语义的方法签名变化：" + row["type"])
    for owner, expected in proof["layouts"].items():
        fields = metadata.fields(owner)
        for name, field in expected.items():
            actual = fields.get(name, {})
            if (
                actual.get("type") != field["type"]
                or actual.get("offset_from_base") != field["offset"]
            ):
                raise ValueError("命令更新语义的字段布局变化：" + owner + "." + name)
    for owner, expected in proof["enums"].items():
        fields = (metadata.get(owner) or {}).get("fields", {})
        actual = {k: v["default"] for k, v in fields.items() if "default" in v}
        if actual != expected:
            raise ValueError("命令更新语义的枚举变化：" + owner)
    return True


def _matching(command, evidence, metadata=None, pe=None):
    row = receipt()["commands"].get(command)
    if row is None:
        return None
    if not evidence or any(
        evidence.get(key) != row[key] for key in ("type", "method", "address", "end")
    ):
        raise ValueError("命令更新语义与原生实现身份不匹配：" + command)
    if (metadata is None) != (pe is None):
        raise ValueError("核对原生配方需要同时提供 PE 与元数据")
    if pe is not None:
        verify_command_effects(pe, metadata)
    return {key: row[key] for key in ("type", "method", "address", "end")}


def _life(definition):
    value = definition.get("life", definition.get("_Life"))
    if value in ("CONSTANT", "GLOBAL", "LOCAL"):
        return value
    return {0: "GLOBAL", 1: "LOCAL", 2: "CONSTANT"}.get(enum_number(value))


def storage_effect(
    target_address, variable, value=None, operation=None, *, variable_catalog=None
):
    """Describe a verified direct storage call; missing definitions stay unknown.

    The caller must have run ``verify_command_effects`` for its current PE.
    Float operation numbers are ASSIGN/ADD/MINUS (0/1/2); timer numbers are
    storage ASSIGN/ACTIVATE/DEACTIVATE/ACTIVATE_NO_RESET (0/1/2/3), not
    resource enums. ASSIGN preserves the timer's active flag.
    """
    helpers = receipt()["helpers"]
    kind = next(
        (
            name
            for name in ("float", "bool", "timer")
            if int(helpers[name]["address"], 16) == target_address
        ),
        None,
    )
    if kind is None:
        return None
    if kind == "float":
        op = FLOAT_OPERATIONS.get(operation)
        if op is None:
            raise MissingState("浮点更新方式未核实")
        value = number(value)
    elif kind == "timer":
        op = TIMER_OPERATIONS.get(operation)
        if op is None:
            raise MissingState("计时器更新方式未核实")
        if op == "assign":
            value = number(value)
    else:
        op = "assign"
        value = scalar(value)
        if type(value) is not bool:
            raise MissingState("布尔更新缺少布尔值")
    update = dict(variable=variable, kind=kind, operation=op)
    if kind != "timer" or op == "assign":
        update["value"] = value
    proof = helpers[kind]
    result = dict(
        kind="mutation",
        effect={
            "float": "set_float_value",
            "bool": "set_bool_value",
            "timer": "set_timer_state",
        }[kind],
        summary={
            "float": "更新行为记录",
            "bool": "更新布尔记录",
            "timer": "更新计时器",
        }[kind],
        variableUpdate=update,
        writeGuard="变量存储有资源定义，GUID 存在且变量不是 CONSTANT；否则不写入",
        semanticEvidence={
            key: proof[key] for key in ("type", "method", "address", "end")
        },
        commandEffectsComplete=True,
    )
    definition = (variable_catalog or {}).get(variable)
    if definition is None:
        result["commandEffectsComplete"] = False
        result["implementationBoundary"] = (
            "变量资源定义尚未绑定，不能推断写入是否生效或使用默认上下限"
        )
        update["definitionStatus"] = "unknown"
        return result
    if definition.get("kind", kind) != kind:
        raise ValueError("变量更新与资源定义类型不匹配")
    update.update(definitionStatus="bound", readOnly=_life(definition) == "CONSTANT")
    if kind == "float":
        minimum = definition.get("min", definition.get("_MinValue"))
        maximum = definition.get("max", definition.get("_MaxValue"))
        update.update(min=number(minimum), max=number(maximum))
    if kind == "timer" and op == "activate":
        update["default"] = number(
            definition.get("default", definition.get("_DefaultValue"))
        )
    return result


def reviewed_command_effect(
    bound, command_evidence, variable_catalog=None, *, metadata=None, pe=None
):
    command = bound.get("commandType")
    kind = VARIABLE_COMMANDS.get(command)
    if kind is None:
        return None
    evidence = _matching(command, command_evidence, metadata, pe)
    expected_arg = command + "Arg"
    if bound.get("argumentType") != expected_arg:
        raise ValueError("变量命令参数类型不匹配：" + str(bound.get("argumentType")))
    argument = bound["argument"]
    variable = scalar(argument["_TargetVariableIndex"])
    if not isinstance(variable, str):
        raise MissingState("变量更新缺少 GUID")
    operation = None
    value = None
    if kind == "float":
        operation = enum_number(argument["_Method"])
        value = scalar(argument["_Value"])
    elif kind == "timer":
        resource_mode = enum_number(argument["_SetType"])
        if resource_mode not in (0, 1, 2):
            raise MissingState("计时器资源更新方式未核实")
        operation = resource_mode + 1
    else:
        value = scalar(argument["_Value"])
    result = storage_effect(
        int(receipt()["helpers"][kind]["address"], 16),
        variable,
        value,
        operation,
        variable_catalog=variable_catalog,
    )
    result["supportingEvidence"] = [result["semanticEvidence"]]
    result["semanticEvidence"] = evidence
    result["commandGuard"] = runtime("enemy_command_work_valid", "命令工作存在")
    result["returnType"] = "System.Void"
    result["continuationStatus"] = "native_caller_continuation"
    return result


def _float32(value):
    try:
        return struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError:
        return math.copysign(math.inf, value)


def apply_variable_update(update, current):
    """Evaluate one known write without inventing missing live variable values."""
    if update.get("definitionStatus") != "bound":
        raise MissingState("变量资源定义未绑定")
    result = dict(current)
    if update["readOnly"]:
        return result
    kind, op = update["kind"], update["operation"]
    allowed = {
        "float": FLOAT_OPERATIONS.values(),
        "bool": ("assign",),
        "timer": TIMER_OPERATIONS.values(),
    }
    if op not in allowed.get(kind, ()):
        raise ValueError("变量更新操作无效")
    if kind == "float":
        value = _float32(number(update["value"]))
        if op != "assign":
            old = _float32(number(current.get("value")))
            value = _float32(old + value if op == "add" else old - value)
        result["value"] = max(min(value, update["max"]), update["min"])
    elif kind == "bool":
        result["value"] = update["value"]
    elif kind == "timer":
        if op != "assign":
            result["active"] = op != "deactivate"
        if op == "assign":
            result["value"] = _float32(update["value"])
        elif op == "activate":
            result["value"] = _float32(update["default"])
    else:
        raise ValueError("未知变量更新类型")
    return result


def dynamic_request_details(bound, command_evidence, *, metadata=None, pe=None):
    if bound.get("commandType") != SELECTED_COMMAND:
        return None
    evidence = _matching(SELECTED_COMMAND, command_evidence, metadata, pe)
    if bound.get("argumentType") != SELECTED_COMMAND + "Arg":
        raise ValueError("动态动作请求参数类型不匹配")
    category = enum_number(bound["argument"]["_EditArg"])
    if category not in SELECTED_SOURCES:
        raise MissingState("动态动作来源尚未核实")
    source, label, field = SELECTED_SOURCES[category]
    return dict(
        effect="request_dynamic_action",
        summary="请求" + label,
        actionSource=dict(
            kind=source, field=field, resourceSelection=category in (2, 3, 5, 7)
        ),
        requestGuard=combined(
            "all",
            runtime("enemy_command_work_valid", "匹配类型的敌人命令工作存在"),
            dict(
                kind="not",
                item=runtime("btable_request_action_mask", "行为表动作请求已屏蔽"),
            ),
        ),
        requestEffects=[
            dict(field=field, value=False, offset=offset)
            for field, offset in REQUEST_EFFECTS
        ],
        semanticEvidence=evidence,
        returnType="System.Void",
        continuationStatus="native_caller_continuation",
        actionConversion="选定 ACTION_ID 经过自身 Extend.convertAction 后交给 requestActionCore",
        selectionEffects=(
            "DamageActionID 无效且 RestartDamageActionID 有效时使用后者，并将恢复槽清为无效"
            if category == 0
            else "按当前来源读取动作"
        ),
        implementationBoundary="具体动作依赖当前选择和 Extend 转换；actor 请求内部效果尚未全部恢复，本节点不保证请求成功或动作完成",
    )


def action_switch_details(bound, command_evidence, *, metadata=None, pe=None):
    if bound.get("commandType") != SWITCH_COMMAND:
        return None
    evidence = _matching(SWITCH_COMMAND, command_evidence, metadata, pe)
    if bound.get("argumentType") != SWITCH_COMMAND + "Arg":
        raise ValueError("动作分派参数类型不匹配")
    category = enum_number(bound["argument"]["_EditArg"])
    if category not in SWITCH_SOURCES:
        raise MissingState("动作分派来源尚未核实")
    source, label, field = SWITCH_SOURCES[category]
    return dict(
        runtimeKey="action_dispatch:" + source,
        inputLabel=label,
        actionSource=dict(kind=source, field=field),
        returnType="System.Int32",
        valueRepresentation="uint32",
        invalidValue=0xFFFFFFFF,
        packing="Category、Index 均非负且可表示为16位时，Category<<16 | Index；任一负数返回0xffffffff，溢出诊断路径仍未核实",
        convertAction=category != 0,
        semanticEvidence=evidence,
        implementationBoundary="动作来源与转换结果依赖运行时状态；这是整数分派编号，不是布尔条件或随机选招",
    )


def pack_action_id(category, index):
    if type(category) is not int or type(index) is not int:
        raise MissingState("动作分派需要整数 Category 与 Index")
    if category < 0 or index < 0:
        return 0xFFFFFFFF
    if category > 0xFFFF or index > 0xFFFF:
        raise MissingState("动作分派超出16位字段范围，原生诊断路径未核实")
    return (category << 16) | index
