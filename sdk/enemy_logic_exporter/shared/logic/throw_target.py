"""The reviewed common throw-target caller, with its collection boundary."""

from .expressions import combined, runtime
from .values import number, scalar

COMMAND = "app.btable.EmCommonCommand.cSetDestZakoThrow"
ARGUMENT = "app.btable.EmCommonCommand.cSetDestZakoThrowArg"
RECEIPT = "throw_target.v1.json"


def throw_target_effect(bound, evidence, *, command=COMMAND, argument_type=ARGUMENT):
    from .target_command_effects import _evidence, _match

    if bound.get("commandType") != command:
        return None
    _match(command, evidence, RECEIPT)
    if bound.get("argumentType") != argument_type:
        raise ValueError("投掷目标命令的参数类型不匹配")
    argument = bound.get("argument") or {}
    lower = number(scalar(argument.get("_RangeMin")))
    upper = number(scalar(argument.get("_RangeMax")))
    inputs = {
        "throw_target_first_position_has_value": dict(
            label="首次目标位置查询有值",
            boolean=True,
            hint="第一次 getTargetPosition(FIRST, false) 的 Nullable.HasValue；不是投掷成功。",
        ),
        "throw_target_second_position_has_value": dict(
            label="再次目标位置查询有值",
            boolean=True,
            hint="第二次 getTargetPosition(FIRST, false) 的独立返回值；不假定两次查询相同。",
        ),
        "throw_target_object_valid": dict(
            label="目标搜索所需游戏对象存在",
            boolean=True,
            hint="cEnemyBTableCommandWork.ThisObject 非空；缺失时不能沿普通 false 返回。",
        ),
        "throw_target_transform_valid": dict(
            label="目标搜索所需位置组件存在",
            boolean=True,
            hint="ThisObject.Transform 非空；缺失时调用错误处理0x46。",
        ),
        "throw_candidate_character_exists": dict(
            label="选中对象的角色存在",
            boolean=True,
            hint="已选 cEnemyManageInfo.Character 非空；目标 setter 自身检查，缺失时不写但仍进入持有请求链。",
        ),
        "throw_candidate_character_object_exists": dict(
            label="选中角色的游戏对象存在",
            boolean=True,
            hint="传给 setTarget 的 Character.GameObject 非空；缺失时 setter 不写，但调用方不返回 false。",
        ),
    }
    query = dict(
        kind="native_collection_query",
        source="app.cEmGridPartition.getArrayLimitedRadius",
        center="ThisObject.Transform.Position",
        radius=upper,
        additionalArguments=[1, False],
        order="原数组顺序；第一个通过过滤的对象，不排序，也不选择最近项",
        filters=[
            "Object、Object.Transform 和 ContextHolder 非空",
            "Context.AIStateManager._CurrentAIInterruptID != 0；_NextAIStateID和_CurrentAIStateID均不为0或12",
            "Context.Hold._HoldState == 0",
            "uint32(Basic.EmID - 43) >= uint32(-3)",
            "Basic.RoleID != 2",
            "not(diffRad(targetPosition - selfPosition, candidatePosition - selfPosition) > angleLimit)，保留无序比较",
            "candidateOffset.x² + candidateOffset.z² >= RangeMin²，且 <= RangeMax²；后者排除NaN",
        ],
        rangeMin=lower,
        rangeMax=upper,
        angleLimitSource="receipt.constants 中原生 diffRad 比较的 float32 常量",
        result="app.cEnemyManageInfo；选中后使用其 Character，不把它误当 TARGET_ACCESS_KEY",
        evaluationBoundary="未在离线播放器执行实时网格查询或候选数组过滤；该选择仍为显式未知条件。",
    )
    nodes = {
        "guard": dict(
            kind="condition",
            expression=runtime(
                "enemy_command_work_valid", "命令工作存在且精确类型检查通过"
            ),
            summary="检查投掷目标命令对象",
            true="first-position",
            false="return-false",
        ),
        "first-position": dict(
            kind="condition",
            expression=runtime(
                "throw_target_first_position_has_value",
                inputs["throw_target_first_position_has_value"]["hint"],
            ),
            summary="检查当前目标位置",
            true="second-position",
            false="return-false",
        ),
        "second-position": dict(
            kind="condition",
            expression=runtime(
                "throw_target_second_position_has_value",
                inputs["throw_target_second_position_has_value"]["hint"],
            ),
            summary="再次取得目标位置",
            true="references",
            false="nullable-exception",
        ),
        "nullable-exception": dict(
            kind="unknown",
            boundaryKind="native_exception",
            reason="第二次 Nullable 位置无值时构造并抛出异常；不以首次查询结果代替，也不沿普通 false 返回。",
        ),
        "references": dict(
            kind="condition",
            expression=combined(
                "all",
                *(
                    runtime(key, inputs[key]["hint"])
                    for key in (
                        "throw_target_object_valid",
                        "throw_target_transform_valid",
                    )
                )
            ),
            summary="检查目标搜索所需引用",
            true="selection",
            false="reference-exception",
        ),
        "reference-exception": dict(
            kind="unknown",
            boundaryKind="native_exception",
            reason="ThisObject 被直接解引用，Transform 缺失调用错误处理0x46；异常路径不返回普通 false。",
        ),
        "selection": dict(
            kind="condition",
            expression=dict(kind="unknown", reason=query["evaluationBoundary"]),
            summary="按实际数组顺序筛选可投掷对象",
            queryContract=query,
            true="setter-guard",
            false="return-false",
        ),
        "setter-guard": dict(
            kind="condition",
            expression=combined(
                "all",
                *(
                    runtime(key, inputs[key]["hint"])
                    for key in (
                        "throw_candidate_character_exists",
                        "throw_candidate_character_object_exists",
                    )
                )
            ),
            summary="检查第二目标 setter 所需角色引用",
            true="target-write",
            false="hold-request",
        ),
        "target-write": dict(
            kind="mutation",
            effect="update_target_positions",
            summary="将首个符合条件的角色设为第二目标",
            targetUpdates=[
                dict(
                    order=1,
                    orderName="SECOND",
                    characterSource="上述原生候选数组中首个满足过滤的 cEnemyManageInfo.Character",
                    position=None,
                    callee="app.cEmModuleTarget.setTarget(CharacterBase, TARGET_ORDER)",
                )
            ],
            invalidateTargetSnapshot=True,
            implementationBoundary="记录实际 Character setter 调用；不把选中对象或 setter 正常返回解释为投掷完成。",
            next="hold-request",
        ),
        "hold-request": dict(
            kind="unknown",
            reason="目标 setter 调用后（包括其引用 guard 不满足而未写入）创建持有检测属性，注册检测器，再调用 requestHoldSendedMediate；检测回调、持有调度与副作用尚未完整恢复。只有此调用链正常返回后，命令才返回 true。",
            boundaryKind="native_call_effects",
            continuationKind="normal_return",
            next="return-true",
        ),
    }
    return dict(
        returnType="System.Boolean",
        semanticEvidence=_evidence(RECEIPT),
        inputDefinitions=inputs,
        nativeGraph=dict(
            entry="guard", nodes=nodes, exits={"return-false": 0, "return-true": 1}
        ),
    )
