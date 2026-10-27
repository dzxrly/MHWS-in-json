"""Offline analysis entry for EM0161_00_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0161_00_0"
NATIVE_OWNER = "Em0161_00"


FORMULA_HISTORY_TABLES = {
    "app.Em0161_00_BTable_AttackStay_Export": (
        "table_9c5b141a_8a09_4d43_b09f_d93fc3d42161",
    ),
    "app.Em0161_00_BTable_CommonAttack_Export": (
        "table_a835c8b9_f2e4_436b_8c61_c56f98e8492f",
    ),
}


def table_history_policy(row):
    method = row["method"]
    policy = {}
    formula = FORMULA_HISTORY_TABLES.get(row["type"], ())
    if any(
        method.startswith(stem) and method[len(stem) :].isdigit() for stem in formula
    ):
        policy["formula"] = True
    return policy or None


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
