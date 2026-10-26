"""Offline analysis entry for EM0078_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0078_00_0"
NATIVE_OWNER = "Em0078_00"

HILL_COMMAND = "app.btable.Em0078_00BTableCommand.cCheckDestHill"
HILL_EVIDENCE_FILE = "em0078_hill.v1.json"
HILL_ATTRIBUTE = 0x2000


def _hill_proof():
    import json
    from ..shared.config import EVIDENCE_DIR

    return json.loads((EVIDENCE_DIR / HILL_EVIDENCE_FILE).read_text(encoding="utf8"))


def verify_native_recipes(pe, metadata):
    """Keep capsule selection, target source, and the hill bit version-bound."""
    proof = _hill_proof()
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
            raise ValueError("巨戟龙目标高台判断的原生实现变化")
    for row in [*proof["nativeProofs"], *proof["constants"]]:
        start, end = int(row["address"], 16), int(row["end"], 16)
        if pe.read(start, end - start).hex() != row["nativeBytes"]:
            raise ValueError("巨戟龙高台查询的原生常量变化")
    for row in proof["fieldChecks"]:
        field = metadata.fields(row["type"]).get(row["field"], {})
        if (
            field.get("type") != row["fieldType"]
            or field.get("offset_from_base") != row["offset"]
        ):
            raise ValueError("巨戟龙高台查询的字段布局变化")
    for row in proof["enumChecks"]:
        fields = (metadata.get(row["type"]) or {}).get("fields", {})
        values = {k: v["default"] for k, v in fields.items() if "default" in v}
        if values != row["values"] or values.get("EM0078_HILL") != HILL_ATTRIBUTE:
            raise ValueError("巨戟龙高台体素标记变化")
    for row in proof["classSymbols"]:
        address = (metadata.get(row["type"]) or {}).get("address")
        if not address or int.from_bytes(
            pe.read(int(row["slot"], 16), 8), "little"
        ) != int(address, 16):
            raise ValueError("巨戟龙高台判断的类型检查变化")
    query = proof["queryMethod"]
    method = (
        (metadata.get(query["type"]) or {}).get("methods", {}).get(query["method"], {})
    )
    if (
        int(method.get("function", "0"), 16) != int(query["address"], 16)
        or method.get("returns", {}).get("type") != "System.Boolean"
        or [p.get("type") for p in method.get("params", [])][1:2] != ["via.Capsule"]
    ):
        raise ValueError("巨戟龙高台查询的胶囊接口变化")
    return True


def _recover_dest_hill(node):
    if node.get("commandType") != HILL_COMMAND:
        return None
    from ..shared.logic.expressions import combined, runtime
    from ..shared.logic.field_checks import reviewed_condition

    target = "em0078_hill_target_position_available"
    query = "em0078_hill_capsule_query_succeeded"
    candidate = "em0078_hill_eligible_nearest_exists"
    attribute = "em0078_hill_nearest_has_hill_attribute"
    result = reviewed_condition(
        combined(
            "all",
            runtime(target, "Context.Target.getTargetPosition(0,false)有值"),
            runtime(query, "VoxelDataManager.getDataInfoList胶囊查询成功"),
            runtime(candidate, "查询内存在满足高度条件且可选为最近项的DATA_INFO"),
            runtime(attribute, "最近项的_GroundAttr含EM0078_HILL位"),
        ),
        [
            {key: row[key] for key in ("type", "method", "address", "end")}
            for row in _hill_proof()["methods"]
        ],
        summary="第0目标附近符合高度条件的最近体素带巨戟龙高台标记",
        extend="app.cEm0078_00Extend",
        inputs={
            target: dict(
                label="第0目标有可用位置",
                boolean=True,
                hint="Context.Target.getTargetPosition(0,false)；目标可为角色、位置或路线，不固定指玩家。",
            ),
            query: dict(
                label="目标位置附近的胶囊体素查询成功",
                boolean=True,
                hint="胶囊端点为P和P−(0,3,0)，半径4.5；没有在本次离线构建中执行实际地图查询。",
            ),
            candidate: dict(
                label="胶囊查询有符合高度条件的最近体素",
                boolean=True,
                hint="仅考虑位置Q.y≤P.y+1的候选，按到P的三维距离平方选最近项；距离相同时保留先遇到的项。",
            ),
            attribute: dict(
                label="所选最近体素带巨戟龙高台标记",
                boolean=True,
                hint="只检查已选最近项的_GroundAttr & EM0078_HILL(0x2000)，不是检查范围内任意体素。",
            ),
        },
    )
    result["queryContracts"] = [
        dict(
            query="VoxelDataManager.getDataInfoList(out List<DATA_INFO>,via.Capsule,in Func)",
            positionSource="Context.Target.getTargetPosition(index=0,optionalBool=false)",
            capsule=dict(
                startOffset=[0.0, 0.0, 0.0], endOffset=[0.0, -3.0, 0.0], radius=4.5
            ),
            unit="游戏坐标单位，未换算成米",
            extraPredicate=None,
            candidateHeight="有限坐标下Q.y <= P.y + 1；原生仅在有序Q.y > P.y+1时跳过",
            nearestSelection="按三维距离平方严格小于当前最小值时替换；无序距离不选择；相同距离保留先遇到项",
            attributeTest=dict(
                field="_GroundAttr",
                mask=HILL_ATTRIBUTE,
                name="EM0078_HILL",
                selectedItemOnly=True,
            ),
            resultFields=dict(
                targetAvailable=target,
                querySucceeded=query,
                eligibleNearestExists=candidate,
                selectedHasAttribute=attribute,
            ),
            emptyOrFailed=False,
            execution="静态核实的查询合同；实际地图查询结果作为独立场景事实输入",
        )
    ]
    return result


# cCheckUnusedHill (game 1.42.0.2): cEm0078_00Extend _Phase (+0x2e8) is
# MIDFIELD and _IsUnusedHill (+0x341) is true.
FIELD_CHECKS = {
    "app.btable.Em0078_00BTableCommand.cCheckUnusedHill": dict(
        spec=("all", ("extend:_Phase", "==", 1), ("extend:_IsUnusedHill",)),
        extend="app.cEm0078_00Extend",
        evidence=[
            dict(
                type="app.btable.Em0078_00BTableCommand.cCheckUnusedHill",
                method="onExecute1233936",
                address="0x144d29ad0",
                end="0x144d29b10",
            )
        ],
        summary="Phase 为 MIDFIELD 且 IsUnusedHill 成立",
        enums={"extend:_Phase": {"EARLY": 0, "MIDFIELD": 1, "FINAL": 2}},
    ),
}


def recover_condition(node, enemy_id, resources):
    """Reviewed field-comparison commands of this monster (FIELD_CHECKS)."""
    from ..shared.logic.field_checks import declared_condition

    hill = _recover_dest_hill(node)
    return hill if hill is not None else declared_condition(FIELD_CHECKS, node)


# cCheckPhase (game 1.42.0.2, onExecute 0x143ba5250..0x143ba52b6): when
# cEm0078_00Extend._Phase (0x2e8) is FINAL and _IsFinishAreaMove (0x345) is
# false, the argument is compared with MIDFIELD; otherwise with _Phase. The
# reviewed record, enum values and evidence live in data/rules.v1.json.
PHASE_COMMAND = "app.btable.Em0078_00BTableCommand.cCheckPhase"
PHASE_FINAL = "FINAL"
PHASE_MIDFIELD = "MIDFIELD"


def _compile_phase(compiler, predicate, values):
    from ..shared.logic.values import enum_number
    from ..shared.models.player_view import comparison, extend_field_label

    binding = predicate["contextBinding"]
    phase = f"extend:{binding['type']}.{binding['field']}"
    finished = f"extend:{binding['type']}.{binding['flagField']}"
    names = compiler.rules[predicate["commandType"]]["enumValues"]
    compiler.choices(
        phase,
        "专用状态 " + extend_field_label(phase),
        [dict(label=name, value=value) for name, value in names.items()],
    )
    compiler.boolean(finished, "专用状态 " + extend_field_label(finished))
    expected = enum_number(values["value"])
    final, midfield = names[PHASE_FINAL], names[PHASE_MIDFIELD]
    # A FINAL phase reads as MIDFIELD until the area move has finished.
    if expected == midfield:
        return dict(
            op="any",
            items=[
                comparison(phase, "eq", midfield),
                dict(
                    op="all",
                    items=[
                        comparison(phase, "eq", final),
                        comparison(finished, "eq", False),
                    ],
                ),
            ],
        )
    if expected == final:
        return dict(
            op="all",
            items=[comparison(phase, "eq", final), comparison(finished, "eq", True)],
        )
    return comparison(phase, "eq", expected)


def _evaluate_phase(rule, bound, context, state):
    from ..shared.logic.predicates import context_value
    from ..shared.logic.values import MissingState, enum_number, required

    binding = bound["contextBinding"]
    actual = context_value(state, binding)
    names = rule["enumValues"]
    finished = required(state, binding["flagField"])
    if type(finished) is not bool:
        raise MissingState("区域移动结束标志必须是布尔值")
    if actual == names[PHASE_FINAL] and not finished:
        actual = names[PHASE_MIDFIELD]
    return actual == enum_number(bound["values"]["value"])


RULE_KINDS = {
    "phase_after_area_move": dict(compile=_compile_phase, evaluate=_evaluate_phase)
}


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
