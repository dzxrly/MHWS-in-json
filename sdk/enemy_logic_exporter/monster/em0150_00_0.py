"""Offline analysis entry for EM0150_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0150_00_0"
NATIVE_OWNER = "Em0150_00"

MODE_CHANGE_COMMAND = "app.btable.Em0150_00BTableCommand.cCheckModeChange"
MIN_MODE_THRESHOLD = 0.0010000000474974513  # float32 at the reviewed native constant
UNIQUE_SPEC = dict(
    package="STM/GameDesign/Enemy/CommonData/StageResident/Data/{enemy}_StageResident.user.3.json",
    fields=["_Unique", "_SpeciesInfo"],
)
THROW_COMMAND = "app.btable.Em0150_00BTableCommand.cSetDestZakoThrow"
THROW_ARGUMENT = "app.btable.Em0150_00BTableCommand.cSetDestZakoThrowArg"
WALL_COMMAND = "app.btable.Em0150_00BTableCommand.cSetDestGimmickWall"
WALL_RECEIPT = "em0150_wall_target.v1.json"


def verify_native_recipes(pe, metadata):
    from ..shared.logic.target_command_effects import verify_target_receipt

    return verify_target_receipt(pe, metadata, WALL_RECEIPT)


def recover_target_command_effect(bound, evidence):
    from ..shared.logic.throw_target import throw_target_effect

    if bound.get("commandType") == THROW_COMMAND:
        return throw_target_effect(
            bound, evidence, command=THROW_COMMAND, argument_type=THROW_ARGUMENT
        )
    if bound.get("commandType") != WALL_COMMAND:
        return None
    from ..shared.logic.target_command_effects import _evidence, _match, target_receipt
    from ..shared.logic.expressions import combined, compare, runtime

    _match(WALL_COMMAND, evidence, WALL_RECEIPT)
    invalid_index = next(
        row["value"]
        for row in target_receipt(WALL_RECEIPT)["constants"]
        if row.get("name") == "invalidGimmickUniqueIndex"
    )
    if bound.get("argumentType") not in (
        "",
        "ace.btable.cCommandArgumentNone",
    ) or bound.get("argument"):
        raise ValueError("墙面目标命令不接受资源参数")
    inputs = {}

    def flag(key, label, source):
        inputs[key] = dict(label=label, boolean=True, hint=source)
        return runtime(key, source)

    def node(expression, yes, no="return", summary="检查墙面目标来源"):
        return dict(
            kind="condition", expression=expression, true=yes, false=no, summary=summary
        )

    work = runtime("enemy_command_work_valid", "命令工作存在且精确类型检查通过")
    available = combined(
        "all",
        flag(
            "wall_exclusive_point_exists",
            "独占点查询返回对象",
            "useBegin(GIMMICK=1, makeTargetAccessKey(ThisObject), false) 的原始对象返回值非空",
        ),
        flag(
            "wall_sub_unique_id_has_value",
            "独占点有子标识",
            "返回对象 cExclusivePoint._SubUniqueID.HasValue",
        ),
    )
    index = "extend:app.cEm0150_00Extend.TargetGimmickUniqueIndex"
    inputs[index] = dict(
        label="已保存的墙面对象编号",
        number=True,
        hint="自身 Extend.TargetGimmickUniqueIndex；-1为无值，未把此编号直接当目标位置。",
    )
    fallback = combined(
        "all",
        runtime("self_extend_valid", "Extend 精确类型为 app.cEm0150_00Extend"),
        compare(index, -1, "ne", source=inputs[index]["hint"]),
        compare(index, invalid_index, "ne", source="原生静态INVALID Gimmick编号"),
        flag(
            "wall_fallback_gimmick_exists",
            "已保存的墙面对象存在",
            "getGimmickUniqueIndex(Extend.TargetGimmickUniqueIndex) 的返回值非空",
        ),
        flag(
            "wall_fallback_object_exists",
            "墙面游戏对象存在",
            "返回 Gimmick 的 GameObject 非空",
        ),
    )
    state_key = "wall_fallback_base_state"
    inputs[state_key] = dict(
        label="墙面基础状态值",
        number=True,
        hint="Gimmick._ContextHolder.Gimmick.BaseParam.BaseState 的原始枚举值；原生仅接受0或3，不自行翻译状态名称。",
    )
    fallback_parameter_refs = combined(
        "all",
        *(
            flag(key, label, source)
            for key, label, source in (
                (
                    "wall_fallback_context_holder_exists",
                    "墙面上下文容器存在",
                    "Gimmick._ContextHolder非空；原生直接解引用",
                ),
                (
                    "wall_fallback_context_exists",
                    "墙面上下文存在",
                    "ContextHolder.Gimmick非空；原生直接解引用",
                ),
                (
                    "wall_fallback_base_param_exists",
                    "墙面基础参数存在",
                    "GimmickContext.BaseParam非空；原生直接读取BaseState",
                ),
            )
        ),
    )
    sub_index = "wall_point_sub_unique_id"
    inputs[sub_index] = dict(
        label="独占点子编号",
        number=True,
        hint="独占点_SubUniqueID.Value；此处已检查HasValue。",
    )
    point = combined(
        "all",
        compare(
            sub_index,
            invalid_index,
            "ne",
            source="独占点_SubUniqueID.Value不为原生INVALID",
        ),
        flag(
            "wall_point_gimmick_exists",
            "独占点对应墙面对象存在",
            "getGimmickUniqueIndex(_SubUniqueID.Value) 返回非空；INVALID编号正常返回",
        ),
        flag(
            "wall_point_gimmick_type_matches",
            "独占点对应墙面类型匹配",
            "返回对象精确类型为app.Gm001_004；不匹配时正常返回",
        ),
        flag(
            "wall_point_object_exists",
            "独占点墙面游戏对象存在",
            "Gimmick.GameObject非空；缺失时正常返回",
        ),
    )
    parameter_refs = combined(
        "all",
        flag(
            "wall_point_parameter_type_matches",
            "墙面攻击点参数类型匹配",
            "_BaseComponents读取的参数精确类型为app.user_data.Gm001_004_BbbUniqueParam；失败的cast随后被裸解引用，属于异常边界",
        ),
        flag(
            "wall_point_array_exists",
            "墙面攻击点数组存在",
            "Gm001_004_BbbUniqueParam._AttackPointInfo非空；直接读取Length",
        ),
    )
    refs = flag(
        "wall_gimmick_transform_exists",
        "墙面位置组件存在",
        "已确认 GameObject 存在之后，其 Transform 非空；缺失时调用错误处理0x46并触发陷阱。",
    )
    proof = _evidence(WALL_RECEIPT)

    def write(position, summary, **extra):
        return dict(
            kind="mutation",
            effect="update_target_positions",
            summary=summary,
            targetUpdates=[
                dict(
                    order=0,
                    orderName="FIRST",
                    category=18,
                    categoryName="UNIQUE",
                    position=position,
                    direction=None,
                    booleanOptions=[False, False],
                    nullableUInt32=None,
                    callee="app.cEmModuleTarget.setTarget(via.vec3, TARGET_POINT_CATEGORY, ...)",
                )
            ],
            invalidateTargetSnapshot=True,
            implementationBoundary="仅声明调用方目标写入和原生向量来源；不运行地图查询或导航，也不宣称独占点申请成功。",
            next="return",
            **extra,
        )

    nodes = dict(
        guard=node(work, "begin", summary="检查墙面目标命令对象"),
        begin=dict(
            kind="mutation",
            effect="request_exclusive_point",
            summary="申请墙面独占点",
            implementationBoundary="调用useBegin，类别GIMMICK=1、当前ThisObject键、false；管理器占用与同步副作用仍由下一边界承载。",
            next="exclusive-call",
        ),
    )
    nodes.update(
        {
            "exclusive-call": dict(
                kind="unknown",
                boundaryKind="native_call_effects",
                reason="独占点 useBegin 的占用、释放及网络同步副作用尚未完整恢复；只有正常返回后才检查其实际返回对象。",
                continuationKind="normal_return",
                next="exclusive-result",
            ),
            "exclusive-result": node(
                available, "point", "fallback", "检查独占点查询返回值"
            ),
            "point": node(point, "point-parameters"),
            "point-parameters": node(
                parameter_refs,
                "point-index",
                "parameter-exception",
                "检查墙面攻击点参数引用",
            ),
            "point-index": node(
                dict(
                    kind="unknown",
                    reason="_UniqueID 对_AttackPointInfo的有符号上界检查、索引解引用和非空候选尚未完整恢复；越过上界或候选为空正常返回，负索引及无效引用仍未证明。",
                ),
                "point-references",
            ),
            "parameter-exception": dict(
                kind="unknown",
                boundaryKind="native_exception",
                reason="墙面参数精确类型cast失败后仍直接读取其_AttackPointInfo，或数组为空时直接读取Length；不沿普通void返回。",
            ),
            "fallback": node(fallback, "fallback-parameters"),
            "fallback-parameters": node(
                fallback_parameter_refs,
                "fallback-state",
                "parameter-exception",
                "检查墙面基础状态引用",
            ),
            "fallback-state": node(
                combined(
                    "any",
                    compare(state_key, 0, source=inputs[state_key]["hint"]),
                    compare(state_key, 3, source=inputs[state_key]["hint"]),
                ),
                "fallback-references",
                summary="检查墙面基础状态",
            ),
            "point-references": node(
                refs, "point-direction", "exception", "检查墙面位置引用"
            ),
            "point-direction": dict(
                kind="mutation",
                effect="write_native_direction",
                summary="更新墙面动作朝向",
                partialImplementationEffects=[
                    dict(
                        destination="Context.ActionArgument.Destination._Direction",
                        nativeFieldWrites="HasValue(+0x30)=true，清除填充(+0x31/+0x38)并写入方向向量(+0x40)",
                        sourceProgram="receipt.vectorPrograms.pointDirection",
                        fieldIdentityVerified=True,
                        writtenBeforeTargetSetter=True,
                    )
                ],
                implementationBoundary="此方向写入先于后续重复GameObject/Transform读取和目标setter；后续失败时它可能已经发生，不与最终目标写入合并。",
                next="point-position",
            ),
            "point-position": dict(
                kind="unknown",
                boundaryKind="native_call_effects",
                reason="方向已写入；接下来重复读取GameObject/Transform、调用原生getter并执行位置向量运算。getter属性身份和异常路径尚未完全闭合，只有这段正常完成后才调用目标setter。",
                continuationKind="normal_return",
                next="point-write",
            ),
            "fallback-references": node(
                refs, "fallback-write", "exception", "检查墙面位置引用"
            ),
            "exception": dict(
                kind="unknown",
                boundaryKind="native_exception",
                reason="墙面 GameObject.Transform 缺失时调用错误处理0x46并触发陷阱，不继续到调用方。",
            ),
            "point-write": write(
                dict(
                    kind="native_vector_formula",
                    formula="Transform.Position + native_rotate(Transform getter output, selectedPoint local offset)",
                    sourceProgram="receipt.vectorPrograms.pointPosition",
                    localOffset="selectedPoint+0x10 的三个float32",
                    transformGetterIdentityVerified=False,
                    arithmetic="保存完整原生SIMD序列及调用来源；未以猜测的Quaternion或Euler字段替代尚未闭合的getter身份。",
                ),
                "按独占点局部偏移更新墙面目标",
            ),
            "fallback-write": write(
                dict(
                    kind="native_vector_source",
                    source="已保存墙面 Gimmick.GameObject.Transform 的当前原生位置getter返回值",
                    sourceProgram="receipt.vectorPrograms.fallbackPosition",
                ),
                "按已保存墙面对象更新目标",
            ),
        }
    )
    return dict(
        returnType="System.Void",
        inputDefinitions=inputs,
        semanticEvidence=proof,
        nativeGraph=dict(entry="guard", nodes=nodes, exits={"return": None}),
    )


def recover_condition(node, enemy_id, resources):
    if node.get("commandType") != MODE_CHANGE_COMMAND:
        return None
    from ..shared.logic.expressions import combined, compare
    from ..shared.logic.field_checks import condition_evidence, reviewed_condition

    parameters, sources = resources.package_value(enemy_id, UNIQUE_SPEC)
    lower, upper, legendary = (
        parameters[k]
        for k in (
            "ModeChangeThreshold_Lower",
            "ModeChangeThreshold_Upper",
            "ModeChangeThreshold_Legendary",
        )
    )
    if any(type(value) not in (int, float) for value in (lower, upper, legendary)):
        raise ValueError("辟兽模式切换的生命阈值不是数值")
    health = "health_percent"
    rank = "environment_current_rank"
    history = "self_basic_legendary_id"
    mode = "extend:app.cEm0150_00Extend.Mode"
    # For non-legendary enemies RANK==1 selects Lower, all other ranks Upper.
    branches = []
    for guards, threshold in (
        ((compare(history, 0, "ne", source="Basic.LegendaryID"),), legendary),
        (
            (
                compare(history, 0, source="Basic.LegendaryID"),
                compare(rank, 1, source="EnvironmentManager.CurrentRank"),
            ),
            lower,
        ),
        (
            (
                compare(history, 0, source="Basic.LegendaryID"),
                compare(rank, 1, "ne", source="EnvironmentManager.CurrentRank"),
            ),
            upper,
        ),
    ):
        if threshold >= MIN_MODE_THRESHOLD:
            branches.append(
                combined(
                    "all",
                    *guards,
                    compare(
                        health,
                        threshold,
                        "lt",
                        source="HealthNormalized × 100，原生严格小于模式切换阈值",
                    ),
                )
            )
    result = reviewed_condition(
        combined(
            "all",
            compare(mode, 1, "ne", source="当前模式不为 SUPER_BURST"),
            (
                combined("any", *branches)
                if branches
                else dict(kind="constant", value=False)
            ),
        ),
        condition_evidence("doshaguma_mode"),
        summary=f"非 SUPER_BURST；普通生命低于 {lower:g}%（下位）或 {upper:g}%（其他任务等级），历战低于 {legendary:g}%",
        extend="app.cEm0150_00Extend",
        inputs={
            health: dict(label="生命值百分比", number=True, min=0, max=100, unit="%"),
            mode: dict(
                label="当前模式",
                options=[
                    dict(label="DEFAULT", value=0),
                    dict(label="SUPER_BURST", value=1),
                ],
            ),
        },
    )
    result["parameterSources"] = sources
    result["parameterBinding"] = UNIQUE_SPEC
    return result


def extract(context):
    """Select this monster's declared tables, imports and native method contexts."""
    return context.extract_enemy(ENEMY_ID, NATIVE_OWNER)


def build_model(
    exe,
    metadata,
    natives,
    native_index,
    helper_index,
    *,
    requests_path=None,
    inventory_path=None,
    context=None,
):
    """Extract this EM from its real slot/import closure and typed native calls."""
    from ..shared.models.native_recipe import build_monster

    return build_monster(
        ENEMY_ID,
        NATIVE_OWNER,
        exe,
        metadata,
        natives,
        native_index,
        helper_index,
        requests_path=requests_path,
        inventory_path=inventory_path,
        context=context,
    )
