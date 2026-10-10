"""Offline analysis entry for EM0155_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0155_00_0"
NATIVE_OWNER = "Em0155_00"

# cCheckContractionDownReturnTimer (game 1.42.0.2): cEm0155_00Extend
# _ContractionDownReturnTimer (ace.TIMER at +0xb0) is _Enabled and _IsTimeOut.
FIELD_CHECKS = {
    "app.btable.Em0155_00BTableCommand.cCheckContractionDownReturnTimer": dict(
        spec=(
            "all",
            ("extend:_ContractionDownReturnTimer._Enabled",),
            ("extend:_ContractionDownReturnTimer._IsTimeOut",),
        ),
        extend="app.cEm0155_00Extend",
        evidence=[
            dict(
                type="app.btable.Em0155_00BTableCommand.cCheckContractionDownReturnTimer",
                method="onExecute1234220",
                address="0x149d9a910",
                end="0x149d9a950",
            )
        ],
        summary="ContractionDownReturnTimer 已启用且已超时",
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
