"""Offline analysis entry for EM0156_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0156_00_0"
NATIVE_OWNER = "Em0156_00"

MAX_RAILGUN_COMMAND = "app.Em0156_00BTableCommand.cCheckTransRailgunChargeMax"


def recover_condition(node, enemy_id, resources):
    if node.get("commandType") != MAX_RAILGUN_COMMAND:
        return None
    from ..shared.logic.expressions import combined, invert, runtime
    from ..shared.logic.field_checks import condition_evidence, reviewed_condition

    ready = "extend:app.cEm0156_00Extend._IsCanTransMaxRailgunCharge"
    return reviewed_condition(
        combined(
            "all",
            invert(runtime("tired", "cEnemyContext.get_IsTired()")),
            runtime(ready, "Extend +0xf6 的最大蓄电转移许可标志"),
        ),
        condition_evidence("rey_dau_max_charge"),
        summary="不疲劳，且允许转入最大电磁炮蓄电",
        extend="app.cEm0156_00Extend",
        inputs={
            "tired": dict(label="疲劳状态", boolean=True),
            ready: dict(label="允许转入最大电磁炮蓄电", boolean=True),
        },
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
