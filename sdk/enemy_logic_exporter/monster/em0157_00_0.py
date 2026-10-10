"""Offline analysis entry for EM0157_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0157_00_0"
NATIVE_OWNER = "Em0157_00"

# cCheckVeilCladTimer (game 1.42.0.2): cEm0157_00Extend _AllVeilPurgeTimer
# (ace.TIMER at +0xb8) has _IsTimeOut (+0xc6).
FIELD_CHECKS = {
    "app.Em0157_00BTableCommand.cCheckVeilCladTimer": dict(
        spec=("extend:_AllVeilPurgeTimer._IsTimeOut",),
        extend="app.cEm0157_00Extend",
        evidence=[
            dict(
                type="app.Em0157_00BTableCommand.cCheckVeilCladTimer",
                method="onExecute1146696",
                address="0x145317460",
                end="0x1453174b0",
            )
        ],
        summary="AllVeilPurgeTimer 已超时",
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
