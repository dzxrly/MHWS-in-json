"""Offline analysis entry for EM0046_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0046_00_0"
NATIVE_OWNER = "Em0046_00"

GEOMETRY_EVIDENCE_FILE = "em0046_geometry.v1.json"
ON_WATER_COMMAND = "app.btable.Em0046_00BTableCommand.cCheckOnWater"
SWIM_PHASE_COMMAND = "app.btable.Em0046_00BTableCommand.cCheckSwimCombatPhase"
SWIM_PHASE_ARGUMENT = "app.btable.Em0046_00BTableCommandArg.cCheckSwimCombatPhaseType"
SWIM_UNIQUE_SPEC = dict(
    package="STM/GameDesign/Enemy/CommonData/StageResident/Data/{enemy}_StageResident.user.3.json",
    fields=["_Unique", "_SpeciesInfo", "SwimCombatData"],
)
SWIM_REMAINING_KEY = "em0046_swim_remaining_rate"
SWIM_PHASE_KEY = "extend:app.cEm0046_00Extend._IsSwimCombatPhase"
SWIM_LEVEL_KEY = "extend:app.cEm0046_00Extend._ElectricLevel"
SWIM_TIMEOUT_KEY = "extend:app.cEm0046_00Extend._SwimCombatTimer._Param._IsTimeOut"
SWIM_TIMER_EPSILON = 1.1920928955078125e-7


FORMULA_HISTORY_TABLES = {
    "app.Em0046_00_BTable_Life_Export": ("table_9fcfce5d_de75_40ed_94a2_9019e106addc",)
}


def table_history_policy(row):
    method = row["method"]
    policy = {}
    formula = FORMULA_HISTORY_TABLES.get(row["type"], ())
    if any(
        method.startswith(stem) and method[len(stem) :].isdigit() for stem in formula
    ):
        policy["formula"] = True
    return policy or None


def _geometry_proof():
    import json
    from ..shared.config import EVIDENCE_DIR

    return json.loads(
        (EVIDENCE_DIR / GEOMETRY_EVIDENCE_FILE).read_text(encoding="utf8")
    )


def verify_native_recipes(pe, metadata):
    """Verify the ray contract and timer formula against the current inputs."""
    proof = _geometry_proof()
    for row in proof["methods"]:
        method = (
            (metadata.get(row["type"]) or {}).get("methods", {}).get(row["method"], {})
        )
        start, end = int(row["address"], 16), int(row["end"], 16)
        if (
            int(method.get("function", "0"), 16) != start
            or method.get("returns", {}).get("type") != row["returns"]
            or [p.get("type") for p in method.get("params", [])] != row["parameters"]
            or pe.read(start, end - start).hex() != row["nativeBytes"]
        ):
            raise ValueError("海龙水面或水中阶段判断的原生实现变化")
    for row in [*proof["nativeProofs"], *proof["constants"]]:
        start, end = int(row["address"], 16), int(row["end"], 16)
        if pe.read(start, end - start).hex() != row["nativeBytes"]:
            raise ValueError("海龙几何或计时辅助证据变化：" + row["address"])
    for row in proof["fieldChecks"]:
        field = metadata.fields(row["type"]).get(row["field"], {})
        if (
            field.get("type") != row["fieldType"]
            or field.get("offset_from_base") != row["offset"]
        ):
            raise ValueError("海龙几何或计时字段布局变化")
    for row in proof["enumChecks"]:
        fields = (metadata.get(row["type"]) or {}).get("fields", {})
        values = {k: v["default"] for k, v in fields.items() if "default" in v}
        if values != row["values"]:
            raise ValueError("海龙水中阶段枚举变化")
    for row in proof["classSymbols"]:
        address = (metadata.get(row["type"]) or {}).get("address")
        if not address or int.from_bytes(
            pe.read(int(row["slot"], 16), 8), "little"
        ) != int(address, 16):
            raise ValueError("海龙水面判断的类型检查变化")
    return True


def _geometry_evidence(command):
    return [
        {key: row[key] for key in ("type", "method", "address", "end")}
        for row in _geometry_proof()["methods"]
        if row["type"] == command
        or command == SWIM_PHASE_COMMAND
        and row["type"] == EXTEND_TYPE
    ]


def _recover_on_water(node):
    if node.get("commandType") != ON_WATER_COMMAND:
        return None
    from ..shared.logic.expressions import combined, runtime
    from ..shared.logic.field_checks import reviewed_condition

    contacts = "em0046_water_ray_has_contacts"
    category1 = "em0046_water_ray_has_userdata_code_1"
    category2 = "em0046_water_ray_has_userdata_code_2"
    result = reviewed_condition(
        combined(
            "all",
            runtime(contacts, "CastRayResult.NumContactPoints > 0"),
            combined(
                "any",
                runtime(category1, "某个命中的 userdata 虚调用返回结构首32位为1"),
                runtime(category2, "某个命中的 userdata 虚调用返回结构首32位为2"),
            ),
        ),
        _geometry_evidence(ON_WATER_COMMAND),
        summary="怪物对象原点上下3单位的射线命中中，存在 userdata 分类代码1或2",
        inputs={
            contacts: dict(
                label="怪物上下射线有碰撞命中",
                boolean=True,
                hint="取怪物 ThisObject 的 Transform 位置，不是玩家位置；射线起点上移3单位，终点下移3单位。",
            ),
            category1: dict(
                label="射线命中中存在 userdata 代码1",
                boolean=True,
                hint="遍历全部命中；取命中 userdata 虚调用返回结构首32位。代码1的正式分类名尚未核实。",
            ),
            category2: dict(
                label="射线命中中存在 userdata 代码2",
                boolean=True,
                hint="没有 userdata 的命中不计；代码2的正式分类名尚未核实，不将其命名为深水或浅水。",
            ),
        },
    )
    result["queryContracts"] = [
        dict(
            query="via.physics.CastRayQuery",
            positionSource="cEnemyBTableCommandWork.ThisObject.Transform.Position",
            startOffset=[0.0, 3.0, 0.0],
            endOffset=[0.0, -3.0, 0.0],
            unit="游戏坐标单位，未换算成米",
            filterOverrides=dict(Layer=14, MaskBits=0),
            optionsEnabled=["NearSort", "AllHits"],
            resultFields=dict(
                hasContacts=contacts,
                hasUserDataCode1=category1,
                hasUserDataCode2=category2,
            ),
            acceptedUserDataCodes=[1, 2],
            userdataCategoryNamesVerified=False,
            selection="遍历全部命中；任一非空userdata的分类首32位为1或2即成立，不限于最近命中",
            execution="静态核实的查询合同；本次没有运行地图射线查询",
        )
    ]
    return result


def _recover_swim_phase(node, enemy_id, resources):
    if node.get("commandType") != SWIM_PHASE_COMMAND or enemy_id != ENEMY_ID:
        return None
    from ..shared.logic.expressions import combined, compare, runtime
    from ..shared.logic.field_checks import reviewed_condition
    from ..shared.logic.values import enum_number, number
    from ..shared.models.player_view import signed_intervals

    if node.get(
        "argumentType"
    ) != SWIM_PHASE_ARGUMENT or "_SwimCombatPhase" not in node.get("argument", {}):
        return None
    mode = enum_number(node["argument"]["_SwimCombatPhase"])
    params, sources = resources.package_value(enemy_id, SWIM_UNIQUE_SPEC)
    rates = {
        name: number(params[name])
        for name in ("_Level2UpTimeRate", "_Level3UpTimeRate")
    }
    inputs = {
        SWIM_PHASE_KEY: dict(
            label="水中战斗阶段已启用",
            boolean=True,
            hint="cEm0046_00Extend._IsSwimCombatPhase；不是当前姿态或是否接触水面。",
        ),
        SWIM_LEVEL_KEY: dict(
            label="海龙当前电力等级",
            options=[
                dict(label="NORMAL", value=0),
                dict(label="LEVEL_1", value=1),
                dict(label="LEVEL_2", value=2),
                dict(label="LEVEL_3", value=3),
            ],
        ),
    }
    if mode in (0, 1):
        field = "_Level2UpTimeRate" if mode == 0 else "_Level3UpTimeRate"
        inputs[SWIM_REMAINING_KEY] = dict(
            label="水中战斗计时的剩余比例",
            number=True,
            signed=True,
            numericRange=dict(min=-3.4028234663852886e38, max=None),
            hint="计时器派生值输入，不是命令最终结果。先将t和L按float32读取：t≤FLT_EPSILON时p=0；否则L≤FLT_EPSILON时p=1；否则p=float32(t/L)。比例=float32(100.0-double(p)*100.0)。原生不夹取到0–100，缺少该值保持未知。",
            **signed_intervals(rates.values(), unit="%"),
        )
        level = compare(
            SWIM_LEVEL_KEY,
            1 if mode == 0 else 3,
            "eq" if mode == 0 else "ne",
            source="当前电力等级",
        )
        condition = combined(
            "all", level, compare(SWIM_REMAINING_KEY, rates[field], "le", source=field)
        )
        summary = f"水中战斗已启用，电等级{'为LEVEL_1' if mode == 0 else '不是LEVEL_3'}且剩余比例 ≤ {rates[field]:g}%"
    elif mode == 2:
        inputs[SWIM_TIMEOUT_KEY] = dict(
            label="水中战斗计时器的超时标志已设置",
            boolean=True,
            hint="读取ace.cTimer._Param._IsTimeOut，不能仅据本函数替换成t≥L。",
        )
        condition = combined(
            "all",
            compare(SWIM_LEVEL_KEY, 3, source="当前电力等级"),
            runtime(SWIM_TIMEOUT_KEY, "计时器存储的_IsTimeOut标志"),
        )
        summary = "水中战斗已启用，当前为LEVEL_3且计时器超时标志已设置"
    else:
        condition = dict(kind="constant", value=False)
        summary = "未定义的水中阶段参数返回假"
    result = reviewed_condition(
        combined("all", runtime(SWIM_PHASE_KEY, "水中战斗阶段已启用"), condition),
        _geometry_evidence(SWIM_PHASE_COMMAND),
        summary=summary,
        extend=EXTEND_TYPE,
        inputs=inputs,
    )
    result["thresholdSources"] = [
        dict(
            resources=sources,
            runtimePath="cEm0046_00Extend.ParamUnique.SwimCombatData",
            values=rates,
        )
    ]
    result["queryContracts"] = [
        dict(
            query="ace.cTimer._Param派生比例",
            execution="不在网页中重新计算t/L；数值作为明确定义的场景输入",
            timerField="_Timer",
            limitField="_Limit",
            epsilon=SWIM_TIMER_EPSILON,
            progressBranches=[
                dict(condition="t <= epsilon", value=0),
                dict(condition="L <= epsilon", value=1),
                dict(condition="otherwise", value="float32(t / L)"),
            ],
            remainingRate="float32(100.0 - double(progress) * 100.0)",
            clamped=False,
            thresholdComparison="remainingRate <= resourceThreshold，包含相等；无序浮点比较不成立",
            finish="LEVEL_3 且计时器存储的_IsTimeOut非0，不重建计时器每帧更新",
        )
    ]
    return result


# cIsSwimCombatPhase (game 1.42.0.2): cEm0046_00Extend
# _DoneSwimCombatPhaseEndAction (+0x116) is false and _IsSwimCombatPhase
# (+0x10e) is true.
FIELD_CHECKS = {
    "app.btable.Em0046_00BTableCommand.cIsSwimCombatPhase": dict(
        spec=(
            "all",
            ("not", ("extend:_DoneSwimCombatPhaseEndAction",)),
            ("extend:_IsSwimCombatPhase",),
        ),
        extend="app.cEm0046_00Extend",
        evidence=[
            dict(
                type="app.btable.Em0046_00BTableCommand.cIsSwimCombatPhase",
                method="onExecute1233781",
                address="0x144194fe0",
                end="0x144195030",
            )
        ],
        summary="IsSwimCombatPhase 成立且 DoneSwimCombatPhaseEndAction 不成立",
    ),
}


def recover_condition(node, enemy_id, resources):
    """Reviewed field-comparison commands of this monster (FIELD_CHECKS)."""
    from ..shared.logic.field_checks import declared_condition

    geometry = _recover_on_water(node) or _recover_swim_phase(node, enemy_id, resources)
    if geometry is not None:
        return geometry
    water = _recover_hunters_or_mission(node)
    return water if water is not None else declared_condition(FIELD_CHECKS, node)


SWIM_HUNTER_COMMAND = "app.btable.Em0046_00BTableCommand.cCheckSwimHunterNum"
HUNTER_WATER_COMMAND = "app.btable.Em0046_00BTableCommand.cCheckHunterInWater"
STORY_COMMAND = "app.btable.Em0046_00BTableCommand.cIsStroyQuest"
STORY_MISSION_ID = 524  # MissionIDList.ID.MISSION_720015


def _recover_hunters_or_mission(node):
    from ..shared.logic.expressions import compare
    from ..shared.logic.field_checks import condition_evidence, reviewed_condition
    from ..shared.logic.values import scalar

    command = node.get("commandType")
    if command == STORY_COMMAND:
        key = "enabled_main_mission_id"
        return reviewed_condition(
            compare(
                key,
                STORY_MISSION_ID,
                source="MissionManager.getEnableMainMissionID()，MISSION_720015",
            ),
            condition_evidence("sea_story_mission"),
            summary="当前启用的主线任务为 MISSION_720015",
            inputs={
                key: dict(
                    label="当前启用的主线任务枚举值", number=True, min=-1, max=None
                )
            },
        )
    if command not in (SWIM_HUNTER_COMMAND, HUNTER_WATER_COMMAND):
        return None
    count = (
        scalar(node["argument"]["_CheckHunterNum"])
        if command == SWIM_HUNTER_COMMAND
        else 0
    )
    if type(count) is not int:
        return None
    operator = "eq" if command == SWIM_HUNTER_COMMAND else "gt"
    key = "em0046_hunters_in_water"
    return reviewed_condition(
        compare(
            key,
            count,
            operator,
            source="cEm0046_00Extend.getHunterNumInWater：上下文与水体数据有效、水相关量为正且 ContinueFlag 168 成立的猎人数",
        ),
        condition_evidence(
            "sea_swim_hunter_count"
            if command == SWIM_HUNTER_COMMAND
            else "sea_hunter_in_water"
        ),
        summary=f"符合水中判据的猎人数 {'=' if operator == 'eq' else '>'} {count}",
        extend="app.cEm0046_00Extend",
        inputs={
            key: dict(
                label="符合水中判据的猎人数", number=True, min=0, max=None, unit="人"
            )
        },
    )


# Verified Extend rule of this monster (game 1.42.0.2); the record lives in
# data/rules.v1.json, the offsets below are checked by the curation command.
EXTEND_TYPE = "app.cEm0046_00Extend"
ELECTRIC_LEVEL_COMMAND = "app.btable.Em0046_00BTableCommand.cCheckElectricLevel"
ELECTRIC_LEVEL_OFFSET = 0x108
# A required level 2 also accepts internal value 3.
ELECTRIC_LEVEL_TWO = (2, 3)

RULE_SPECS = (
    (
        ELECTRIC_LEVEL_COMMAND,
        "electric",
        "专用",
        "要求电力等级 2 时接受内部值 2 或 3；其余等级使用相等比较",
        {"value": 0x10},
        EXTEND_TYPE,
        ELECTRIC_LEVEL_OFFSET,
    ),
)


def _compile_electric(compiler, predicate, values):
    from ..shared.logic.values import enum_number
    from ..shared.models.player_view import missing_state

    if not predicate.get("contextBinding"):
        return missing_state()
    key, _ = compiler.context_field(predicate["contextBinding"])
    expected = enum_number(values["value"])
    if expected == ELECTRIC_LEVEL_TWO[0]:
        return dict(
            op="any",
            items=[compiler.context_option(key, v) for v in ELECTRIC_LEVEL_TWO],
        )
    return compiler.context_option(key, expected)


def _evaluate_electric(rule, bound, context, state):
    from ..shared.logic.predicates import context_value
    from ..shared.logic.values import enum_number

    actual = context_value(state, bound["contextBinding"])
    expected = enum_number(bound["values"]["value"])
    if expected == ELECTRIC_LEVEL_TWO[0]:
        return actual in ELECTRIC_LEVEL_TWO
    return actual == expected


RULE_KINDS = {"electric": dict(compile=_compile_electric, evaluate=_evaluate_electric)}


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
