"""Reviewed target writes; vectors retain their native inputs and operations.

These recipes describe calls made by the command. They do not execute the
game's target module, navigation, Transform access, or vector queries.
"""

from copy import deepcopy
from functools import lru_cache
import json
import math
import struct

from ..config import (
    BOOLEAN_TYPE,
    EVIDENCE_DIR,
    NO_ARGUMENT_TYPES,
    OBSTACLE_CLIMB_COMMAND as OBSTACLE_COMMAND,
    OBSTACLE_HEIGHT_COMPONENT_OFFSET,
    OBSTACLE_HEIGHT_FLOAT_OFFSET,
    OBSTACLE_HEIGHT_POINTER_OFFSET,
    OBSTACLE_STEP_UP_WALL as STEP_UP_WALL,
    OBSTACLE_TYPE_ENUM,
    OBSTACLE_TYPE_RUNTIME_KEY as OBSTACLE_TYPE_KEY,
    SIDE_WALK_ANGLE_FIELD,
    SIDE_WALK_SUPPORTING_METHODS,
    TARGET_COMMAND_EXECUTE_METHOD,
    TARGET_FIRST_ORDER as FIRST_ORDER,
    TARGET_MODULE_SETTER_CALLEE,
    TARGET_OBSTACLE_CATEGORY as OBSTACLE_CATEGORY,
    TARGET_POSITION_GETTER_SOURCE,
    TARGET_POSITION_SETTER_CALLEE,
    TARGET_SECOND_ORDER as SECOND_ORDER,
    TARGET_UNIQUE_CATEGORY as UNIQUE_CATEGORY,
)
from .expressions import combined, compare, runtime
from .values import number, scalar

OBSTACLE_RECEIPT = "target_command_effects.v1.json"
CHARACTER_KEY = "target_command_character_exists"
GAME_OBJECT_KEY = "target_command_game_object_exists"
TRANSFORM_KEY = "target_command_transform_exists"
CURRENT_NODE_KEY = "target_command_current_obstacle_node_exists"
WALL_NODE_KEY = "target_command_wall_obstacle_node_exists"
SIZE_SETTING_KEY = "target_command_size_setting_exists"
HEIGHT_COMPONENT_KEY = "target_command_height_component_chain_valid"


@lru_cache(maxsize=None)
def target_receipt(name):
    return json.loads((EVIDENCE_DIR / name).read_text(encoding="utf8"))


def verify_target_receipt(pe, metadata, name):
    """Reject changed methods, bytes, layouts, enum values, or type guards."""
    proof = target_receipt(name)
    for row in proof["methods"]:
        method = (
            (metadata.get(row["type"]) or {}).get("methods", {}).get(row["method"], {})
        )
        if (
            int(method.get("function", "0"), 16) != int(row["address"], 16)
            or method.get("returns", {}).get("type") != row["returns"]
            or [p.get("type") for p in method.get("params", [])] != row["parameters"]
        ):
            raise ValueError("目标更新命令的方法身份或签名变化：" + row["type"])
    for row in [*proof["methods"], *proof["nativeProofs"], *proof["constants"]]:
        start, end = int(row["address"], 16), int(row["end"], 16)
        expected = bytes.fromhex(row["nativeBytes"])
        if len(expected) != end - start or pe.read(start, end - start) != expected:
            raise ValueError("目标更新命令的原生字节变化：" + row["address"])
    for row in proof["fieldChecks"]:
        field = metadata.fields(row["type"]).get(row["field"], {})
        if (
            field.get("type") != row["fieldType"]
            or field.get("offset_from_base") != row["offset"]
        ):
            raise ValueError("目标更新命令的字段布局变化：" + row["type"])
    for row in proof["enumChecks"]:
        fields = (metadata.get(row["type"]) or {}).get("fields", {})
        values = {
            key: value["default"] for key, value in fields.items() if "default" in value
        }
        if values != row["values"]:
            raise ValueError("目标更新命令的枚举变化：" + row["type"])
    for row in proof["classSymbols"]:
        address = (metadata.get(row["type"]) or {}).get("address")
        slot = row.get("slot")
        if "sourceType" in row:
            from capstone import CS_OP_MEM
            from ..native.symbols import instructions, method_stem

            source = next(
                method
                for method in proof["methods"]
                if method["type"] == row["sourceType"]
                and method_stem(method["method"]) == row["sourceMethod"]
            )
            pc = int(source["address"], 16) + int(row["instructionOffset"], 16)
            if not int(source["address"], 16) <= pc < int(source["end"], 16):
                raise ValueError("目标更新命令的类型来源超出已审核方法范围")
            native, _ = instructions(pe, pc, pc + 16)
            ins = native[0] if native else None
            if (
                ins is None
                or ins.address + ins.size > int(source["end"], 16)
                or ins.mnemonic != "cmp"
                or len(ins.operands) != 2
                or ins.operands[1].type != CS_OP_MEM
                or ins.reg_name(ins.operands[1].mem.base) != "rip"
                or ins.operands[1].mem.index
            ):
                raise ValueError("目标更新命令的类型来源指令变化：" + row["type"])
            slot = hex(ins.address + ins.size + ins.operands[1].mem.disp)
        if not address or int.from_bytes(pe.read(int(slot, 16), 8), "little") != int(
            address, 16
        ):
            raise ValueError("目标更新命令的原生类型检查变化：" + row["type"])
    return True


