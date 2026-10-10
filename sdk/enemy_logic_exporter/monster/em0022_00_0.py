"""Offline analysis entry for EM0022_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0022_00_0"
NATIVE_OWNER = "Em0022_00"

# Area checks (game 1.42.0.2) read cEnemyContext.Area _CurrentStageNo (+0x14)
# and _CurrentAreaNo (+0xe0): cCheckNest is area 14 on stage 3; cCheckThrowBall
# is true unless the monster is in area 4 of stage 3.
FIELD_CHECKS = {
    "app.btable.Em0022_00BTableCommand.cCheckNest": dict(
        spec=(
            "all",
            ("key:self_current_area_no", "==", 14),
            ("key:self_current_stage_no", "==", 3),
        ),
        evidence=[
            dict(
                type="app.btable.Em0022_00BTableCommand.cCheckNest",
                method="onExecute1233721",
                address="0x1453933d0",
                end="0x145393400",
            )
        ],
        summary="怪物位于地图 3 的区域 14",
    ),
    "app.btable.Em0022_00BTableCommand.cCheckThrowBall": dict(
        spec=(
            "any",
            ("key:self_current_stage_no", "!=", 3),
            ("key:self_current_area_no", "!=", 4),
        ),
        evidence=[
            dict(
                type="app.btable.Em0022_00BTableCommand.cCheckThrowBall",
                method="onExecute1233725",
                address="0x1459df9f0",
                end="0x1459dfa30",
            )
        ],
        summary="怪物不在地图 3 的区域 4",
    ),
}


def recover_condition(node, enemy_id, resources):
    """Reviewed field-comparison commands of this monster (FIELD_CHECKS)."""
    from ..shared.logic.field_checks import declared_condition

    return declared_condition(FIELD_CHECKS, node)


# Verified Extend rule of this monster (game 1.42.0.2); the record lives in
# data/rules.v1.json, the offsets below are checked by the curation command.
EXTEND_TYPE = "app.cEm0022_00Extend"
BREAK_FANG_COMMAND = "app.btable.Em0022_00BTableCommand.cCheckBreakFangCount"
BREAK_FANG_OFFSET = 0x70
# Resource compare type -> operator over the broken fang count.
FANG_COMPARE = {0: "ge", 1: "le", 2: "eq"}

RULE_SPECS = (
    (
        BREAK_FANG_COMMAND,
        "fang_count",
        "专用",
        "断牙数量：比较类型 0 为 ≥，1 为 ≤，2 为 =",
        {"compare": 0x10, "value": 0x18},
        EXTEND_TYPE,
        BREAK_FANG_OFFSET,
    ),
)


def _compile_fang_count(compiler, predicate, values):
    from ..shared.logic.values import enum_number
    from ..shared.models.player_view import comparison, missing_state, unknown

    if not predicate.get("contextBinding"):
        return missing_state()
    key, label = compiler.context_field(predicate["contextBinding"])
    operator = FANG_COMPARE.get(enum_number(values["compare"]))
    if operator is None:
        return unknown("不支持的断牙数量比较")
    compiler.inputs[key] = dict(label=label, number=True, min=0, max=None)
    return comparison(key, operator, values["value"])


def _evaluate_fang_count(rule, bound, context, state):
    from ..shared.logic.predicates import context_value
    from ..shared.logic.values import MissingState, enum_number, number

    actual = context_value(state, bound["contextBinding"])
    expected = number(bound["values"]["value"])
    operator = FANG_COMPARE.get(enum_number(bound["values"]["compare"]))
    if operator is None:
        raise MissingState("不支持的断牙数量比较")
    return {
        "ge": actual >= expected,
        "le": actual <= expected,
        "eq": actual == expected,
    }[operator]


RULE_KINDS = {
    "fang_count": dict(compile=_compile_fang_count, evaluate=_evaluate_fang_count)
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
    context=None
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
