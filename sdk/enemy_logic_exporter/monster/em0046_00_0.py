"""Offline analysis entry for EM0046_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0046_00_0"
NATIVE_OWNER = "Em0046_00"

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
                address="0x144195220",
                end="0x144195270",
            )
        ],
        summary="IsSwimCombatPhase 成立且 DoneSwimCombatPhaseEndAction 不成立",
    ),
}


def recover_condition(node, enemy_id, resources):
    """Reviewed field-comparison commands of this monster (FIELD_CHECKS)."""
    from ..shared.logic.field_checks import declared_condition

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
