"""Offline analysis entry for EM0160_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0160_00_0"
NATIVE_OWNER = "Em0160_00"

MODE_COMMAND = "app.Em0160_00BTableCommand.cCheckChangeMode"
MIN_MODE_THRESHOLD = 0.0010000000474974513  # float32 at the reviewed native constant
UNIQUE_SPEC = dict(
    package="STM/GameDesign/Enemy/CommonData/StageResident/Data/{enemy}_StageResident.user.3.json",
    fields=["_Unique", "_GenusInfo"],
)
ABSORBED_ACTION_COMMAND = "app.Em0160_00BTableCommand.cCanAbsorbedAction"
ABSORBED_STATE_KEY = "extend:app.cEm0160Extend._AbsorbCocoonState"
LOCAL_HISTORY_TABLE = "table_b703035f_fa40_4c4c_a4eb_629aa0247b36"
LOCAL_HISTORY_TABLES = (
    LOCAL_HISTORY_TABLE,
    "table_0d7f8b3f_9c2b_457a_83f6_40eddaa80312",
)
FORMULA_HISTORY_TABLES = (
    "table_5a438c68_cd51_4292_ac34_b1406d7fa238",
    "table_70850a29_17cd_4bc1_b942_ac6177bb861c",
)
LOCAL_HISTORY_EXPORT = "app.Em0160_00_BTable_CommonAttack_Export"


def table_history_policy(row):
    if row["type"] != LOCAL_HISTORY_EXPORT:
        return None
    method = row["method"]
    local = any(
        method.startswith(stem) and method[len(stem) :].isdigit()
        for stem in LOCAL_HISTORY_TABLES
    )
    formula = any(
        method.startswith(stem) and method[len(stem) :].isdigit()
        for stem in FORMULA_HISTORY_TABLES
    )
    policy = {}
    if local:
        policy["local"] = True
    if formula:
        policy["formula"] = True
    return policy or None


def _absorbed_action_proof():
    import json
    from ..shared.config import EVIDENCE_DIR

    return json.loads(
        (EVIDENCE_DIR / "em0160_absorbed_action.v1.json").read_text(encoding="utf-8")
    )


def verify_native_recipes(pe, metadata):
    proof = _absorbed_action_proof()
    row = proof["command"]
    method = (metadata.get(row["type"]) or {}).get("methods", {}).get(row["method"], {})
    start, end = int(row["address"], 16), int(row["end"], 16)
    if (
        int(method.get("function", "0"), 16) != start
        or method.get("returns", {}).get("type") != "System.Boolean"
        or [p.get("type") for p in method.get("params", [])]
        != ["ace.btable.cCommandWork"]
        or pe.read(start, end - start).hex() != row["nativeBytes"]
    ):
        raise ValueError("锁刃龙吸收后动作判断的原生实现变化")
    for symbol in proof["classSymbols"]:
        actual = (metadata.get(symbol["type"]) or {}).get("address")
        if not actual or int.from_bytes(
            pe.read(int(symbol["slot"], 16), 8), "little"
        ) != int(actual, 16):
            raise ValueError("锁刃龙吸收后动作判断的类型检查变化")
    for owner, fields in proof["layouts"].items():
        for name, expected in fields.items():
            field = metadata.fields(owner).get(name, {})
            if (
                field.get("type") != expected["type"]
                or field.get("offset_from_base") != expected["offset"]
            ):
                raise ValueError("锁刃龙吸收后动作判断的字段布局变化")
    enum = proof["stateEnum"]
    fields = (metadata.get(enum["type"]) or {}).get("fields", {})
    if any(
        fields.get(name, {}).get("default") != enum[name]
        for name in ("WAIT_ACTION", "AFTER")
    ):
        raise ValueError("锁刃龙吸收后状态枚举变化")
    return True


def recover_boolean_command_effect(row, metadata, pe):
    if row["type"] != ABSORBED_ACTION_COMMAND:
        return None
    verify_native_recipes(pe, metadata)
    proof = _absorbed_action_proof()
    if any(
        row.get(key) != proof["command"][key]
        for key in ("type", "method", "address", "end")
    ):
        raise ValueError("锁刃龙吸收后动作判断的方法上下文不匹配")
    from ..shared.logic.expressions import compare
    from ..shared.logic.field_checks import reviewed_condition

    state = proof["stateEnum"]
    evidence = [
        {key: proof["command"][key] for key in ("type", "method", "address", "end")}
    ]
    return dict(
        condition=reviewed_condition(
            compare(
                ABSORBED_STATE_KEY, state["WAIT_ACTION"], source="等待吸收后的动作"
            ),
            evidence,
            summary="吸收状态为 WAIT_ACTION 时推进到 AFTER",
            extend="app.cEm0160Extend",
            inputs={
                ABSORBED_STATE_KEY: dict(
                    label="吸收茧状态",
                    options=[
                        dict(label=name, value=value)
                        for name, value in metadata.enum(state["type"])[1].items()
                    ],
                )
            },
        ),
        onTrue={ABSORBED_STATE_KEY: state["AFTER"]},
        effectSummary="将吸收茧状态从 WAIT_ACTION 推进到 AFTER",
    )


def recover_condition(node, enemy_id, resources):
    if node.get("commandType") != MODE_COMMAND:
        return None
    from ..shared.logic.expressions import combined, compare
    from ..shared.logic.field_checks import condition_evidence, reviewed_condition

    parameters, sources = resources.package_value(enemy_id, UNIQUE_SPEC)
    threshold = parameters["UnleashModeChangeThreshold"]
    if type(threshold) not in (int, float):
        raise ValueError("锁刃龙模式切换的生命阈值不是数值")
    result = reviewed_condition(
        (
            combined(
                "all",
                compare(
                    "self_basic_legendary_id", 2, source="Basic.LegendaryID == KING"
                ),
                compare(
                    "extend:app.cEm0160Extend._Mode",
                    1,
                    "ne",
                    source="当前模式不为 UNLEASH",
                ),
                compare(
                    "health_percent",
                    threshold,
                    "lt",
                    source="HealthNormalized × 100 严格小于 UnleashModeChangeThreshold",
                ),
            )
            if threshold >= MIN_MODE_THRESHOLD
            else dict(kind="constant", value=False)
        ),
        condition_evidence("arkveld_unleash"),
        summary=f"历战分类为 KING、当前不是 UNLEASH，且生命值 < {threshold:g}%",
        extend="app.cEm0160Extend",
        inputs={
            "health_percent": dict(
                label="生命值百分比", number=True, min=0, max=100, unit="%"
            ),
            "extend:app.cEm0160Extend._Mode": dict(
                label="当前模式",
                options=[
                    dict(label="DEFAULT", value=0),
                    dict(label="UNLEASH", value=1),
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