def verify_target_command_effects(pe, metadata):
    from .throw_target import RECEIPT

    for name in (OBSTACLE_RECEIPT, RECEIPT):
        verify_target_receipt(pe, metadata, name)
    return True


def _evidence(name):
    return [
        {key: row[key] for key in ("type", "method", "address", "end")}
        for row in target_receipt(name)["methods"]
    ]


def _match(command, evidence, receipt_name):
    row = next(
        row
        for row in target_receipt(receipt_name)["methods"]
        if row["type"] == command
        and row["method"].startswith(TARGET_COMMAND_EXECUTE_METHOD)
    )
    if not evidence or any(
        evidence.get(key) != row[key] for key in ("type", "method", "address", "end")
    ):
        raise ValueError("目标更新命令与已核实原生实现不匹配：" + command)


def _side_walk_supporting_evidence():
    rows = [
        row
        for row in _evidence(OBSTACLE_RECEIPT)
        if (row["type"], row["method"]) in SIDE_WALK_SUPPORTING_METHODS
    ]
    if (
        len(rows) != len(SIDE_WALK_SUPPORTING_METHODS)
        or {(row["type"], row["method"]) for row in rows}
        != SIDE_WALK_SUPPORTING_METHODS
    ):
        raise ValueError("侧向目标更新的六项辅助方法证据不完整")
    return rows


def _reference_inputs():
    return {
        CHARACTER_KEY: dict(
            label="怪物角色对象有效",
            boolean=True,
            hint="Accessor.Character 非空；独立的引用存在事实，不是目标更新命令的结果。",
        ),
        GAME_OBJECT_KEY: dict(
            label="怪物角色的游戏对象有效",
            boolean=True,
            hint="Accessor.Character 的 GameObject 非空；需先有 Character。",
        ),
        TRANSFORM_KEY: dict(
            label="怪物角色的位置组件有效",
            boolean=True,
            hint="角色 GameObject 的 Transform 非空；SideWalkOffset 中缺失时调用错误处理，不返回普通 false。",
        ),
    }


def _mutation(updates, evidence, summary, exception_boundary):
    return dict(
        effect="update_target_positions",
        summary=summary,
        targetUpdates=updates,
        invalidateTargetSnapshot=True,
        semanticEvidence=evidence,
        exceptionBoundary=exception_boundary["reason"],
        exceptionContract=deepcopy(exception_boundary),
        implementationBoundary="只记录已核实的目标设置调用与向量来源；未运行游戏目标模块、位置计算或导航。目标位置未知时使此前目标相关快照失效。",
    )


