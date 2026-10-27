"""Offline analysis entry for EM0150_50_0; no inferred or placeholder graph."""

ENEMY_ID = "EM0150_50_0"
NATIVE_OWNER = "Em0150_50"


FORMULA_HISTORY_TABLES = {
    "app.Em0150_50_BTable_Life_Export": ("table_33117d36_79de_4c27_a50c_9b8678aa17b9",)
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
