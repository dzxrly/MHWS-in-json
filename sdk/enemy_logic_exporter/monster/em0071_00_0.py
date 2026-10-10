"""Offline analysis entry for EM0071_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0071_00_0"
NATIVE_OWNER = "Em0071_00"

# Verified Extend rule of this monster (game 1.42.0.2): plain equality of one
# internal state field, evaluated by the shared "unique_state" kind. The record
# lives in data/rules.v1.json; the offset is checked by the curation command.
EXTEND_TYPE = "app.cEm0071_00Extend"
STATE_TYPE_COMMAND = "app.btable.Em0071_00BTableCommand.cCheckStateType"
STATE_TYPE_OFFSET = 0xEC

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