def reviewed_target_command_effect(bound, evidence):
    """The common obstacle command: its Boolean is independent of queries."""
    from .throw_target import COMMAND, throw_target_effect

    if bound.get("commandType") == COMMAND:
        return throw_target_effect(bound, evidence)
    if bound.get("commandType") != OBSTACLE_COMMAND:
        return None
    _match(OBSTACLE_COMMAND, evidence, OBSTACLE_RECEIPT)
    if bound.get("argumentType") not in NO_ARGUMENT_TYPES or bound.get("argument"):
        raise ValueError("障碍攀爬目标命令不接受资源参数")
    proof = target_receipt(OBSTACLE_RECEIPT)
    enums = next(
        row["values"]
        for row in proof["enumChecks"]
        if row["type"] == OBSTACLE_TYPE_ENUM
    )
    inputs = _reference_inputs()
    inputs.pop(TRANSFORM_KEY)
    inputs.update(
        {
            OBSTACLE_TYPE_KEY: dict(
                label="当前障碍类型",
                options=[
                    dict(
                        label=name,
                        value=value if value < 0x80000000 else value - 0x100000000,
                    )
                    for name, value in enums.items()
                    if name != "MAX"
                ],
                hint="Context.Obstacle.ObstacleType；命令只在 STEP_UP_WALL 时设置目标。",
            ),
            CURRENT_NODE_KEY: dict(
                label="当前障碍节点有效",
                boolean=True,
                hint="Context.Obstacle.CurrentNode 非空；通过类型判定后本方法直接读取其 Position。",
            ),
            WALL_NODE_KEY: dict(
                label="墙面障碍节点有效",
                boolean=True,
                hint="Context.Obstacle.WallNode 非空；读取其 Normal，不重新执行碰撞查询。",
            ),
            SIZE_SETTING_KEY: dict(
                label="当前体型参数有效",
                boolean=True,
                hint="按当前 MODEL_SIZE 查到 EmParamCommon.cSizeSetting；读取 CharaCtrlRadius。",
            ),
            HEIGHT_COMPONENT_KEY: dict(
                label="攀爬高度来源的组件引用有效",
                boolean=True,
                hint="Character+0x160清除引用标记后，读取+0x18处指针，再读取该对象+0x78的float；正式字段名尚未核实。",
            ),
        }
    )
    guard = combined(
        "all",
        runtime(
            "enemy_command_work_valid", "工作对象存在且类型为 cEnemyBTableCommandWork"
        ),
        runtime(CHARACTER_KEY, "Accessor.Character != null"),
        runtime(GAME_OBJECT_KEY, "Character.GameObject != null"),
        compare(OBSTACLE_TYPE_KEY, STEP_UP_WALL, source="STEP_UP_WALL"),
    )
    precondition = combined(
        "all",
        runtime(CURRENT_NODE_KEY, "Obstacle.CurrentNode != null"),
        runtime(WALL_NODE_KEY, "Obstacle.WallNode != null"),
        runtime(SIZE_SETTING_KEY, "当前体型设置 != null"),
        runtime(HEIGHT_COMPONENT_KEY, inputs[HEIGHT_COMPONENT_KEY]["hint"]),
        runtime("self_target_context_valid", "Context.Target != null"),
    )
    exception = dict(
        reason="类型与引用 guard 通过后，节点、体型设置、角色组件链及 Target 被直接解引用；缺失不是普通 false 返回。",
        uncheckedSources=[
            "Character component chain used for h",
            "Obstacle.CurrentNode",
            "Obstacle.WallNode",
            "current model-size setting",
            "Context.Target",
        ],
        componentHeightFieldNameVerified=False,
    )
    position = dict(
        kind="native_vector_formula",
        formula="f32(f32(A + (0,h,0)) - f32(f32(N * r) * 2.0))",
        sources=dict(
            A="Context.Obstacle.CurrentNode.Position",
            N="Context.Obstacle.WallNode.Normal",
            r="EmParamCommon.SizeSetting[current MODEL_SIZE].CharaCtrlRadius",
            h=dict(
                kind="native_float_read",
                relativeTo="Accessor.Character",
                path=[
                    dict(
                        addressOffset=OBSTACLE_HEIGHT_COMPONENT_OFFSET,
                        clearReferenceTagBit=63,
                        dereferenceOffset=OBSTACLE_HEIGHT_POINTER_OFFSET,
                    ),
                    dict(readFloatOffset=OBSTACLE_HEIGHT_FLOAT_OFFSET),
                ],
                fieldNameVerified=False,
            ),
        ),
        arithmetic="每个向量分量按 float32 加减乘；不归一化 Normal，也没有射线或导航成功判定",
    )
    mutation = _mutation(
        [
            dict(
                order=FIRST_ORDER,
                orderName="FIRST",
                category=OBSTACLE_CATEGORY,
                categoryName="OBSTACLE",
                position=position,
                direction=None,
                booleanOptions=[False, True],
                nullableUInt32=None,
                callee=TARGET_MODULE_SETTER_CALLEE,
            )
        ],
        _evidence(OBSTACLE_RECEIPT),
        "按已有墙面障碍信息更新攀爬目标",
        exception,
    )
    return dict(
        returnType=BOOLEAN_TYPE,
        returnExpression=guard,
        normalPrecondition=precondition,
        inputDefinitions=inputs,
        targetMutation=mutation,
        exceptionBoundary=exception["reason"],
        exceptionContract=exception,
        semanticEvidence=_evidence(OBSTACLE_RECEIPT),
        returnSemantics="guard 不成立返回 false且不写；正常写入后返回 true，未读取 setter 成功值。调用方是否使用该返回由实际指令决定。",
    )


