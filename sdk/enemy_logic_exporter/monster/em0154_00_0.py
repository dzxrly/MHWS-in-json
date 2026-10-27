"""Offline analysis entry for EM0154_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0154_00_0"
NATIVE_OWNER = "Em0154_00"

# Reviewed native methods; local histories are split only at their actual reads.
LOCAL_HISTORY_TABLES = {
    "app.Em0154_00_BTable_AttackStay_Export": (
        "table_0d9ef720_1ec4_4f34_af19_653d2a1ec787",
    ),
}


def table_history_policy(row):
    method = row["method"]
    stems = LOCAL_HISTORY_TABLES.get(row["type"], ())
    local = any(
        method.startswith(stem) and method[len(stem) :].isdigit() for stem in stems
    )
    return dict(local=True) if local else None


SIDE_WALK_COMMAND = "app.Em0154_00BTableCommand.cSideWalkOffset"
SIDE_WALK_ARGUMENT = SIDE_WALK_COMMAND + "Arg"
SIDE_WALK_EXTEND = "app.cEm0154_00Extend"
SIDE_WALK_RECEIPT = "em0154_target_effects.v1.json"
SIDE_WALK_ANGLE_MULTIPLIERS = (3.1415927410125732,)


def verify_native_recipes(pe, metadata):
    from ..shared.logic.target_command_effects import verify_target_receipt

    return verify_target_receipt(pe, metadata, SIDE_WALK_RECEIPT)


def recover_target_command_effect(bound, evidence):
    from ..shared.logic.target_command_effects import side_walk_target_effect

    return side_walk_target_effect(
        bound,
        evidence,
        command=SIDE_WALK_COMMAND,
        argument_type=SIDE_WALK_ARGUMENT,
        extend_type=SIDE_WALK_EXTEND,
        receipt_name=SIDE_WALK_RECEIPT,
        angle_multipliers=SIDE_WALK_ANGLE_MULTIPLIERS,
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
