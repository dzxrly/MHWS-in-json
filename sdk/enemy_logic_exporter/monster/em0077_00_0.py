"""Offline analysis entry for EM0077_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0077_00_0"
NATIVE_OWNER = "Em0077_00"

# Reviewed native methods; local histories are split only at their actual reads.
LOCAL_HISTORY_TABLES = {
    "app.Em0077_00_BTable_CommonAttack_Export": (
        "table_0efbf28f_52d5_4f4e_bf80_d3e4e7091cff",
        "table_527b5fb2_98e8_4384_b594_8f94c59d6a19",
        "table_73d6aa18_e552_40a4_8b42_a881209aa2e9",
        "table_dbe09b32_ecc6_43d2_8de0_81ea1bdb33b7",
    ),
}


def table_history_policy(row):
    method = row["method"]
    stems = LOCAL_HISTORY_TABLES.get(row["type"], ())
    local = any(
        method.startswith(stem) and method[len(stem) :].isdigit() for stem in stems
    )
    return dict(local=True) if local else None


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