def side_walk_target_effect(
    bound,
    evidence,
    *,
    command,
    argument_type,
    extend_type,
    receipt_name,
    angle_multipliers
):
    """Build one monster-owned SideWalk recipe after exact identity binding."""
    if bound.get("commandType") != command:
        return None
    _match(command, evidence, receipt_name)
    if bound.get("argumentType") != argument_type:
        raise ValueError("侧向目标更新的资源参数类型不匹配")
    angle = number(scalar(bound["argument"][SIDE_WALK_ANGLE_FIELD]))

    def f32(value):
        try:
            return struct.unpack("<f", struct.pack("<f", value))[0]
        except OverflowError:
            return math.copysign(math.inf, value)

    radians = f32(angle)
    for multiplier in angle_multipliers:
        radians = f32(radians * multiplier)
    inputs = _reference_inputs()
    guard = combined(
        "all",
        runtime(
            "enemy_command_work_valid", "工作对象存在且类型为 cEnemyBTableCommandWork"
        ),
        runtime("self_extend_valid", "自身 Extend 存在且原生精确类型为 " + extend_type),
    )
    precondition = combined(
        "all",
        *(runtime(key, definition["hint"]) for key, definition in inputs.items()),
        runtime("self_target_context_valid", "Context.Target != null")
    )
    exception = dict(
        reason="work/Extend guard通过后 Character 被直接解引用；GameObject 或 Transform 缺失调用错误处理0x46并终止正常路径，不是普通 false 返回。",
        uncheckedSources=[
            "Accessor.Character",
            "Character.GameObject",
            "Character.GameObject.Transform",
            "Context.Target",
        ],
        explicitNullErrorCode=70,
    )
    position = dict(
        kind="native_vector_formula",
        formula="rotationAxis(f32(T + f32(P - T)), (0,1,0), angleRadians, T)",
        sources=dict(
            T=TARGET_POSITION_GETTER_SOURCE,
            P="Accessor.Character.GameObject.Transform.Position",
        ),
        angle=dict(
            sourceField=SIDE_WALK_ANGLE_FIELD,
            resourceValue=angle,
            operations=[
                dict(operation="multiply_float32", value=value)
                for value in angle_multipliers
            ],
            radians=radians,
        ),
        arithmetic="减法、加法和角度每次乘法分别按 float32；保留 T+(P−T) 的顺序，不直接替换为 P。",
    )
    updates = [
        dict(
            order=FIRST_ORDER,
            orderName="FIRST",
            category=UNIQUE_CATEGORY,
            categoryName="UNIQUE",
            position=position,
        ),
        dict(
            order=SECOND_ORDER,
            orderName="SECOND",
            category=UNIQUE_CATEGORY,
            categoryName="UNIQUE",
            position=dict(
                kind="native_vector_source",
                source=TARGET_POSITION_GETTER_SOURCE,
                capturedBeforeFirstWrite=True,
            ),
        ),
    ]
    for update in updates:
        update.update(
            booleanOptions=[False],
            nullableUInt32=None,
            callee=TARGET_POSITION_SETTER_CALLEE,
            targetSubCategory=0,
        )
    mutation = _mutation(
        updates,
        [*_side_walk_supporting_evidence(), *_evidence(receipt_name)],
        "更新侧向目标并保存原目标位置",
        exception,
    )
    return dict(
        returnType=BOOLEAN_TYPE,
        returnExpression=guard,
        normalPrecondition=precondition,
        inputDefinitions=inputs,
        targetMutation=mutation,
        exceptionBoundary=exception["reason"],
        exceptionContract=exception,
        semanticEvidence=_evidence(receipt_name),
        returnSemantics="work/Extend guard不成立返回 false且不写；正常调用两次 setter 后返回 true，与导航成败无关。",
    )
