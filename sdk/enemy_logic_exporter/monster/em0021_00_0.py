"""Offline analysis entry for EM0021_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0021_00_0"
NATIVE_OWNER = "Em0021_00"

# Verified Extend rules of this monster (game 1.42.0.2); records live in
# data/rules.v1.json, the offsets below are checked by the curation command.
EXTEND_TYPE = "app.cEm0021_00Extend"
MUSHROOM_TYPE_COMMAND = "app.btable.Em0021_00BTableCommand.cCheckMushroomType"
CATCH_MUSHROOM_COMMAND = "app.btable.Em0021_00BTableCommand.cCheckCatchMushroom"
MUSHROOM_TYPE_OFFSET = 0x98
CATCH_MUSHROOM_OFFSET = 0xA0
# cCheckMushroomType: internal type 5 also satisfies any nonzero request.
ANY_MUSHROOM_TYPE = 5
# cCheckCatchMushroom: internal values that count as holding an item.
CATCH_MUSHROOM_VALUES = (0, 1, 2, 3, 4, 5, 7)

RULE_SPECS = (
    (
        MUSHROOM_TYPE_COMMAND,
        "mushroom",
        "专用",
        "蘑菇类型相等，或当前类型为 5 且要求类型不为 0",
        {"value": 0x10},
        EXTEND_TYPE,
        MUSHROOM_TYPE_OFFSET,
    ),
    (
        CATCH_MUSHROOM_COMMAND,
        "catch_mushroom",
        "专用",
        "拿取物品内部值属于 0、1、2、3、4、5、7",
        {},
        EXTEND_TYPE,
        CATCH_MUSHROOM_OFFSET,
    ),
)


def _compile_mushroom(compiler, predicate, values):
    from ..shared.logic.values import enum_number
    from ..shared.models.player_view import missing_state

    if not predicate.get("contextBinding"):
        return missing_state()
    key, _ = compiler.context_field(predicate["contextBinding"])
    expected = enum_number(values["value"])
    items = [compiler.context_option(key, expected)]
    if expected != 0:
        items.append(compiler.context_option(key, ANY_MUSHROOM_TYPE))
    return dict(op="any", items=items) if len(items) > 1 else items[0]


def _evaluate_mushroom(rule, bound, context, state):
    from ..shared.logic.predicates import context_value
    from ..shared.logic.values import enum_number

    actual = context_value(state, bound["contextBinding"])
    expected = enum_number(bound["values"]["value"])
    return actual == expected or actual == ANY_MUSHROOM_TYPE and expected != 0


def _compile_catch(compiler, predicate, values):
    from ..shared.models.player_view import missing_state

    if not predicate.get("contextBinding"):
        return missing_state()
    key, _ = compiler.context_field(predicate["contextBinding"])
    return dict(
        op="any", items=[compiler.context_option(key, v) for v in CATCH_MUSHROOM_VALUES]
    )


def _evaluate_catch(rule, bound, context, state):
    from ..shared.logic.predicates import context_value

    return context_value(state, bound["contextBinding"]) in CATCH_MUSHROOM_VALUES


RULE_KINDS = {
    "mushroom": dict(compile=_compile_mushroom, evaluate=_evaluate_mushroom),
    "catch_mushroom": dict(compile=_compile_catch, evaluate=_evaluate_catch),
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
