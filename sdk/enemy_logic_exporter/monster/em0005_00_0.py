"""Offline analysis entry for EM0005_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0005_00_0"
NATIVE_OWNER = "Em0005_00"

# Reviewed native methods; local histories are split only at their actual reads.
LOCAL_HISTORY_TABLES = {
    "app.Em0005_00_BTable_CommonAttack_Export": (
        "table_3836c102_83fa_489d_b2d8_c07eabbf6c0c",
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
