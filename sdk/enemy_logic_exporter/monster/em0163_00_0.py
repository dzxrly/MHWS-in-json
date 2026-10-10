"""Offline analysis entry for EM0163_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0163_00_0"
NATIVE_OWNER = "Em0163_00"

# cIsNestArea (game 1.42.0.2): cEnemyContext.Area._CurrentAreaNo (+0xe0) == 12.
FIELD_CHECKS = {
    "app.btable.Em0163_00BTableCommand.cIsNestArea": dict(
        spec=("key:self_current_area_no", "==", 12),
        evidence=[
            dict(
                type="app.btable.Em0163_00BTableCommand.cIsNestArea",
                method="onExecute1234507",
                address="0x144a200b0",
                end="0x144a200f0",
            )
        ],
        summary="怪物位于区域 12",
    ),
}


def recover_condition(node, enemy_id, resources):
    """Reviewed field-comparison commands of this monster (FIELD_CHECKS)."""
    from ..shared.logic.field_checks import declared_condition

    return declared_condition(FIELD_CHECKS, node)


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
