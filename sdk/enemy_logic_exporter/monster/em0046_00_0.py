"""Offline analysis entry for EM0046_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0046_00_0"
NATIVE_OWNER = "Em0046_00"

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
