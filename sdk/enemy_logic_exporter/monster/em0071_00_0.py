"""Offline analysis entry for EM0071_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0071_00_0"
NATIVE_OWNER = "Em0071_00"

# Verified Extend rule of this monster (game 1.42.0.2): plain equality of one
# internal state field, evaluated by the shared "unique_state" kind. The record
# lives in data/rules.v1.json; the offset is checked by the curation command.
EXTEND_TYPE = "app.cEm0071_00Extend"
STATE_TYPE_COMMAND = "app.btable.Em0071_00BTableCommand.cCheckStateType"
STATE_TYPE_OFFSET = 0xEC

STATE_CHANGE_COMMAND = "app.btable.Em0071_00BTableCommand.cCheckStateChange"
UNIQUE_SPEC = dict(
    package="STM/GameDesign/Enemy/CommonData/StageResident/Data/{enemy}_StageResident.user.3.json",
    fields=["_Unique", "_SpeciesInfo"],
)


def recover_condition(node, enemy_id, resources):
    if node.get("commandType") != STATE_CHANGE_COMMAND:
        return None
    from ..shared.logic.expressions import combined, compare, invert, runtime
    from ..shared.logic.field_checks import condition_evidence, reviewed_condition
    from ..shared.logic.values import enum_number
    from ..shared.resources.reader import typed

    # The native implementation handles only the resource SUPER request.
    if enum_number(node["argument"]["_EditArg"]) != 1:
        expression = dict(kind="constant", value=False)
        return reviewed_condition(
            expression,
            condition_evidence("gore_state_change"),
            summary="此状态切换命令只接受 SUPER 请求",
            extend=EXTEND_TYPE,
        )
    parameters, sources = resources.package_value(enemy_id, UNIQUE_SPEC)
    safe, fes = parameters["SafeTransVital"], parameters["SafeTransVital_Fes"]
    levels = [
        typed(item)[1]["TransformValue"] for item in parameters["TransformPointInfo"]
    ]
    if not levels or any(
        type(value) not in (int, float) for value in (safe, fes, *levels)
    ):
        raise ValueError("黑蚀龙变身阈值表为空或包含非数值")
    count = f"extend:{EXTEND_TYPE}._TransformedCount"
    virus = f"extend:{EXTEND_TYPE}.<VirusValue>k__BackingField"
    state = f"extend:{EXTEND_TYPE}.<State>k__BackingField"
    option = "em0071_basic_option_tag_low_bit"
    force = combined(
        "all",
        compare(count, 0, source="首次变身"),
        combined(
            "any",
            combined(
                "all",
                compare(option, 0, source="Basic.OptionTag & 1"),
                compare(
                    "health_percent",
                    safe,
                    "lt",
                    source="HealthNormalized × 100 < SafeTransVital",
                ),
            ),
            combined(
                "all",
                compare(option, 1, source="Basic.OptionTag & 1"),
                compare(
                    "health_percent",
                    fes,
                    "lt",
                    source="HealthNormalized × 100 < SafeTransVital_Fes",
                ),
            ),
        ),
    )
    accumulated = combined(
        "any",
        *(
            combined(
                "all",
                compare(
                    count,
                    index,
                    "ge" if index == len(levels) - 1 else "eq",
                    source="变身次数；超出阈值表时使用最后一项",
                ),
                compare(
                    virus,
                    threshold,
                    "ge",
                    source=f"VirusValue ≥ TransformPointInfo[{index}].TransformValue",
                ),
            )
            for index, threshold in enumerate(levels)
        ),
    )
    result = reviewed_condition(
        combined(
            "all",
            compare(state, 2, "ne", source="当前不是 SUPER 状态"),
            invert(runtime("tired", "cEnemyContext.get_IsTired()")),
            combined("any", force, accumulated),
        ),
        condition_evidence("gore_state_change"),
        summary=f"非 SUPER 且不疲劳；首次变身生命低于 {safe:g}%（OptionTag 最低位为 0）或 {fes:g}%（最低位为 1），或病毒累积达到当前次数阈值 {levels}",
        extend=EXTEND_TYPE,
        inputs={
            count: dict(label="已经变身的次数", number=True, min=0, max=None),
            virus: dict(label="病毒累积值", number=True, min=0, max=None),
            state: dict(
                label="当前内部状态",
                options=[
                    dict(label="NORMAL", value=0),
                    dict(label="LOOK", value=1),
                    dict(label="SUPER", value=2),
                ],
            ),
            option: dict(
                label="Basic.OptionTag 的最低位",
                options=[
                    dict(label="0（通常阈值）", value=0),
                    dict(label="1（Fes 阈值）", value=1),
                ],
            ),
            "health_percent": dict(
                label="生命值百分比", number=True, min=0, max=100, unit="%"
            ),
            "tired": dict(label="疲劳状态", boolean=True),
        },
    )
    result["parameterSources"] = sources
    result["parameterBinding"] = UNIQUE_SPEC
    return result


RULE_SPECS = (
    (
        STATE_TYPE_COMMAND,
        "unique_state",
        "专用",
        "专用内部状态相等；不将其解释为全局战斗阶段",
        {"value": 0x10},
        EXTEND_TYPE,
        STATE_TYPE_OFFSET,
    ),
)


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
